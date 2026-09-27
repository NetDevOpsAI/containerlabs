# SRv6 uSID L3VPN Lab: High-Level Design

## 1. About this document

### 1.1 Purpose

This document describes the design of the `iol-srv6` lab. It explains each part of the design and each configuration block. It shows how one packet travels through the lab. It gives a hop-by-hop procedure to check every step.

### 1.2 Scope

The document covers the lab in this folder:

- `lab-srv6.clab.yml` (the topology)
- `configs/*.cfg` (the startup configuration of each node)
- `gen_configs.py` (the script that makes the configurations)
- `verify.py` and `cli.py` (the test tools)

### 1.3 How to read the document

- **Observed** means the text comes from a command or a packet capture in the running lab. The lab was tested on 2026-09-21 with IOS-XE 17.18.2 (IOL image).
- **Concept** means the text explains a general SRv6 rule. The lab does not show this rule in its output.
- SPI values, sequence numbers, and MAC addresses change after each deploy. IPv6 link-local addresses change too. Use them as examples only.
- Segment Routing over IPv6 is "SRv6". A micro segment is a "uSID".

### 1.4 Terms

| Term | Meaning |
|---|---|
| CE | Customer edge router. It connects to the provider. |
| PE | Provider edge router. It has the customer VRF. |
| P | Provider core router. It only forwards IPv6 packets. |
| VRF | Virtual routing and forwarding table. It keeps customer routes apart. |
| SID | Segment identifier. In SRv6 it is a 128-bit IPv6 address. |
| Locator | The IPv6 prefix that a router owns. All SIDs of the router come from it. |
| uSID | Micro segment. A short SID (16 bits) that a router packs into one IPv6 address with other uSIDs. |
| SRH | Segment routing header. An IPv6 extension header that holds a list of SIDs. |
| ECMP | Equal-cost multipath. A router uses more than one path with the same cost. |
| ESP | Encapsulating Security Payload. The IPsec protocol that encrypts the data. |
| GRE | Generic Routing Encapsulation. The tunnel type of `Tunnel100`. |

## 2. Design summary

The lab has 10 nodes. Two hosts connect through two CE routers, two PE routers, and four P routers.

| Layer | Technology | Where |
|---|---|---|
| Core links | IPv6 with link-local addresses only | All P and PE core links |
| Core IGP | IS-IS level 2, IPv6 multi-topology | PE and P routers |
| Core transport | SRv6 with uSID (format `usid-f3216`) | PE and P routers |
| Customer service | BGP VPNv4 (IPv4 VPN) between PE routers | `pe-rtr-1`, `pe-rtr-2` |
| PE-CE routing | eBGP in VRF `CE-RTR1` | PE to CE |
| Customer overlay | GRE tunnel protected by IPsec | `ipsec-rtr1` to `ipsec-rtr2` |
| Customer LAN | IPv4 static routes through `Tunnel100` | CE to host |

Section 5.8 explains how the VPNv4 customer service works.

Five design rules apply:

1. The core has no IPv4 forwarding. The customer IPv4 packet rides inside an IPv6 packet.
2. The core links have no global IPv6 address. Only the loopbacks have global IPv6 addresses.
3. The P routers do not know any customer route. They only use the locator routes from IS-IS.
4. The PE routers add and remove the SRv6 encapsulation.
5. The CE routers encrypt the traffic. The provider network carries only ESP packets.

## 3. Topology

### 3.1 Diagram

```
                         SRv6 core: IS-IS, IPv6 link-local links
                  +-----------------------------------------------+
                  |                                               |
                  |        +-------+            +-------+         |
                  |   +----|  P1   |------------|  P2   |----+    |
                  |   |    +-------+ \        / +-------+    |    |
                  |   |               \      /                |    |
 host1 -- CE1 -- PE1 -+                 \    /                 +- PE2 -- CE2 -- host2
                  |   |                /    \                 |    |
                  |   |    +-------+ /        \ +-------+     |    |
                  |   +----|  P3   |------------|  P4   |-----+    |
                  |        +-------+            +-------+          |
                  +-----------------------------------------------+

 host1 = host1, CE1 = ipsec-rtr1, PE1 = pe-rtr-1, P1..P4 = core-p-rtr-1..4,
 PE2 = pe-rtr-2, CE2 = ipsec-rtr2, host2 = host2

 Cross links: P1-P4 and P3-P2.

 Overlay:  CE1 Tunnel100 (172.30.1.1) <====== GRE over IPsec ======> CE2 Tunnel100 (172.30.1.2)
```

### 3.2 Node list

| Node | Role | Container name | Mgmt IP | Loopback(s) |
|---|---|---|---|---|
| `host1` | Host, site 1 | `clab-iol-srv6-host1` | 172.100.210.11 | none |
| `ipsec-rtr1` | CE, AS 65250 | `clab-iol-srv6-ipsec-rtr1` | 172.100.210.12 | Lo100 172.20.1.1/32 |
| `pe-rtr-1` | PE, AS 65001 | `clab-iol-srv6-pe-rtr-1` | 172.100.210.13 | Lo0 10.0.0.1/32, 2001:DB8:FFFF::1/128 |
| `core-p-rtr-1` | P | `clab-iol-srv6-core-p-rtr-1` | 172.100.210.14 | Lo0 10.0.0.11/32, 2001:DB8:FFFF::11/128 |
| `core-p-rtr-2` | P | `clab-iol-srv6-core-p-rtr-2` | 172.100.210.15 | Lo0 10.0.0.12/32, 2001:DB8:FFFF::12/128 |
| `core-p-rtr-3` | P | `clab-iol-srv6-core-p-rtr-3` | 172.100.210.16 | Lo0 10.0.0.13/32, 2001:DB8:FFFF::13/128 |
| `core-p-rtr-4` | P | `clab-iol-srv6-core-p-rtr-4` | 172.100.210.17 | Lo0 10.0.0.14/32, 2001:DB8:FFFF::14/128 |
| `pe-rtr-2` | PE, AS 65001 | `clab-iol-srv6-pe-rtr-2` | 172.100.210.18 | Lo0 10.0.0.2/32, 2001:DB8:FFFF::2/128 |
| `ipsec-rtr2` | CE, AS 65351 | `clab-iol-srv6-ipsec-rtr2` | 172.100.210.19 | Lo100 172.21.1.1/32 |
| `host2` | Host, site 2 | `clab-iol-srv6-host2` | 172.100.210.20 | none |

All nodes use the image `vrnetlab/cisco_iol:17.18.02`. Log in with `ssh admin@clab-iol-srv6-<node>` (password `admin`).

### 3.3 Links

`Ethernet0/0` is the management port of each node. The data links start at `Ethernet0/1`. In the containers, `ethN` is `Ethernet0/N`. Use this rule when you read packet captures.

| # | Node A | Interface A | Node B | Interface B | Network | Type |
|---|---|---|---|---|---|---|
| 1 | `host1` | Et0/1 | `ipsec-rtr1` | Et0/2 | 192.168.1.0/24 | IPv4 LAN |
| 2 | `ipsec-rtr1` | Et0/1 | `pe-rtr-1` | Et0/1 | 10.1.1.0/30 | IPv4, eBGP, VRF |
| 3 | `pe-rtr-1` | Et0/2 | `core-p-rtr-1` | Et0/1 | link-local | Core |
| 4 | `pe-rtr-1` | Et0/3 | `core-p-rtr-3` | Et0/1 | link-local | Core |
| 5 | `core-p-rtr-1` | Et0/2 | `core-p-rtr-2` | Et0/1 | link-local | Core |
| 6 | `core-p-rtr-1` | Et0/3 | `core-p-rtr-4` | Et0/2 | link-local | Core |
| 7 | `core-p-rtr-3` | Et0/2 | `core-p-rtr-4` | Et0/1 | link-local | Core |
| 8 | `core-p-rtr-3` | Et0/3 | `core-p-rtr-2` | Et0/2 | link-local | Core |
| 9 | `core-p-rtr-2` | Et0/3 | `pe-rtr-2` | Et0/2 | link-local | Core |
| 10 | `core-p-rtr-4` | Et0/3 | `pe-rtr-2` | Et0/3 | link-local | Core |
| 11 | `pe-rtr-2` | Et0/1 | `ipsec-rtr2` | Et0/1 | 10.2.2.0/30 | IPv4, eBGP, VRF |
| 12 | `ipsec-rtr2` | Et0/2 | `host2` | Et0/1 | 192.168.2.0/24 | IPv4 LAN |

The topology picture uses other interface numbers. The lab uses the numbers in this table.

### 3.4 Path cost

Each core link has IS-IS metric 10. From `pe-rtr-1` to the locator of `pe-rtr-2`, the cost is 30. Four paths have this cost:

| Path | Nodes |
|---|---|
| A | PE1, P1, P2, PE2 |
| B | PE1, P1, P4, PE2 |
| C | PE1, P3, P2, PE2 |
| D | PE1, P3, P4, PE2 |

The routers use ECMP over these paths. Each router chooses a next hop with its own hash. Do not assume a path. Use the validation procedure in section 9 to find it.

## 4. Addressing plan

| Item | Value | Note |
|---|---|---|
| Management network | 172.100.210.0/24 | Docker network `clab-iol-srv6` |
| Core loopback IPv4 | 10.0.0.<n>/32 | Used as IS-IS router ID and BGP router ID |
| Core loopback IPv6 | 2001:DB8:FFFF::<n>/128 | BGP session address, SRv6 encapsulation source |
| Core links | IPv6 link-local only (`ipv6 enable`) | No global IPv4 or IPv6 address |
| SRv6 block | FCBB:BB00::/32 | Shared by all nodes |
| SRv6 locators | FCBB:BB00:<n>::/48 | One per PE and P router |
| PE-CE link, site 1 | 10.1.1.0/30 (CE .1, PE .2) | In VRF `CE-RTR1` on the PE |
| PE-CE link, site 2 | 10.2.2.0/30 (CE .1, PE .2) | In VRF `CE-RTR1` on the PE |
| Customer LAN, site 1 | 192.168.1.0/24 (CE .1, host .10) | |
| Customer LAN, site 2 | 192.168.2.0/24 (CE .1, host .10) | |
| Tunnel source | 172.20.1.1/32 (CE1), 172.21.1.1/32 (CE2) | `Loopback100` |
| Tunnel network | 172.30.1.0/30 (CE1 .1, CE2 .2) | `Tunnel100` |

The node number `<n>` is:

| Node | `<n>` (hex, as written in the address) |
|---|---|
| `pe-rtr-1` | 1 |
| `pe-rtr-2` | 2 |
| `core-p-rtr-1` | 11 |
| `core-p-rtr-2` | 12 |
| `core-p-rtr-3` | 13 |
| `core-p-rtr-4` | 14 |

IPv6 addresses use hexadecimal digits. The locator `FCBB:BB00:11::/48` for `core-p-rtr-1` uses the hex value 0x0011.

## 5. Design details

### 5.1 IPv6 with link-local addresses in the core

Each core interface has the command `ipv6 enable`. This command makes a link-local address (`FE80::/10`) from the MAC address. The interface has no other address.

IS-IS sends its packets on the data link. It does not need a global address. The IS-IS neighbor uses the link-local address as the IPv6 next hop. In the FIB, a route shows a next hop such as `FE80::A8BB:CCFF:FE00:110, Ethernet0/2`.

The loopbacks have global IPv6 addresses. The BGP session between the PE routers needs them. The SRv6 encapsulation source also needs one.

### 5.2 IS-IS

IS-IS is the only IGP in the core.

| Parameter | Value | Reason |
|---|---|---|
| Process | `router isis 1` | Same on all core nodes |
| NET | `49.0001.0000.0000.<n>.00` | One area. The system ID is the node number in 4 digits. |
| Level | `is-type level-2-only` | One level is enough |
| Metric style | `wide` | SRv6 locators need wide metrics |
| Address family | `ipv6` with `multi-topology` | Carries the IPv6 topology and the SRv6 locator |
| Interface type | `isis network point-to-point` | No DIS election on Ethernet links |
| Interfaces | Core links and `Loopback0` | `ipv6 router isis 1` on each |

The IS-IS LSP of each router has the SRv6 locator in the TLV "SRv6 Locator". The TLV has the End SID and its structure. Observed for `pe-rtr-1`:

```
SRv6 Locator: (MT-IPv6) FCBB:BB00:1::/48 Metric:0 Algorithm:0
  End SID: FCBB:BB00:1:: uN (PSP/USD)
    SID Structure:
      Block Length: 32, Node-ID Length: 16, Func-Length: 0, Args-Length: 80
```

The other routers learn the locator as a normal IPv6 route with IS-IS type `I2`.

### 5.3 SRv6 SID and uSID

#### 5.3.1 SID structure

An SRv6 SID has 128 bits. The format `usid-f3216` divides the SID in this way:

```
 |<-- block: 32 bits -->|<- node: 16 bits ->|<- function: 16 bits ->|<---- argument: 64 bits ---->|
   FCBB:BB00              0002                E002                    0000:0000:0000:0000
```

Example: the SID `FCBB:BB00:2:E002::` has these fields:

| Field | Bits | Value | Meaning |
|---|---|---|---|
| Block | 32 | `FCBB:BB00` | The SRv6 block of the network |
| Node ID | 16 | `0002` | `pe-rtr-2` |
| Function | 16 | `E002` | The behavior on the node (here, decapsulate and look up in a VRF) |
| Argument | 64 | zeros | Not used by this SID |

The locator is the block plus the node ID: `FCBB:BB00:2::/48`.

#### 5.3.2 SID behaviors in this lab

The routers make three kinds of SID:

| Behavior | Full name | Function values | What the router does |
|---|---|---|---|
| `uN` | Micro node (End with NEXT-CSID) | `::` (no function) | The packet has arrived at this node. Shift the next uSID into the active position. Forward the packet. |
| `uA` | Micro adjacency (End.X with NEXT-CSID) | `E000`, `E001`, `E002` | Send the packet on one specific link. |
| `uDT4` | Micro decapsulation and IPv4 table lookup (End.DT4) | `E002` on the PEs | Remove the outer IPv6 header. Look up the inner IPv4 destination in a VRF. |

`PSP/USD` after `uN` and `uA` is the flavor. `PSP` is penultimate segment pop. `USD` is ultimate segment decapsulation. These flavors matter only when a packet has an SRH. This lab does not use an SRH.

#### 5.3.3 SID table (observed)

The routers assign the `uA` function values in the order of the interface list. The BGP process assigns the `uDT4` value.

| Node | uN | uA (interface) | uDT4 |
|---|---|---|---|
| `pe-rtr-1` | `FCBB:BB00:1::` | `:1:E000::` (Et0/3 to P3), `:1:E001::` (Et0/2 to P1) | `FCBB:BB00:1:E002::` (VRF `CE-RTR1`) |
| `pe-rtr-2` | `FCBB:BB00:2::` | `:2:E000::` (Et0/3 to P4), `:2:E001::` (Et0/2 to P2) | `FCBB:BB00:2:E002::` (VRF `CE-RTR1`) |
| `core-p-rtr-1` | `FCBB:BB00:11::` | `:11:E000::` (Et0/1 to PE1), `:11:E001::` (Et0/2 to P2), `:11:E002::` (Et0/3 to P4) | none |
| `core-p-rtr-2` | `FCBB:BB00:12::` | `:12:E000::` (Et0/3 to PE2), `:12:E001::` (Et0/2 to P3), `:12:E002::` (Et0/1 to P1) | none |
| `core-p-rtr-3` | `FCBB:BB00:13::` | `:13:E000::` (Et0/1 to PE1), `:13:E001::` (Et0/2 to P4), `:13:E002::` (Et0/3 to P2) | none |
| `core-p-rtr-4` | `FCBB:BB00:14::` | `:14:E000::` (Et0/3 to PE2), `:14:E001::` (Et0/1 to P3), `:14:E002::` (Et0/2 to P1) | none |

The P routers have locators and SIDs. Normal shortest-path traffic does not use these SIDs. See section 7.3.

### 5.4 VRF and BGP VPNv4

#### 5.4.1 VRF

Each PE has one VRF with the same name and the same route targets:

| Item | Value |
|---|---|
| VRF name | `CE-RTR1` |
| Route distinguisher | `65001:1` |
| Route target export and import | `65001:1` |
| VRF interface | `Ethernet0/1` (link to the CE) |

Both PE routers use the same VRF name and route target. Each router imports the routes that the other PE exports.

#### 5.4.2 iBGP between the PE routers

| Item | Value |
|---|---|
| AS | 65001 (both PE routers) |
| Neighbor address | The IPv6 loopback of the other PE (`2001:DB8:FFFF::1` and `::2`) |
| Update source | `Loopback0` |
| Address family | `vpnv4` only (`no bgp default ipv4-unicast`) |
| Community | `send-community extended` (carries the route target) |

The BGP TCP session uses IPv6. The session runs between the loopbacks. IS-IS makes these loopback addresses reachable.

#### 5.4.3 SID for the VRF

In the VRF address family, the command `segment-routing srv6` links the VRF to the locator `LOC1`. The command `alloc-mode per-vrf` makes one SID for the whole VRF. Observed on `pe-rtr-1`:

```
FCBB:BB00:1:E002::   LOC1   uDT4   CE-RTR1   router bgp
```

Two BGP messages carry the SID:

- A PE that exports a route adds its `uDT4` SID to the VPNv4 route. The BGP attribute is the SRv6 L3 Service TLV (RFC 9252).
- The remote PE keeps the SID with the route. IOS shows it as `srv6 out-sid`. The local SID for the same prefix is `srv6 in-sid`.

Observed on `pe-rtr-1` for the route `172.21.1.1/32`, learned from `pe-rtr-2`:

```
2001:DB8:FFFF::2 (metric 40) (via default) from 2001:DB8:FFFF::2 (10.0.0.2)
  Extended Community: RT:65001:1
  srv6 out-sid: FCBB:BB00:2:E002::
```

The BGP next hop is `2001:DB8:FFFF::2`. The forwarding table uses the SID and not the next hop. See section 7.1.

### 5.5 PE-CE eBGP

| Site | CE | CE AS | PE address | CE address | Prefix that the CE announces |
|---|---|---|---|---|---|
| 1 | `ipsec-rtr1` | 65250 | 10.1.1.2 | 10.1.1.1 | 172.20.1.1/32 |
| 2 | `ipsec-rtr2` | 65351 | 10.2.2.2 | 10.2.2.1 | 172.21.1.1/32 |

Each CE announces only its tunnel source loopback (`Loopback100`). The provider network then carries the traffic between the two tunnel endpoints. The provider network does not carry the customer LAN routes.

### 5.6 IPsec overlay

The two CE routers make a GRE tunnel and protect it with IPsec.

| Item | Value |
|---|---|
| Tunnel | `Tunnel100`, GRE/IP |
| Tunnel addresses | 172.30.1.1/30 (CE1), 172.30.1.2/30 (CE2) |
| Tunnel source and destination | `Loopback100` of each CE |
| IKE (phase 1) | ISAKMP policy 10: AES-256, SHA-256, pre-shared key, DH group 14 |
| IPsec (phase 2) | Transform set `TS`: `esp-aes 256`, `esp-sha256-hmac`, tunnel mode |
| Protection | `tunnel protection ipsec profile IPSEC-PROF` |
| MSS | `ip tcp adjust-mss 1360` |
| LAN routes | `192.168.2.0/24` via `Tunnel100` on CE1, `192.168.1.0/24` via `Tunnel100` on CE2 |

The IPsec selector is GRE (protocol 47) between the two loopbacks. Observed on `ipsec-rtr1`:

```
local  ident (addr/mask/prot/port): (172.20.1.1/255.255.255.255/47/0)
remote ident (addr/mask/prot/port): (172.21.1.1/255.255.255.255/47/0)
transform: esp-256-aes esp-sha256-hmac ,
in use settings ={Tunnel, }
```

The IPsec traffic is a normal IPv4 flow between the two loopbacks. The BGP routes in the VRF and the SRv6 core carry it.

### 5.7 Hosts

The hosts are IOL routers. They have `Ethernet0/1` in the customer LAN and a default route to the CE. Their management port `Ethernet0/0` is in `vrf definition MGMT`. This VRF keeps the management network out of the test path.

If the management port is not in a VRF, a host sends lab traffic through `Ethernet0/0`. The ping then works but does not use the lab. The lab has this VRF to prevent this fault.

### 5.8 How the VPNv4 customer service works

This section explains the customer service for a network engineer who knows MPLS L3VPN. It follows one route, `172.21.1.1/32`, from `ipsec-rtr2` to `ipsec-rtr1`. All output in this section is observed.

#### 5.8.1 What the service does

The customer has two sites. Each site has one CE router. The service gives the two CE routers IPv4 reachability to each other across the provider network.

- Each PE keeps the customer routes in a VRF. The other customers, and the provider, do not see these routes.
- The two PE routers exchange the customer routes with MP-BGP (address family VPNv4).
- The core carries the customer packets inside IPv6 packets. The lab has no MPLS.
- In this lab, the customer uses the service to connect the two tunnel loopbacks (`172.20.1.1/32` and `172.21.1.1/32`). The customer builds the IPsec tunnel on top of this service (section 5.6).

What each device knows:

| Device | Customer routes | Provider routes | Observed |
|---|---|---|---|
| CE | Own site and the remote loopback | None | The CE has one eBGP neighbor: the PE (AS 65001). |
| PE | In VRF `CE-RTR1` and in the VPNv4 table | In the global IPv6 table | The global table has no customer route. |
| P | None | In the global IPv6 table | `show bgp all summary` shows `% BGP not active`. |

Observed on `pe-rtr-1`: the customer route is in the VRF and not in the global table.

```
pe-rtr-1#show ip route 172.21.1.1
% Network not in table

pe-rtr-1#show ip route vrf CE-RTR1 bgp
B        172.20.1.1 [20/0] via 10.1.1.1
B        172.21.1.1 [200/0] via FCBB:BB00:2:E002:: (default:ipv6)
```

#### 5.8.2 Compare with MPLS L3VPN

The control plane is the same as in MPLS L3VPN. Only two things change: the VPN identifier in the packet and the transport to the remote PE.

| Function | MPLS L3VPN | This lab |
|---|---|---|
| Customer separation on the PE | VRF | VRF `CE-RTR1` |
| Make the prefix unique | Route distinguisher (RD) | RD `65001:1` |
| Select which VRF gets the route | Route target (RT) | RT `65001:1` (import and export) |
| PE to PE route exchange | MP-BGP VPNv4 over an IPv4 loopback | MP-BGP VPNv4 over an IPv6 loopback |
| BGP next hop | IPv4 loopback of the PE | IPv6 loopback of the PE (`2001:DB8:FFFF::2`) |
| **VPN identifier in the packet** | VPN label (MPLS) | uDT4 SID in the IPv6 destination address |
| **Transport to the remote PE** | Transport label (LDP or SR-MPLS) | IPv6 route to the locator (IS-IS). No label. |
| PE to CE | eBGP | eBGP |
| State in the core | Labels | IPv6 routes only |

#### 5.8.3 The three tables on a PE

| Table | What it holds | Command |
|---|---|---|
| Global IPv6 table | Core loopbacks and locators from IS-IS | `show ipv6 route isis` |
| VRF IPv4 table | Customer routes of the VRF | `show ip route vrf CE-RTR1` |
| VPNv4 BGP table | Customer routes with RD, RT, and SID | `show bgp vpnv4 unicast all` |

Observed VRF settings on `pe-rtr-1`:

```
pe-rtr-1#show ip vrf detail CE-RTR1
VRF CE-RTR1 (VRF Id = 1); default RD 65001:1
  Interfaces:
    Et0/1
Address family ipv4 unicast (Table ID = 0x1):
  Export VPN route-target communities
    RT:65001:1
  Import VPN route-target communities
    RT:65001:1
  VRF label allocation mode: per-prefix
```

The line `VRF label allocation mode: per-prefix` is for MPLS labels. The lab does not use MPLS labels. The SRv6 SID mode is the command `alloc-mode per-vrf` in the BGP configuration.

#### 5.8.4 Route advertisement: CE2 to CE1

The route `172.21.1.1/32` is the loopback of `ipsec-rtr2`. It travels in eight steps.

| Step | Device | Action |
|---|---|---|
| 1 | `ipsec-rtr2` | The `network 172.21.1.1 mask 255.255.255.255` command puts the prefix in BGP. The CE sends it to the PE with eBGP. |
| 2 | `pe-rtr-2` | The PE receives the route in VRF `CE-RTR1`. It installs the route with next hop `10.2.2.1` and distance 20 (eBGP). |
| 3 | `pe-rtr-2` | The PE exports the route into VPNv4. It adds the RD (`65001:1`), the export RT (`65001:1`), and the `uDT4` SID of the VRF (`FCBB:BB00:2:E002::`). It sets the next hop to its own loopback (`2001:DB8:FFFF::2`). |
| 4 | `pe-rtr-2` | The PE sends the VPNv4 update to `pe-rtr-1`. The TCP session (port 179) runs between the IPv6 loopbacks. |
| 5 | `pe-rtr-1` | The PE checks the RT in the update. `RT:65001:1` matches the import RT of VRF `CE-RTR1`. The PE accepts the route and keeps the SID. |
| 6 | `pe-rtr-1` | The PE installs the route in the VRF with distance 200 (iBGP). The next hop is the SID. |
| 7 | `pe-rtr-1` | The PE sends the route to `ipsec-rtr1` with eBGP. It adds its own AS (65001) to the AS path. |
| 8 | `ipsec-rtr1` | The CE installs the route with next hop `10.1.1.2` and distance 20 (eBGP). |

The same route in each table:

| Device | Table | Entry (observed) |
|---|---|---|
| `ipsec-rtr2` | BGP | `172.21.1.1/32`, next hop `0.0.0.0`, weight 32768 (local) |
| `pe-rtr-2` | VRF route table | `B 172.21.1.1 [20/0] via 10.2.2.1` |
| `pe-rtr-2` | VPNv4 table | `65001:1:172.21.1.1/32`, exported with `RT:65001:1` and the local SID |
| `pe-rtr-1` | VPNv4 table | `65001:1:172.21.1.1/32`, next hop `2001:DB8:FFFF::2`, `srv6 out-sid FCBB:BB00:2:E002::` |
| `pe-rtr-1` | VRF route table | `B 172.21.1.1 [200/0] via FCBB:BB00:2:E002:: (default:ipv6)` |
| `ipsec-rtr1` | Route table | `B 172.21.1.1 [20/0] via 10.1.1.2` |

The other direction works in the same way. `ipsec-rtr2` sees the route `172.20.1.1/32` with the AS path `65001 65250`. The provider AS (65001) is in the path. The customer AS (65250) is the origin.

#### 5.8.5 How routes move between the VRF and VPNv4

A PE uses two BGP address families for the customer service. One faces the CE. The other faces the other PE. The VRF definition connects them. No `redistribute` command and no route map move the routes. The RD and the route targets of the VRF control the movement.

| Part | Configuration | Faces | Carries |
|---|---|---|---|
| VRF IPv4 address family | `address-family ipv4 vrf CE-RTR1` under `router bgp 65001` | The CE (eBGP, `10.1.1.1` on `pe-rtr-1`) | Plain IPv4 prefixes of the customer |
| VPNv4 address family | `address-family vpnv4` under `router bgp 65001` | The other PE (iBGP, `2001:DB8:FFFF::2` on `pe-rtr-1`) | VPNv4 prefixes (RD plus IPv4 prefix), route targets, and the `uDT4` SID |
| VRF definition | `vrf definition CE-RTR1` with `rd`, `route-target export`, `route-target import` | No neighbor | The rules that move routes between the two address families |

Two terms describe the movement:

- **Export** moves a route from the VRF IPv4 address family to VPNv4. The PE that learns the route from its CE does this.
- **Import** moves a route from VPNv4 to the VRF IPv4 address family. The PE that receives the route from the other PE does this.

**The VRF view.** The command `show bgp vpnv4 unicast vrf CE-RTR1` shows the routes of the VRF. It shows the routes from the CE and the routes that the PE imported. Observed on `pe-rtr-1`:

```
pe-rtr-1#show bgp vpnv4 unicast vrf CE-RTR1
Route Distinguisher: 65001:1 (default for vrf CE-RTR1)
 *>   172.20.1.1/32    10.1.1.1                 0             0 65250 i
 *>i  172.21.1.1/32    2001:DB8:FFFF::2
```

The first route came from the CE. The PE exports it. The second route came from the other PE (the letter `i` means iBGP). The PE imported it. Both PE routers use RD 65001:1, so both routes show under the same RD. Concept: if the PE routers use different RD values, an imported route keeps the RD of the PE that exported it. The VRF routing table uses only the IPv4 prefix.

##### Export: VRF IPv4 to VPNv4

The route is `172.20.1.1/32` (the loopback of `ipsec-rtr1`). `pe-rtr-1` exports it.

| Step | Action of the PE | Observed |
|---|---|---|
| 1 | Receive the route from the CE with eBGP. Put it in the BGP table of the VRF. | `show bgp vpnv4 unicast all 172.20.1.1/32` shows `10.1.1.1 (via vrf CE-RTR1) from 10.1.1.1` and `external`. |
| 2 | Add the RD. The IPv4 prefix becomes a VPNv4 prefix. | The entry name is `65001:1:172.20.1.1/32`. |
| 3 | Add the export route target. The CE did not send it. | `Extended Community: RT:65001:1` |
| 4 | Add the service identifier of the VRF: the `uDT4` SID of the VRF (`FCBB:BB00:1:E002::`). | `srv6 in-sid: FCBB:BB00:1:E002::` |
| 5 | Send the route to the VPNv4 neighbor. | `show bgp vpnv4 unicast all neighbors 2001:DB8:FFFF::2 advertised-routes` lists one prefix: `172.20.1.1/32`. |
| 6 | Set the BGP next hop to the own loopback in the update. | `pe-rtr-2` receives the next hop `2001:DB8:FFFF::1`. The local view of the advertised route still shows the CE address `10.1.1.1`. |
| 7 | Keep the AS path. iBGP adds no AS number. | The path is `65250`. |

##### Import: VPNv4 to VRF IPv4

The route is the same route, `172.20.1.1/32`. `pe-rtr-2` imports it.

| Step | Action of the PE | Observed |
|---|---|---|
| 1 | Receive the VPNv4 update from the iBGP neighbor. | `show bgp vpnv4 unicast all neighbors 2001:DB8:FFFF::1 routes` on `pe-rtr-2` lists `172.20.1.1/32`. |
| 2 | Check that the BGP next hop is reachable in the IGP. | `2001:DB8:FFFF::1 (metric 40)` |
| 3 | Compare the route targets in the update with the import route targets of the VRFs. One match is enough. | The update has `RT:65001:1`. The VRF `CE-RTR1` imports `RT:65001:1`. The route is imported. |
| 4 | Discard the route if no VRF matches. | Not seen in the normal state. See the export exercise below: the neighbor shows `Total number of prefixes 0`. |
| 5 | Use the IPv4 prefix in the VRF. The RD is not used in the VRF routing table. | The route table shows `172.20.1.1`. |
| 6 | Keep the `uDT4` SID for forwarding. | `srv6 out-sid: FCBB:BB00:1:E002::` |
| 7 | Select the best path. Install it in the VRF routing table. | `B 172.20.1.1 [200/0] via FCBB:BB00:1:E002:: (default:ipv6)` (distance 200 means iBGP) |
| 8 | Advertise the route to the CE with eBGP. Add the AS 65001. Set the next hop to the PE address on the PE-CE link. Do not send the route target. | `ipsec-rtr2` shows `172.20.1.1/32` with next hop `10.2.2.2` and path `65001 65250`. The entry has no route target. |

The command `show bgp vpnv4 unicast vrf CE-RTR1 neighbors 10.2.2.1 advertised-routes` on `pe-rtr-2` shows the route that the PE sends to the CE. The output shows the route before the outbound changes. It still has the next hop `2001:DB8:FFFF::1` and the path `65250`. The CE receives the next hop `10.2.2.2` and the path `65001 65250`.

##### The same route, step by step

Observed values for `172.20.1.1/32`, from `ipsec-rtr1` to `ipsec-rtr2`:

| Point | Prefix | RD | Route target | Next hop | AS path | SID |
|---|---|---|---|---|---|---|
| `ipsec-rtr1` sends | `172.20.1.1/32` | none | none | `10.1.1.1` | `65250` | none |
| `pe-rtr-1` VRF table (from the CE) | `172.20.1.1/32` | none | none | `10.1.1.1` | `65250` | none |
| `pe-rtr-1` VPNv4 table (after export) | `65001:1:172.20.1.1/32` | `65001:1` | `RT:65001:1` (added) | `10.1.1.1` in the local view. `2001:DB8:FFFF::1` in the update. | `65250` | `srv6 in-sid FCBB:BB00:1:E002::` |
| `pe-rtr-2` VPNv4 table (received) | `65001:1:172.20.1.1/32` | `65001:1` | `RT:65001:1` | `2001:DB8:FFFF::1` | `65250` | `srv6 out-sid FCBB:BB00:1:E002::` |
| `pe-rtr-2` VRF routing table (after import) | `172.20.1.1/32` | not used | not used | `FCBB:BB00:1:E002::` | `65250` | used for forwarding |
| `ipsec-rtr2` receives | `172.20.1.1/32` | none | none | `10.2.2.2` | `65001 65250` | none |

Read the table from top to bottom. The RD and the route target exist only between the two PE routers. The CE routers see plain IPv4 routes.

##### Rules

| Rule | Observed or concept |
|---|---|
| Export takes the routes that the CE sent. A route that the PE imported is not exported again. | Observed: `neighbors 2001:DB8:FFFF::2 advertised-routes` on `pe-rtr-1` lists only `172.20.1.1/32`. The imported route `172.21.1.1/32` is not in the list. |
| A route is imported when at least one route target in the update matches at least one import route target of the VRF. | Concept. The VRF can have many `route-target import` lines. |
| A route carries all export route targets of the VRF. | Concept. The VRF can have many `route-target export` lines. |
| Export and import are separate. The export route target is what the other PE sees. The import route target is what this PE accepts. | Observed in the two exercises (import: section 5.8.7, export: below). |
| The RD does not decide the import. It only makes the prefix unique in VPNv4. | Concept. IOS also refuses a direct RD change. The message is `Do "no rd 65001:1" first, in "vrf CE-RTR1" submode, before redefining the RD for the VRF`. The lab does not test this change, because `no rd` removes the VRF from VPNv4. |
| A route imported from an iBGP neighbor goes to the eBGP CE. | Observed on `ipsec-rtr2`: it has the route `172.20.1.1/32` from `pe-rtr-2`. |
| The route target does not go to the CE. | Observed: the entry on `ipsec-rtr2` has no extended community. |

Concept: the RT values set the shape of the VPN.

| Pattern | Export RT | Import RT | Result |
|---|---|---|---|
| Any-to-any (this lab) | One value, `65001:1` | The same value, `65001:1` | Every site reaches every site |
| Hub and spoke | Hub: `HUB`. Spokes: `SPOKE`. | Hub: `SPOKE`. Spokes: `HUB`. | Spokes reach only the hub |
| Shared service | Site: own RT. Service site: `SERVICE`. | Site: own RT and `SERVICE`. Service site: all site RTs. | All sites reach the service site |

##### Commands for each step

| Step | Command | Node |
|---|---|---|
| Route from the CE in the VRF | `show bgp vpnv4 unicast vrf CE-RTR1 neighbors 10.1.1.1 routes` | `pe-rtr-1` |
| Route with RD, RT, and SID after export | `show bgp vpnv4 unicast all 172.20.1.1/32` | `pe-rtr-1` |
| Routes sent to the other PE (export) | `show bgp vpnv4 unicast all neighbors 2001:DB8:FFFF::2 advertised-routes` | `pe-rtr-1` |
| Routes received from the other PE (before import) | `show bgp vpnv4 unicast all neighbors 2001:DB8:FFFF::1 routes` | `pe-rtr-2` |
| Route imported into the VRF | `show bgp vpnv4 unicast vrf CE-RTR1` and `show ip route vrf CE-RTR1 bgp` | `pe-rtr-2` |
| Route sent to the CE | `show bgp vpnv4 unicast vrf CE-RTR1 neighbors 10.2.2.1 advertised-routes` | `pe-rtr-2` |
| Route received by the CE | `show ip bgp` | `ipsec-rtr2` |
| Route targets of the VRF | `show ip vrf detail CE-RTR1` | Both PE routers |

##### Exercise: break the export route target

The exercise in section 5.8.7 breaks the import side. This exercise breaks the export side. It uses `pe-rtr-2`, which exports `172.21.1.1/32`. The restore steps give back the original configuration.

**Step 1.** Change the export RT of `pe-rtr-2`:

```
pe-rtr-2# configure terminal
pe-rtr-2(config)# vrf definition CE-RTR1
pe-rtr-2(config-vrf)# no route-target export 65001:1
pe-rtr-2(config-vrf)# route-target export 65001:2
pe-rtr-2(config-vrf)# end
```

**Step 2.** Wait 20 seconds. Check `pe-rtr-2` and `pe-rtr-1`.

Observed (the result is the same in `lab-srv6` and `lab-sr-mpls`):

| Check | Before | After |
|---|---|---|
| `pe-rtr-2`: `show bgp vpnv4 unicast vrf CE-RTR1` | Both routes | Both routes (the import side of `pe-rtr-2` is not changed) |
| `pe-rtr-1`: `show bgp vpnv4 unicast all` | `172.20.1.1/32` and `172.21.1.1/32` | Only `172.20.1.1/32` |
| `pe-rtr-1`: `neighbors 2001:DB8:FFFF::2 routes` | 1 prefix | `Total number of prefixes 0` |
| `pe-rtr-1`: `show ip route vrf CE-RTR1 bgp` | Two BGP routes | Only `172.20.1.1` (from the CE) |
| `ping 172.21.1.1 source 172.20.1.1` on `ipsec-rtr1` | 100 percent | 0 percent |

`pe-rtr-2` still sends the route. The update now has `RT:65001:2`. `pe-rtr-1` imports only `RT:65001:1`. No VRF on `pe-rtr-1` accepts the update, so `pe-rtr-1` does not keep the route. The BGP session stays up.

**Step 3.** Restore the configuration:

```
pe-rtr-2# configure terminal
pe-rtr-2(config)# vrf definition CE-RTR1
pe-rtr-2(config-vrf)# no route-target export 65001:2
pe-rtr-2(config-vrf)# route-target export 65001:1
pe-rtr-2(config-vrf)# end
```

**Step 4.** Wait 25 seconds. Check that `show ip route vrf CE-RTR1 bgp` on `pe-rtr-1` has the route `172.21.1.1` and that the ping works.

Use the two exercises together to find the fault. If the route is missing on the receiving PE, check the export RT on the sending PE and the import RT on the receiving PE. The command `neighbors <peer> routes` on the receiving PE tells you if the update was accepted.

#### 5.8.6 Read one VPNv4 route

Observed on `pe-rtr-1`:

```
pe-rtr-1#show bgp vpnv4 unicast vrf CE-RTR1 172.21.1.1/32
BGP routing table entry for 65001:1:172.21.1.1/32, version 5
Paths: (1 available, best #1, table CE-RTR1)
  65351
    2001:DB8:FFFF::2 (metric 40) (via default) from 2001:DB8:FFFF::2 (10.0.0.2)
      Origin IGP, metric 0, localpref 100, valid, internal, best
      Extended Community: RT:65001:1
      srv6 out-sid: FCBB:BB00:2:E002::
```

| Field | Value | Meaning |
|---|---|---|
| Entry name | `65001:1:172.21.1.1/32` | RD plus prefix. This is the VPNv4 prefix. |
| `table CE-RTR1` | VRF name | The router imported the route into this VRF. |
| Path `65351` | AS path | The AS of `ipsec-rtr2`. The PE routers are in the same AS, so iBGP adds nothing. |
| `2001:DB8:FFFF::2` | BGP next hop | The IPv6 loopback of `pe-rtr-2`. It is an IPv6 next hop for an IPv4 prefix. |
| `(metric 40)` | IGP cost to the next hop | IS-IS cost to `2001:DB8:FFFF::2/128`: 30 for the path plus 10 for the loopback. |
| `internal` | iBGP | The route came from a PE in the same AS. |
| `RT:65001:1` | Route target | The value that the import RT of the VRF must match. |
| `srv6 out-sid` | `FCBB:BB00:2:E002::` | The `uDT4` SID of `pe-rtr-2`. `pe-rtr-1` puts it in the destination address. |

The BGP next hop and the SID have different jobs. The next hop must be reachable in IS-IS (BGP checks it). The forwarding table uses the SID and the locator route `FCBB:BB00:2::/48`.

#### 5.8.7 Exercise: break the route target

This exercise shows how the RT controls the service. It uses `pe-rtr-1`. The exercise is safe. The restore steps give back the original configuration.

**Step 1.** Change the import RT so that it does not match the RT in the update:

```
pe-rtr-1# configure terminal
pe-rtr-1(config)# vrf definition CE-RTR1
pe-rtr-1(config-vrf)# no route-target import 65001:1
pe-rtr-1(config-vrf)# route-target import 65001:2
pe-rtr-1(config-vrf)# end
```

**Step 2.** Wait 15 seconds. Check the tables.

Observed:

| Check | Before | After |
|---|---|---|
| `show ip vrf detail CE-RTR1` | Import `RT:65001:1` | Import `RT:65001:2` |
| `show bgp vpnv4 unicast all` | Has `172.20.1.1/32` and `172.21.1.1/32` | Has only `172.20.1.1/32` |
| `show bgp vpnv4 unicast all 172.21.1.1/32` | The route with the SID | `% Network not in table` |
| `show ip route vrf CE-RTR1 bgp` | Two BGP routes | Only `172.20.1.1` (from the CE) |
| `ping 172.21.1.1 source 172.20.1.1` on `ipsec-rtr1` | 100 percent | 0 percent |

The BGP session stays up. The PE receives the update, and no local VRF imports it (the RT does not match). The PE does not keep the route. The customer loses the service, and the IPsec tunnel is down.

**Step 3.** Restore the configuration:

```
pe-rtr-1# configure terminal
pe-rtr-1(config)# vrf definition CE-RTR1
pe-rtr-1(config-vrf)# no route-target import 65001:2
pe-rtr-1(config-vrf)# route-target import 65001:1
pe-rtr-1(config-vrf)# end
```

**Step 4.** Wait 20 seconds. Check that the route `B 172.21.1.1 [200/0] via FCBB:BB00:2:E002::` is in `show ip route vrf CE-RTR1 bgp` and that the ping works.

Use this exercise to learn the symptom. The remote route is missing from the VRF, the BGP session is up, and the core is fine. Check the RT first.

#### 5.8.8 Lookups on each device

| Device | Lookup | Result |
|---|---|---|
| `ipsec-rtr1` | IPv4 route to `172.21.1.1` | eBGP route, next hop `10.1.1.2` |
| `pe-rtr-1` | 1. VRF `CE-RTR1` route to `172.21.1.1` | VPN SID `FCBB:BB00:2:E002::`. The PE encapsulates the packet. |
| `pe-rtr-1` | 2. IPv6 route to `FCBB:BB00:2:E002::` | Locator route `FCBB:BB00:2::/48`. Two ECMP next hops. |
| P router | IPv6 route to `FCBB:BB00:2:E002::` | Locator route `FCBB:BB00:2::/48`. The router does not open the inner packet. |
| `pe-rtr-2` | 1. Local SID table | Match: `FCBB:BB00:2:E002::` is `uDT4`. The PE removes the IPv6 header. |
| `pe-rtr-2` | 2. VRF `CE-RTR1` route to `172.21.1.1` | eBGP route, next hop `10.2.2.1` |
| `ipsec-rtr2` | Local address | The packet is for `Loopback100`. The CE processes the ESP packet. |

Section 7 and section 8 give the header details and the packet captures.

#### 5.8.9 Design points

- **The CE routers use different AS numbers.** `ipsec-rtr1` is AS 65250 and `ipsec-rtr2` is AS 65351. Concept: if both CE routers used the same AS, each CE would reject the remote route. The BGP loop check finds the own AS in the AS path. To fix this, use `neighbor <CE> as-override` on the PE, or `neighbor <PE> allowas-in` on the CE.
- **The PE routers use one AS (65001).** This makes an iBGP session between them. The routes from the remote PE are not advertised to a third PE. Concept: with more than two PE routers, use a full mesh or a route reflector.
- **`send-community extended` is required.** Without it, the update has no RT. The remote PE then cannot import the route. Concept.
- **The customer announces only the loopbacks.** The provider does not learn `192.168.1.0/24` or `192.168.2.0/24`. The customer uses static routes to `Tunnel100` for the LANs.
- **The provider prefixes do not go to the CE.** Observed: the route table of `ipsec-rtr1` has no `10.0.0.x` route (the IPv4 loopbacks of the provider).
- **Each PE makes its own SID.** `pe-rtr-1` uses `FCBB:BB00:2:E002::` to send to site 2. `pe-rtr-2` uses `FCBB:BB00:1:E002::` to send to site 1. The function value `E002` is the same on both PE routers because each PE allocates from its own locator in the same order.
- **The BGP next hop is an IPv6 address.** The IPv4 customer prefix has an IPv6 next hop. If IS-IS has no route to `2001:DB8:FFFF::2`, the route is not valid.

#### 5.8.10 Where to check the service

| Question | Command | Node | Section |
|---|---|---|---|
| Is the PE-CE session up? | `show ip bgp summary` | CE | 9.9 |
| Does the PE receive the customer prefix? | `show ip route vrf CE-RTR1 bgp` | PE | 9.8 |
| Is the VPNv4 session up? | `show bgp vpnv4 unicast all summary` | PE | 9.6 |
| Does the route have RD, RT, and SID? | `show bgp vpnv4 unicast all <prefix>` | PE | 9.7 |
| Do the RT values match? | `show ip vrf detail CE-RTR1` | PE | 5.8.7 |
| Did the PE export the route? | `show bgp vpnv4 unicast all neighbors 2001:DB8:FFFF::2 advertised-routes` | Sending PE | 5.8.5 |
| Did the PE accept the route (import)? | `show bgp vpnv4 unicast all neighbors 2001:DB8:FFFF::1 routes` | Receiving PE | 5.8.5 |
| Does the FIB encapsulate? | `show ip cef vrf CE-RTR1 <prefix> detail` | PE | 9.8 |

## 6. Configuration explained

The configurations are in `configs/`. `gen_configs.py` makes them. Each block below has the code and the explanation. The examples use `pe-rtr-1` and `ipsec-rtr1`.

### 6.1 Management block (all nodes)

```
username admin privilege 15 secret admin
ip domain name lab.local
ip ssh version 2
crypto key generate rsa modulus 2048
interface Ethernet0/0
 ip address 172.100.210.13 255.255.255.0
 no shutdown
line vty 0 4
 login local
 transport input ssh
```

This block gives SSH access. The lab needs a domain name and an RSA key to start the SSH server.

### 6.2 PE: VRF

```
vrf definition CE-RTR1
 rd 65001:1
 route-target export 65001:1
 route-target import 65001:1
 address-family ipv4
 exit-address-family
```

| Line | Explanation |
|---|---|
| `rd 65001:1` | Makes the customer prefix unique in VPNv4 |
| `route-target export/import` | Controls which routes go to and come from other PE routers |
| `address-family ipv4` | Turns on IPv4 in the VRF |

### 6.3 PE: loopback and core interfaces

```
interface Loopback0
 ip address 10.0.0.1 255.255.255.255
 ipv6 address 2001:DB8:FFFF::1/128
 ipv6 router isis 1
 ip router isis 1
!
interface Ethernet0/2
 no ip address
 ipv6 enable
 ipv6 router isis 1
 isis network point-to-point
 no shutdown
```

| Line | Explanation |
|---|---|
| `ipv6 address 2001:DB8:FFFF::1/128` | Global IPv6 address for BGP and SRv6 |
| `ipv6 router isis 1` | Puts the interface in IS-IS for IPv6 |
| `ip router isis 1` | Also advertises the IPv4 loopback in IS-IS. The core does not use IPv4 to forward traffic. |
| `ipv6 enable` | Makes the link-local address. The link has no global address. |
| `isis network point-to-point` | Uses the point-to-point IS-IS hello. No DIS election. |

### 6.4 PE and P: IS-IS

```
router isis 1
 net 49.0001.0000.0000.0001.00
 is-type level-2-only
 metric-style wide
 router-id Loopback0
 address-family ipv6
  multi-topology
  segment-routing srv6
   locator LOC1
  exit-address-family
```

| Line | Explanation |
|---|---|
| `net ...` | IS-IS address. `0000.0000.0001` is the system ID. |
| `multi-topology` | IS-IS keeps a separate IPv6 topology (MT-IPv6). The LSP output shows `MT-IPv6`. |
| `segment-routing srv6` / `locator LOC1` | Tells IS-IS to advertise the locator `LOC1` in its LSP |

### 6.5 PE and P: SRv6 locator

```
segment-routing srv6
 encapsulation
  source-address 2001:DB8:FFFF::1
 locators
  locator LOC1
   prefix FCBB:BB00:1::/48
   format usid-f3216
```

| Line | Explanation |
|---|---|
| `source-address` | Source IPv6 address of the outer header when this router encapsulates |
| `locator LOC1` | Name of the locator |
| `prefix FCBB:BB00:1::/48` | Block `FCBB:BB00` plus node `0001` |
| `format usid-f3216` | uSID format: block 32 bits, node 16 bits (F3216 = format 32-16) |

### 6.6 PE: CE-facing interface

```
interface Ethernet0/1
 vrf forwarding CE-RTR1
 ip address 10.1.1.2 255.255.255.252
 no shutdown
```

`vrf forwarding` puts the interface in the customer VRF. Enter it before the IP address, because the command removes an existing address.

### 6.7 PE: BGP

```
router bgp 65001
 bgp router-id 10.0.0.1
 no bgp default ipv4-unicast
 neighbor 2001:DB8:FFFF::2 remote-as 65001
 neighbor 2001:DB8:FFFF::2 update-source Loopback0
 address-family vpnv4
  neighbor 2001:DB8:FFFF::2 activate
  neighbor 2001:DB8:FFFF::2 send-community extended
 address-family ipv4 vrf CE-RTR1
  neighbor 10.1.1.1 remote-as 65250
  neighbor 10.1.1.1 activate
  segment-routing srv6
   locator LOC1
   alloc-mode per-vrf
```

| Line | Explanation |
|---|---|
| `neighbor 2001:DB8:FFFF::2 ...` | iBGP to the other PE, over the IPv6 loopback |
| `address-family vpnv4` | The session carries VPNv4 routes |
| `send-community extended` | Sends the route target |
| `address-family ipv4 vrf CE-RTR1` | Runs the eBGP session to the CE inside the VRF |
| `segment-routing srv6` / `locator LOC1` | Uses `LOC1` to make the VRF SID |
| `alloc-mode per-vrf` | One SID for the whole VRF |

Note: the keyword is `alloc-mode` with a hyphen. The form `alloc mode` is not valid in this image.

### 6.7.1 P router

A P router has the same core configuration as a PE. It has no VRF, no BGP, and no CE-facing interface. It has three core interfaces.

### 6.8 CE: IPsec and tunnel

```
crypto isakmp policy 10
 encryption aes 256
 hash sha256
 authentication pre-share
 group 14
crypto isakmp key srv6-lab-psk address 172.21.1.1
crypto ipsec transform-set TS esp-aes 256 esp-sha256-hmac
 mode tunnel
crypto ipsec profile IPSEC-PROF
 set transform-set TS
interface Loopback100
 ip address 172.20.1.1 255.255.255.255
interface Tunnel100
 ip address 172.30.1.1 255.255.255.252
 tunnel source Loopback100
 tunnel destination 172.21.1.1
 tunnel protection ipsec profile IPSEC-PROF
 ip tcp adjust-mss 1360
```

| Line | Explanation |
|---|---|
| `crypto isakmp policy 10` | IKE phase 1 parameters |
| `crypto isakmp key ... address 172.21.1.1` | Pre-shared key for the peer loopback |
| `crypto ipsec transform-set TS` | ESP with AES-256 and SHA-256 |
| `crypto ipsec profile IPSEC-PROF` | Links the transform set to the tunnel |
| `tunnel source/destination` | The two loopbacks. The provider network must route between them. |
| `tunnel protection ipsec profile` | Encrypts the GRE packets |
| `ip tcp adjust-mss 1360` | Reduces the TCP segment size. IOL does not let you change the interface MTU. |

### 6.9 CE: eBGP and routes

```
interface Ethernet0/1
 ip address 10.1.1.1 255.255.255.252
interface Ethernet0/2
 ip address 192.168.1.1 255.255.255.0
router bgp 65250
 bgp router-id 172.20.1.1
 neighbor 10.1.1.2 remote-as 65001
 address-family ipv4
  network 172.20.1.1 mask 255.255.255.255
  neighbor 10.1.1.2 activate
ip route 192.168.2.0 255.255.255.0 Tunnel100
```

| Line | Explanation |
|---|---|
| `neighbor 10.1.1.2 remote-as 65001` | eBGP to the PE |
| `network 172.20.1.1 mask 255.255.255.255` | Announces the tunnel source to the provider |
| `ip route 192.168.2.0 ... Tunnel100` | Sends the remote LAN into the tunnel |

### 6.10 Host

```
vrf definition MGMT
interface Ethernet0/0
 vrf forwarding MGMT
 ip address 172.100.210.11 255.255.255.0
interface Ethernet0/1
 ip address 192.168.1.10 255.255.255.0
ip route 0.0.0.0 0.0.0.0 192.168.1.1
```

### 6.11 Differences between the nodes

| Item | Value that changes |
|---|---|
| Mgmt IP | `172.100.210.<11..20>` |
| Loopback and NET | Node number `<n>` (section 4) |
| Locator | `FCBB:BB00:<n>::/48` |
| PE-CE subnet and AS | Site 1: `10.1.1/30`, AS 65250. Site 2: `10.2.2/30`, AS 65351. |
| BGP neighbor of the PE | The other PE loopback |
| P interfaces | `Ethernet0/1`, `0/2`, `0/3` (all core) |
| PE interfaces | `Ethernet0/1` (CE), `0/2` and `0/3` (core) |

## 7. Forwarding model

### 7.1 Route to SID: how the PE chooses the encapsulation

Observed on `pe-rtr-1`:

```
pe-rtr-1#show ip route vrf CE-RTR1 bgp
B   172.20.1.1 [20/0]  via 10.1.1.1
B   172.21.1.1 [200/0] via FCBB:BB00:2:E002:: (default:ipv6)

pe-rtr-1#show ip cef vrf CE-RTR1 172.21.1.1/32 detail
  Path: v4-rcrsv-FCBB:BB00:2:E002:: (VPN-SID: FCBB:BB00:2:E002::)
    IPv6 TC: 0   Flow Label: 0   Hop Limit: 64
      Src: 2001:DB8:FFFF::1
      Dst: FCBB:BB00:2:E002::
    Segment List (1) mode:combine
      FCBB:BB00:2:E002::
  recursive via FCBB:BB00:2:E002::
    recursive via FCBB:BB00:2::/48
      nexthop FE80::A8BB:CCFF:FE00:110 Ethernet0/2
      nexthop FE80::A8BB:CCFF:FE00:310 Ethernet0/3
```

The output has three levels of lookup:

1. The customer prefix `172.21.1.1/32` points to the VPN SID `FCBB:BB00:2:E002::`.
2. The VPN SID points to the locator route `FCBB:BB00:2::/48`. IS-IS made this route.
3. The locator route has two next hops (ECMP): `Ethernet0/2` to P1 and `Ethernet0/3` to P3.

The "Segment List (1)" line shows one segment. The router puts this segment in the destination address of the outer header. The router adds no SRH. The packet captures confirm this: the IPv6 next header is 4 (IPv4-in-IPv6), not 43 (SRH). This is the reduced encapsulation behavior (`H.Encaps.Red`, RFC 8986).

### 7.2 Outer header

The PE adds this IPv6 header to the customer packet:

| Field | Value | Source |
|---|---|---|
| Source address | `2001:DB8:FFFF::1` | `segment-routing srv6` > `encapsulation` > `source-address` |
| Destination address | `FCBB:BB00:2:E002::` | The VPN SID from BGP |
| Next header | 4 (IPv4) | The payload is an IPv4 packet |
| Hop limit | 64 | Default |
| Flow label | 0 | Shown in the CEF output |
| Extension headers | none | One segment only |

### 7.3 What the P routers do

A P router does not process the SID. The destination address `FCBB:BB00:2:E002::` is not a SID of the P router. The P router does a normal longest-prefix match. The match is the IS-IS route `FCBB:BB00:2::/48`. It decrements the hop limit and forwards the packet.

Observed on `core-p-rtr-1`:

```
core-p-rtr-1#show ipv6 route FCBB:BB00:2:E002::
Routing entry for FCBB:BB00:2::/48
  Known via "isis 1", distance 115, metric 20, type level-2
    FE80::A8BB:CCFF:FE00:210, Ethernet0/2
    FE80::A8BB:CCFF:FE00:420, Ethernet0/3
```

A P router keeps no customer state. It needs no VRF, no BGP, and no MPLS label.

### 7.4 What the egress PE does

The destination address of the packet matches a local SID of `pe-rtr-2`: the `uDT4` SID `FCBB:BB00:2:E002::`. The router does these steps:

1. Remove the outer IPv6 header.
2. Look up the inner IPv4 destination in VRF `CE-RTR1`.
3. Forward the packet to the CE (`10.2.2.1` on `Ethernet0/1`).

Observed on `pe-rtr-2`: the route `172.21.1.1/32` in the VRF points to `10.2.2.1` on `Ethernet0/1`.

### 7.5 Concept: a uSID list with more than one uSID

This lab does not use this function. It is important to know for SRv6 uSID.

The packet carrier is a 128-bit destination address. It has the block and up to six 16-bit uSIDs. To go through P3 and P2 to reach the `uDT4` of PE2, a sender can use this destination address:

```
FCBB:BB00 : 0013 : 0012 : 0002 : E002 : 0000 : 0000
 block      P3     P2     PE2    DT4    (end of list)
```

Each `uN` router does the same steps:

1. The destination address matches the local `uN` locator (`FCBB:BB00:13::/48` for P3).
2. The router shifts the uSIDs 16 bits to the left. The block stays.
3. The router forwards the packet to the new destination `FCBB:BB00:12:2:E002::`.

In this lab, the shortest path is enough. The destination address has only the `uDT4` SID. The header does not change in the core.

## 8. Packet walk

### 8.1 Test flow

`host1` sends an ICMP echo request to `host2`:

```
host1# ping 192.168.2.10
```

The capture tool is `tcpdump` in the container `wbitt/network-multitool`. Each capture uses the network namespace of the node. See section 9.2.

The tables below use one real test. The path can be different in your test (section 3.4).

### 8.2 Forward direction: host1 to host2

Observed path: `host1` > `ipsec-rtr1` > `pe-rtr-1` > `core-p-rtr-3` > `core-p-rtr-2` > `pe-rtr-2` > `ipsec-rtr2` > `host2`.

| Step | Where | What happens | Packet on the wire after this step |
|---|---|---|---|
| 1 | `host1` Et0/1 | The host uses its default route. It sends the packet to the CE. | IPv4 `192.168.1.10 > 192.168.2.10`, ICMP echo request, TTL 255 |
| 2 | `ipsec-rtr1` | The CE looks up `192.168.2.10`. The static route points to `Tunnel100`. The CE decrements the TTL. It adds a GRE header. IPsec then encrypts the GRE packet in ESP. | IPv4 `172.20.1.1 > 172.21.1.1`, protocol 50 (ESP), TTL 255, IP length 188 |
| 3 | `ipsec-rtr1` Et0/1 to `pe-rtr-1` Et0/1 | The CE uses its BGP route to `172.21.1.1` (next hop `10.1.1.2`). The ESP packet leaves on the PE-CE link. | Same as step 2 |
| 4 | `pe-rtr-1` | The packet arrives in VRF `CE-RTR1`. The PE decrements the IPv4 TTL. It finds the route with the VPN SID. It adds the outer IPv6 header. It chooses `Ethernet0/3` (ECMP). | IPv6 `2001:DB8:FFFF::1 > FCBB:BB00:2:E002::`, next header 4, hop limit 64, inner IPv4 TTL 254, IPv6 payload length 188 |
| 5 | `core-p-rtr-3` | The P router matches `FCBB:BB00:2::/48`. It decrements the hop limit. It chooses `Ethernet0/3` (ECMP). | Same, hop limit 63 |
| 6 | `core-p-rtr-2` | The P router matches `FCBB:BB00:2::/48`. It decrements the hop limit. It sends the packet on `Ethernet0/3`. | Same, hop limit 62 |
| 7 | `pe-rtr-2` | The destination matches the local SID `FCBB:BB00:2:E002::` (`uDT4`). The PE removes the IPv6 header. It looks up `172.21.1.1` in VRF `CE-RTR1`. It sends the packet to the CE. | IPv4 `172.20.1.1 > 172.21.1.1`, ESP, TTL 254 (the PE does not change it) |
| 8 | `ipsec-rtr2` | The CE decrypts the ESP packet. It removes the GRE header. The packet arrives on `Tunnel100`. The CE looks up `192.168.2.10`. It decrements the TTL and sends the packet to the LAN. | IPv4 `192.168.1.10 > 192.168.2.10`, ICMP echo request, TTL 253 |
| 9 | `host2` | The host receives the echo request. It sends an echo reply. | |

Numbers that show the header size:

- The IPv4 ESP packet has 188 bytes (steps 2, 3, 7).
- The SRv6 packet has 228 bytes: 40 bytes for the outer IPv6 header plus 188 bytes (steps 4 to 6).
- Each customer packet has a 100-byte IPv4 packet at the start (a ping with 100 bytes).

Two TTL facts:

- The IPv4 TTL of the ESP packet is 254 in the core. It does not change between `pe-rtr-1` and `pe-rtr-2`. Only the IPv6 hop limit changes in the core (64, 63, 62).
- The hop limit (not the IPv4 TTL) is what a `traceroute` in the core would show. The customer traceroute does not show the core routers. The customer sees `192.168.1.1` and then `172.30.1.2` and then `192.168.2.10`.

### 8.3 Return direction: host2 to host1

The return packet follows the same steps in reverse. The core path can be different because each router uses its own hash. Observed return path: `pe-rtr-2` > `core-p-rtr-2` > `core-p-rtr-1` > `pe-rtr-1`.

| Step | Where | Packet |
|---|---|---|
| 1 | `host2` to `ipsec-rtr2` | IPv4 `192.168.2.10 > 192.168.1.10`, ICMP echo reply |
| 2 | `ipsec-rtr2` to `pe-rtr-2` | IPv4 `172.21.1.1 > 172.20.1.1`, ESP, TTL 255 |
| 3 | `pe-rtr-2` (encapsulate) | IPv6 `2001:DB8:FFFF::2 > FCBB:BB00:1:E002::`, next header 4, hop limit 64, inner TTL 254 |
| 4 | `core-p-rtr-2` | Same, hop limit 63 |
| 5 | `core-p-rtr-1` | Same, hop limit 62 |
| 6 | `pe-rtr-1` (`uDT4` `FCBB:BB00:1:E002::`) | IPv4 `172.21.1.1 > 172.20.1.1`, ESP, TTL 254 |
| 7 | `ipsec-rtr1` | The CE decrypts the packet and sends the echo reply to `host1` |

The two directions use different SPI values. Example: outbound `0xB1808D9D` (CE1 to CE2) and `0x4F9EEBEB` (CE2 to CE1).

### 8.4 Capture evidence (observed)

These lines come from one test on 2026-09-21.

Between `pe-rtr-1` and the CE (ESP, IPv4):

```
IP (ttl 255, proto ESP (50), length 188) 172.20.1.1 > 172.21.1.1: ESP(spi=0xb1808d9d,seq=0xeb)
```

In the core, at `core-p-rtr-3` (ingress from `pe-rtr-1`) and at `core-p-rtr-2` (ingress from `core-p-rtr-3`) and at `pe-rtr-2`:

```
core-p-rtr-3  eth1  IP6 (hlim 64, next-header IPIP (4) payload length: 188) 2001:db8:ffff::1 > fcbb:bb00:2:e002::: IP (ttl 254, proto ESP (50), length 188) 172.20.1.1 > 172.21.1.1: ESP(spi=0xb1808d9d,seq=0xeb)
core-p-rtr-2  eth2  IP6 (hlim 63, next-header IPIP (4) payload length: 188) 2001:db8:ffff::1 > fcbb:bb00:2:e002::: IP (ttl 254, proto ESP (50), length 188) 172.20.1.1 > 172.21.1.1: ESP(spi=0xb1808d9d,seq=0xeb)
pe-rtr-2      eth2  IP6 (hlim 62, next-header IPIP (4) payload length: 188) 2001:db8:ffff::1 > fcbb:bb00:2:e002::: IP (ttl 254, proto ESP (50), length 188) 172.20.1.1 > 172.21.1.1: ESP(spi=0xb1808d9d,seq=0xeb)
```

After the egress PE (IPv4, ESP, TTL 254) and after the CE (plain ICMP, TTL 253):

```
ipsec-rtr2  eth1  IP (ttl 254, proto ESP (50), length 188) 172.20.1.1 > 172.21.1.1: ESP(spi=0xb1808d9d,seq=0xeb)
host2       eth1  IP (ttl 253, proto ICMP (1), length 100) 192.168.1.10 > 192.168.2.10: ICMP echo request
```

`core-p-rtr-4` saw no packet of this flow. `core-p-rtr-1` saw only the return direction.

## 9. Hop-by-hop validation

Use this section to check each part of the design, in order. Each step has a command, the expected result, and the meaning. Log in with `ssh admin@clab-iol-srv6-<node>`.

You can also use the tools in the lab folder:

```
uv run cli.py <node> "<command>" ["<command>" ...]    # run commands on a node
uv run verify.py                                       # run all checks (26 tests)
```

### 9.1 Validation order

Check from the bottom up. If one step fails, stop and fix it before the next step.

| Step | Layer | Question |
|---|---|---|
| 1 | Links | Are the core links up? |
| 2 | IS-IS | Do the routers see each other? |
| 3 | IS-IS routes | Do the routers have the loopback and locator routes? |
| 4 | SRv6 | Does each router own a locator and SIDs? |
| 5 | BGP | Is the VPNv4 session up? |
| 6 | VPN route | Does the PE have the remote route with a SID? |
| 7 | FIB | Does the FIB encapsulate with the correct SID? |
| 8 | PE-CE | Does the CE announce and learn the tunnel loopbacks? |
| 9 | IPsec | Are the security associations up? |
| 10 | End to end | Does the host ping work, and does the packet use the core? |

### 9.2 Packet capture method

The IOL containers do not have `tcpdump`. Attach a helper container to the namespace of a node:

```
docker run --rm --net container:clab-iol-srv6-core-p-rtr-3 --cap-add NET_RAW \
  --entrypoint tcpdump wbitt/network-multitool -i any -nn -e -v -c 5 'ip6 proto 4'
```

| Part | Meaning |
|---|---|
| `--net container:<name>` | Uses the network namespace of the node |
| `-i any` | Captures on all interfaces. The output shows `ethN` for each packet. |
| `ip6 proto 4` | Shows IPv6 packets that carry IPv4 (SRv6 without SRH) |
| `esp` | Filter for ESP packets (IPv4, on the PE-CE links) |
| `icmp` | Filter for the plain ICMP packets on the LAN |
| `-Q in` | Shows only the received packets (one line per hop) |

Start the capture. Then run the ping from `host1`. The `ethN` value is `Ethernet0/N`.

### 9.3 Step 1 and 2: links and IS-IS neighbors

Command on each core node:

```
show isis neighbors
```

Expected: every neighbor has state `UP`, type `L2`. The expected number of neighbors is:

| Node | Neighbors |
|---|---|
| `pe-rtr-1`, `pe-rtr-2` | 2 |
| `core-p-rtr-1..4` | 3 |

Observed on `pe-rtr-1`:

```
System Id       Type Interface     IP Address      State Holdtime Circuit Id
core-p-rtr-1    L2   Et0/2                         UP    25       02
core-p-rtr-3    L2   Et0/3                         UP    28       02
```

The IP Address column is empty. This is correct: the links have no IPv4 address.

Command: `show ipv6 interface brief`. Expected: each core interface has only a `FE80::` address. `Loopback0` has an `FE80::` address and `2001:DB8:FFFF::<n>`.

### 9.4 Step 3: IS-IS routes

Command on `pe-rtr-1`:

```
show ipv6 route isis
```

Expected: one `I2` route for each loopback (`2001:DB8:FFFF::2`, `::11`, `::12`, `::13`, `::14`) and one `I2` route for each remote locator (`FCBB:BB00:2::/48`, `:11::/48`, `:12::/48`, `:13::/48`, `:14::/48`).

Observed:

```
I2  2001:DB8:FFFF::2/128 [115/40]
     via FE80::A8BB:CCFF:FE00:110, Ethernet0/2
     via FE80::A8BB:CCFF:FE00:310, Ethernet0/3
I2  FCBB:BB00:2::/48 [115/30]
     via FE80::A8BB:CCFF:FE00:110, Ethernet0/2
     via FE80::A8BB:CCFF:FE00:310, Ethernet0/3
I2  FCBB:BB00:11::/48 [115/10]
     via FE80::A8BB:CCFF:FE00:110, Ethernet0/2
```

| What to check | Meaning |
|---|---|
| Metric of `FCBB:BB00:2::/48` is 30 | Three links of metric 10 |
| Two next hops | ECMP: P1 and P3 |
| Next hops are `FE80::` addresses | The core works with link-local addresses |
| Metric of the loopback `::2` is 40 | 30 plus the loopback metric 10 |

To see how the locator is in the LSP, use `show isis database detail`. Find the line `SRv6 Locator: (MT-IPv6) FCBB:BB00:<n>::/48`.

### 9.5 Step 4: SRv6 locators and SIDs

Commands on each PE and P node:

```
show segment-routing srv6 locator
show segment-routing srv6 sid
```

Expected for the locator: name `LOC1`, format `usid-f3216`, status `Up`.

Expected for the SID table on `pe-rtr-1`:

```
SID                   Locator  Behavior      Context                                Owner
FCBB:BB00:1::         LOC1     uN (PSP/USD)                                         SID-MGR
FCBB:BB00:1:E000::    LOC1     uA (PSP/USD)  Et0/3 FE80::A8BB:CCFF:FE00:310        router isis 1
FCBB:BB00:1:E001::    LOC1     uA (PSP/USD)  Et0/2 FE80::A8BB:CCFF:FE00:110        router isis 1
FCBB:BB00:1:E002::    LOC1     uDT4          CE-RTR1                                router bgp
```

| What to check | Meaning |
|---|---|
| One `uN` per node | The node SID. Owner is `SID-MGR`. |
| One `uA` per core interface | IS-IS makes the adjacency SIDs. |
| One `uDT4` with context `CE-RTR1` (PE only) | BGP made the VRF SID. If it is missing, check `alloc-mode per-vrf` and the locator. |

A P router has `uN` and `uA` SIDs and no `uDT4`.

### 9.6 Step 5: VPNv4 session

Command on `pe-rtr-1`:

```
show bgp vpnv4 unicast all summary
```

Expected: the neighbor `2001:DB8:FFFF::2` (AS 65001) has a number in the `State/PfxRcd` column (not `Idle` or `Active`). The neighbor `10.1.1.1` (AS 65250) also has a number.

Observed:

```
Neighbor          V   AS    MsgRcvd MsgSent TblVer InQ OutQ Up/Down  State/PfxRcd
10.1.1.1          4  65250  6       5       5      0   0    00:02:43 1
2001:DB8:FFFF::2  4  65001  6       6       5      0   0    00:02:53 1
```

If the IPv6 session does not come up, ping the remote loopback: `ping 2001:DB8:FFFF::2 source Loopback0`. Then check step 3.

### 9.7 Step 6: VPN route with the SID

Command on `pe-rtr-1`:

```
show bgp vpnv4 unicast all
show bgp vpnv4 unicast all 172.21.1.1/32
```

Expected: the route `172.21.1.1/32` has the next hop `2001:DB8:FFFF::2`, the route target `RT:65001:1`, and the line `srv6 out-sid: FCBB:BB00:2:E002::`.

The `out-sid` value must be equal to the `uDT4` SID in the SID table of `pe-rtr-2` (step 4). If the route has no `out-sid`, the remote PE did not allocate a SID. Check the `segment-routing srv6` block in the VRF address family of `pe-rtr-2`.

For the local route, the command `show bgp vpnv4 unicast all 172.20.1.1/32` shows `srv6 in-sid: FCBB:BB00:1:E002::`. The `in-sid` is the SID that the remote PE uses to reach this site.

### 9.8 Step 7: VRF route and FIB

Commands on `pe-rtr-1`:

```
show ip route vrf CE-RTR1 bgp
show ip cef vrf CE-RTR1 172.21.1.1/32 detail
```

Expected in the route table: `B 172.21.1.1 [200/0] via FCBB:BB00:2:E002:: (default:ipv6)`.

Expected in the CEF output:

- `Src: 2001:DB8:FFFF::1` and `Dst: FCBB:BB00:2:E002::` (the outer header)
- `Segment List (1)` with the SID
- `recursive via FCBB:BB00:2::/48` with one next hop for each ECMP path

Then check the P routers. Command on `core-p-rtr-1` and on all other P routers:

```
show ipv6 route FCBB:BB00:2:E002::
```

Expected: the entry is `FCBB:BB00:2::/48` (the locator, not a host route), source `isis 1`. Each P router has the same answer for the locator.

### 9.9 Step 8: PE-CE routing

Commands on `ipsec-rtr1`:

```
show ip bgp summary
show ip route 172.21.1.1
ping 172.21.1.1 source 172.20.1.1
```

Expected:

- The neighbor `10.1.1.2` (AS 65001) is established.
- The route `172.21.1.1/32` is a BGP route through `10.1.1.2`.
- The ping has a success rate of 100 percent. This ping crosses the SRv6 core without IPsec.

This ping is the first end-to-end test. It proves that the VPN carries the traffic between the two loopbacks. Do this test before you check IPsec.

### 9.10 Step 9: IPsec

Commands on `ipsec-rtr1`:

```
show crypto isakmp sa
show crypto ipsec sa | include ident|spi|transform|in use|encaps|decaps
ping 172.30.1.2
```

Expected:

- Two ISAKMP entries with state `QM_IDLE` and status `ACTIVE`.
- The IPsec selector is protocol 47 between `172.20.1.1` and `172.21.1.1`.
- The transform is `esp-256-aes esp-sha256-hmac` in tunnel mode.
- The counters `encaps` and `decaps` increase with each ping.
- The tunnel ping to `172.30.1.2` has a success rate of 100 percent.

If the ISAKMP entry stays in `MM_NO_STATE` or does not appear, the IKE packets do not cross the core. Go back to step 8.

### 9.11 Step 10: end-to-end and per-hop proof

Commands on `host1`:

```
ping 192.168.2.10 repeat 100
traceroute 192.168.2.10 numeric
```

Expected: success rate is 95 percent or more. The first packet can be lost while the routers do ARP. The traceroute shows three hops:

```
1  192.168.1.1     (ipsec-rtr1)
2  172.30.1.2      (Tunnel100 of ipsec-rtr2)
3  192.168.2.10    (host2)
```

The core routers do not show in this output. This is correct. The tunnel hides them.

To follow one packet through the core, do this:

1. Start a capture with the filter `ip6 proto 4` on all four P routers and on both PE routers. See section 9.2.
2. Send a short ping from `host1` (`repeat 3`).
3. Read the captures. The routers that show the packet are on the path.
4. Check that the hop limit decreases by 1 on each router, and that the inner IPv4 TTL does not change.

Use this table as the check list for one direction:

| Capture point | Filter | Expected packet |
|---|---|---|
| `host1` LAN side (on `ipsec-rtr1` `eth2`) | `icmp` | Plain ICMP, `192.168.1.10 > 192.168.2.10` |
| `ipsec-rtr1` `eth1` | `esp` | IPv4 ESP, `172.20.1.1 > 172.21.1.1`, TTL 255 |
| `pe-rtr-1` egress | `ip6 proto 4` | IPv6 `... > FCBB:BB00:2:E002::`, hop limit 64, next header 4 |
| Each P router | `ip6 proto 4` | Same packet, hop limit 1 lower on each hop |
| `pe-rtr-2` ingress | `ip6 proto 4` | Same packet, hop limit 62 (with 2 P routers on the path) |
| `pe-rtr-2` `eth1` | `esp` | IPv4 ESP, no IPv6 header, TTL 254 |
| `ipsec-rtr2` `eth2` | `icmp` | Plain ICMP, TTL 253 |

Also check the counters. The P routers count the forwarded IPv6 packets. `verify.py` uses this command:

```
show ipv6 traffic | include forwarded
```

The counter increases on the P routers in the path when the test sends packets.

### 9.12 Full test

`verify.py` runs 26 checks:

| Group | Checks |
|---|---|
| IS-IS | Adjacency count on 6 nodes |
| SRv6 | Locator state on 6 nodes |
| BGP | VPNv4 session, remote route with SID, local SID, on 2 PE routers |
| IPsec | ISAKMP SA on 2 CE routers |
| Data plane | CE loopback ping, tunnel ping, IPsec counters |
| End to end | Ping in both directions, core packet counters |

Run it with `uv run verify.py`. The exit code is 0 when all checks pass.

## 10. Fault finding

| Symptom | Likely cause | How to check |
|---|---|---|
| No IS-IS neighbor | `ipv6 enable` or `ipv6 router isis 1` is missing. The interface is down. | `show isis neighbors`, `show ipv6 interface brief` |
| No locator route on a PE | `segment-routing srv6` / `locator LOC1` is missing under IS-IS | `show ipv6 route isis`, `show isis database detail` |
| Locator status is not `Up` | The locator prefix or format is wrong | `show segment-routing srv6 locator` |
| No `uDT4` SID | The VRF has no `segment-routing srv6` block or no `alloc-mode per-vrf` | `show segment-routing srv6 sid` |
| VPNv4 session is `Idle` or `Active` | No route to the remote loopback. Wrong `update-source`. | `ping 2001:DB8:FFFF::2 source Loopback0` |
| VPNv4 route has no `out-sid` | The remote PE has no SID for the VRF | `show bgp vpnv4 unicast all <prefix>` on both PE routers |
| Sending PE has the route, receiving PE has none, session is up | The export RT on the sending PE does not match the import RT on the receiving PE | `neighbors 2001:DB8:FFFF::1 routes` on the receiving PE (0 prefixes), `show ip vrf detail CE-RTR1` on both PE routers (section 5.8.5) |
| Route in the VRF, but ping fails | The FIB has no encapsulation. The core has no locator route. | `show ip cef vrf CE-RTR1 <prefix> detail`, `show ipv6 route <SID>` on each P router |
| Packet leaves the PE but does not arrive | A P router does not have the locator route, or the hop limit is 0 | Capture on each hop (section 9.11) |
| ISAKMP does not start | Loopback ping fails, or the pre-shared keys are different | `ping 172.21.1.1 source 172.20.1.1`, `show crypto isakmp sa` |
| Host ping works, but no core traffic | The host management port carries the traffic (no `MGMT` VRF) | `show ip arp` on the host. The remote host must not be in the ARP table on `Ethernet0/0`. |
| SSH to a node fails | The node is still in boot (about 2 minutes) | `docker logs clab-iol-srv6-<node>` |

## 11. Lab limits

- **IOL cannot change the MTU.** The interface MTU is 1500 bytes. The GRE, ESP, and outer IPv6 headers add bytes. The lab uses `ip tcp adjust-mss 1360` to prevent TCP fragmentation. Large non-TCP packets can be fragmented.
- **The lab has only one VRF and one route target.** It does not show route-target filtering.
- **The lab has no traffic engineering.** Each packet has one SID. The lab does not use an SRH or a list of uSIDs (section 7.5).
- **The hash decides the ECMP path.** A path can change between tests.
- **The core does not forward IPv4.** The core links have no IPv4 address. The IPv4 loopbacks only give the router IDs.
- **The pre-shared key is in the configuration in clear text.** This is a lab setting.
- **The hosts are IOL routers.** They are not Linux hosts.

## 12. Quick command list

| Purpose | Command | Node |
|---|---|---|
| IS-IS neighbors | `show isis neighbors` | Core |
| IS-IS IPv6 routes | `show ipv6 route isis` | Core |
| IS-IS database and SRv6 TLV | `show isis database detail` | Core |
| Locator state | `show segment-routing srv6 locator` | PE, P |
| All SIDs of the node | `show segment-routing srv6 sid` | PE, P |
| VPNv4 sessions | `show bgp vpnv4 unicast all summary` | PE |
| VPNv4 routes | `show bgp vpnv4 unicast all` | PE |
| One VPNv4 route with the SID | `show bgp vpnv4 unicast all <prefix>` | PE |
| VRF routes | `show ip route vrf CE-RTR1` | PE |
| Encapsulation in the FIB | `show ip cef vrf CE-RTR1 <prefix> detail` | PE |
| Route to a SID | `show ipv6 route <SID>` | P, PE |
| ISAKMP state | `show crypto isakmp sa` | CE |
| IPsec state and counters | `show crypto ipsec sa` | CE |
| Tunnel state | `show interfaces Tunnel100` | CE |
| Forwarded IPv6 packets | `show ipv6 traffic` | P |
| Start the lab | `clab deploy -t lab-srv6.clab.yml` | Host |
| Stop the lab | `clab destroy -t lab-srv6.clab.yml --cleanup` | Host |
