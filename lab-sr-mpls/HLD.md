# SR-MPLS L3VPN Lab: High-Level Design

## 1. About this document

### 1.1 Purpose

This document describes the design of the `iol-srmpls` lab. It explains each part of the design and each configuration block. It shows how one packet travels through the lab. It gives a hop-by-hop procedure to check every step.

The lab is the SR-MPLS version of `lab-srv6`. The topology, the nodes, and the customer side are the same. Only the provider core is different. The file `COMPARE.md` compares the two labs. The file `../lab-srv6/HLD.md` describes the SRv6 lab in the same structure as this document.

### 1.2 Scope

The document covers the lab in this folder:

- `lab-sr-mpls.clab.yml` (the topology)
- `configs/*.cfg` (the startup configuration of each node)
- `gen_configs.py` (the script that makes the configurations)
- `verify.py` and `cli.py` (the test tools)

### 1.3 How to read the document

- **Observed** means the text comes from a command or a packet capture in the running lab. The lab was tested on 2026-09-21 with IOS-XE 17.18.2 (IOL image).
- **Concept** means the text explains a general SR-MPLS rule. The lab does not show this rule in its output.
- SPI values, sequence numbers, and MAC addresses change after each deploy. Use them as examples only.
- Dynamic labels (16, 17, 18 in this lab) can be different after a deploy. The prefix-SID labels (16001 and up) do not change.
- Output filters can hide the second line of an ECMP entry. Read the full output when you look for ECMP.

### 1.4 Terms

| Term | Meaning |
|---|---|
| CE | Customer edge router. It connects to the provider. |
| PE | Provider edge router. It has the customer VRF. |
| P | Provider core router. It only switches labels. |
| VRF | Virtual routing and forwarding table. It keeps customer routes apart. |
| SR-MPLS | Segment Routing with the MPLS data plane. A segment is an MPLS label. |
| SID | Segment identifier. In SR-MPLS it is a label, or an index into a label range. |
| SRGB | Segment Routing Global Block. The label range that all nodes use for prefix SIDs. |
| Prefix SID | A global segment for a prefix (here, a node loopback). |
| Adjacency SID | A local segment for one link to a neighbor. |
| LFIB | Label forwarding information base. The table that a router uses to switch labels. |
| PHP | Penultimate hop popping. The router before the last router removes the transport label. |
| ECMP | Equal-cost multipath. A router uses more than one path with the same cost. |
| ESP | Encapsulating Security Payload. The IPsec protocol that encrypts the data. |
| GRE | Generic Routing Encapsulation. The tunnel type of `Tunnel100`. |

## 2. Design summary

The lab has 10 nodes. Two hosts connect through two CE routers, two PE routers, and four P routers.

| Layer | Technology | Where |
|---|---|---|
| Core links | IPv4 unnumbered (`ip unnumbered Loopback0`) | All P and PE core links |
| Core IGP | IS-IS level 2, IPv4 | PE and P routers |
| Core transport | SR-MPLS with prefix SIDs (SRGB 16000 to 23999) | PE and P routers |
| Customer service | BGP VPNv4 (IPv4 VPN) between PE routers, with a per-VRF VPN label | `pe-rtr-1`, `pe-rtr-2` |
| PE-CE routing | eBGP in VRF `CE-RTR1` | PE to CE |
| Customer overlay | GRE tunnel protected by IPsec | `ipsec-rtr1` to `ipsec-rtr2` |
| Customer LAN | IPv4 static routes through `Tunnel100` | CE to host |

Section 5.8 explains how the VPNv4 customer service works.

Five design rules apply:

1. The core does not carry customer routes. The customer IPv4 packet rides under two MPLS labels.
2. The core links have no IP address. They borrow the address of `Loopback0`.
3. The P routers do not know any customer route. They only switch labels from IS-IS.
4. The PE routers push and pop the VPN label. The P routers swap or pop the transport label.
5. The CE routers encrypt the traffic. The provider network carries only ESP packets.

The design does not use LDP or RSVP. IS-IS distributes all transport labels.

## 3. Topology

### 3.1 Diagram

```
                         SR-MPLS core: IS-IS, unnumbered links
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
| `host1` | Host, site 1 | `clab-iol-srmpls-host1` | 172.100.211.11 | none |
| `ipsec-rtr1` | CE, AS 65250 | `clab-iol-srmpls-ipsec-rtr1` | 172.100.211.12 | Lo100 172.20.1.1/32 |
| `pe-rtr-1` | PE, AS 65001 | `clab-iol-srmpls-pe-rtr-1` | 172.100.211.13 | Lo0 10.0.0.1/32 |
| `core-p-rtr-1` | P | `clab-iol-srmpls-core-p-rtr-1` | 172.100.211.14 | Lo0 10.0.0.11/32 |
| `core-p-rtr-2` | P | `clab-iol-srmpls-core-p-rtr-2` | 172.100.211.15 | Lo0 10.0.0.12/32 |
| `core-p-rtr-3` | P | `clab-iol-srmpls-core-p-rtr-3` | 172.100.211.16 | Lo0 10.0.0.13/32 |
| `core-p-rtr-4` | P | `clab-iol-srmpls-core-p-rtr-4` | 172.100.211.17 | Lo0 10.0.0.14/32 |
| `pe-rtr-2` | PE, AS 65001 | `clab-iol-srmpls-pe-rtr-2` | 172.100.211.18 | Lo0 10.0.0.2/32 |
| `ipsec-rtr2` | CE, AS 65351 | `clab-iol-srmpls-ipsec-rtr2` | 172.100.211.19 | Lo100 172.21.1.1/32 |
| `host2` | Host, site 2 | `clab-iol-srmpls-host2` | 172.100.211.20 | none |

All nodes use the image `vrnetlab/cisco_iol:17.18.02`. Log in with `ssh admin@clab-iol-srmpls-<node>` (password `admin`).

### 3.3 Links

`Ethernet0/0` is the management port of each node. The data links start at `Ethernet0/1`. In the containers, `ethN` is `Ethernet0/N`. Use this rule when you read packet captures.

| # | Node A | Interface A | Node B | Interface B | Network | Type |
|---|---|---|---|---|---|---|
| 1 | `host1` | Et0/1 | `ipsec-rtr1` | Et0/2 | 192.168.1.0/24 | IPv4 LAN |
| 2 | `ipsec-rtr1` | Et0/1 | `pe-rtr-1` | Et0/1 | 10.1.1.0/30 | IPv4, eBGP, VRF |
| 3 | `pe-rtr-1` | Et0/2 | `core-p-rtr-1` | Et0/1 | unnumbered | Core |
| 4 | `pe-rtr-1` | Et0/3 | `core-p-rtr-3` | Et0/1 | unnumbered | Core |
| 5 | `core-p-rtr-1` | Et0/2 | `core-p-rtr-2` | Et0/1 | unnumbered | Core |
| 6 | `core-p-rtr-1` | Et0/3 | `core-p-rtr-4` | Et0/2 | unnumbered | Core |
| 7 | `core-p-rtr-3` | Et0/2 | `core-p-rtr-4` | Et0/1 | unnumbered | Core |
| 8 | `core-p-rtr-3` | Et0/3 | `core-p-rtr-2` | Et0/2 | unnumbered | Core |
| 9 | `core-p-rtr-2` | Et0/3 | `pe-rtr-2` | Et0/2 | unnumbered | Core |
| 10 | `core-p-rtr-4` | Et0/3 | `pe-rtr-2` | Et0/3 | unnumbered | Core |
| 11 | `pe-rtr-2` | Et0/1 | `ipsec-rtr2` | Et0/1 | 10.2.2.0/30 | IPv4, eBGP, VRF |
| 12 | `ipsec-rtr2` | Et0/2 | `host2` | Et0/1 | 192.168.2.0/24 | IPv4 LAN |

The topology picture uses other interface numbers. The lab uses the numbers in this table.

### 3.4 Path cost

Each core link has IS-IS metric 10. The loopback route has metric 10. From `pe-rtr-1` to `10.0.0.2/32`, the cost is 40 (three links plus the loopback). Four paths have this cost:

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
| Management network | 172.100.211.0/24 | Docker network `clab-iol-srmpls` |
| Core loopback | 10.0.0.<n>/32 | IS-IS router ID, BGP router ID, BGP session address, prefix-SID prefix |
| Core links | `ip unnumbered Loopback0` | No IP address of their own |
| SRGB | 16000 to 23999 | The IOS-XE default |
| SRLB | 15000 to 15999 | The IOS-XE default (not used by this lab) |
| Prefix-SID label | 16000 + <n> | One per node loopback |
| PE-CE link, site 1 | 10.1.1.0/30 (CE .1, PE .2) | In VRF `CE-RTR1` on the PE |
| PE-CE link, site 2 | 10.2.2.0/30 (CE .1, PE .2) | In VRF `CE-RTR1` on the PE |
| Customer LAN, site 1 | 192.168.1.0/24 (CE .1, host .10) | |
| Customer LAN, site 2 | 192.168.2.0/24 (CE .1, host .10) | |
| Tunnel source | 172.20.1.1/32 (CE1), 172.21.1.1/32 (CE2) | `Loopback100` |
| Tunnel network | 172.30.1.0/30 (CE1 .1, CE2 .2) | `Tunnel100` |

The node number `<n>` is:

| Node | `<n>` |
|---|---|
| `pe-rtr-1` | 1 |
| `pe-rtr-2` | 2 |
| `core-p-rtr-1` | 11 |
| `core-p-rtr-2` | 12 |
| `core-p-rtr-3` | 13 |
| `core-p-rtr-4` | 14 |

Here `<n>` is a decimal number. Example: `core-p-rtr-1` has the loopback `10.0.0.11` and the label 16011.

## 5. Design details

### 5.1 Unnumbered core links

Each core interface has the command `ip unnumbered Loopback0`. The interface has no IP address. It uses the address of `Loopback0` as the source address of its packets.

IS-IS works over these links. IS-IS sends its packets on the data link. The neighbor shows the loopback address of the other router. Observed on `pe-rtr-1`:

```
System Id       Type Interface     IP Address      State Holdtime Circuit Id
core-p-rtr-1    L2   Et0/2         10.0.0.11       UP    21       02
core-p-rtr-3    L2   Et0/3         10.0.0.13       UP    30       02
```

The next hop of a route is the loopback address of the neighbor. Example: `10.0.0.11` on `Ethernet0/2`. Observed:

```
pe-rtr-1#show ip interface brief | include Ethernet0/[23]|Loopback
Ethernet0/2            10.0.0.1        YES unset  up                    up
Ethernet0/3            10.0.0.1        YES unset  up                    up
Loopback0              10.0.0.1        YES TFTP   up                    up
```

The unnumbered link is the IPv4 equivalent of the link-local core in `lab-srv6`. There is no address plan for the core links.

### 5.2 IS-IS

IS-IS is the only IGP in the core.

| Parameter | Value | Reason |
|---|---|---|
| Process | `router isis 1` | Same on all core nodes |
| NET | `49.0001.0000.0000.<n>.00` | One area. The system ID is the node number in 4 digits. |
| Level | `is-type level-2-only` | One level is enough |
| Metric style | `wide` | SR needs wide metrics |
| SR | `segment-routing mpls` | Tells IS-IS to advertise SR data and to program labels |
| Interface type | `isis network point-to-point` | No DIS election on Ethernet links |
| Interfaces | Core links and `Loopback0` | `ip router isis 1` on each |

IS-IS carries two pieces of SR information:

- The router capability TLV has the SRGB. Observed in the LSP of `core-p-rtr-1`:

```
Segment Routing: I:1 V:0, SRGB Base: 16000 Range: 8000
Segment Routing Local Block: SRLB Base: 15000 Range: 1000
Segment Routing Algorithms: SPF, Strict-SPF
```

- The prefix of each loopback has a prefix-SID index. Observed on `pe-rtr-1`:

```
pe-rtr-1#show isis rib
10.0.0.2/32  prefix attr X:0 R:0 N:1  prefix SID index 2 - Bound
  [115/L2/40] via 10.0.0.11(Ethernet0/2), from 10.0.0.2
     SRGB: 16000, range: 8000 prefix-SID index: 2, R:0 N:1 P:0 E:0 V:0 L:0
     label: 16002
  [115/L2/40] via 10.0.0.13(Ethernet0/3), from 10.0.0.2
     label: 16002
```

The label is the SRGB base plus the index: 16000 + 2 = 16002. Two routes have the same cost (ECMP).

### 5.3 SR-MPLS labels

#### 5.3.1 Label types in this lab

| Label type | Range or value | Scope | Made by | Use |
|---|---|---|---|---|
| Prefix SID | 16000 + index (16001 to 16014) | Global: same value on all nodes | Configuration (`connected-prefix-sid-map`) and IS-IS | Transport to a node |
| Adjacency SID | Dynamic (16, 17, 18 in this lab) | Local to the router | IS-IS | Send on one link (not used in normal forwarding) |
| VPN label | Dynamic (18 on both PE routers in this lab) | Local to the PE | BGP | Select the customer VRF |

The prefix SID is the same on every router because all routers use the same SRGB. A router that receives label 16002 knows the destination is `10.0.0.2` (`pe-rtr-2`).

The VPN label and the adjacency labels come from the same dynamic pool. Do not confuse them. In this lab, both PE routers have the VPN label 18 by chance. Each PE allocates its own value.

#### 5.3.2 Prefix-SID table

| Node | Loopback | Index | Label |
|---|---|---|---|
| `pe-rtr-1` | 10.0.0.1/32 | 1 | 16001 |
| `pe-rtr-2` | 10.0.0.2/32 | 2 | 16002 |
| `core-p-rtr-1` | 10.0.0.11/32 | 11 | 16011 |
| `core-p-rtr-2` | 10.0.0.12/32 | 12 | 16012 |
| `core-p-rtr-3` | 10.0.0.13/32 | 13 | 16013 |
| `core-p-rtr-4` | 10.0.0.14/32 | 14 | 16014 |

#### 5.3.3 Label table of each node (observed)

The tables show the local label, the action, and the next hop. `Pop Label` means the router removes the top label and sends the packet (PHP or a link SID). A remote prefix has an equal label in and out (swap). Each remote node label has two ECMP lines on some routers. The table shows the first line.

`pe-rtr-1`:

| Local label | Action | Prefix or context | Interface (next hop) |
|---|---|---|---|
| 16 | Pop | 10.0.0.11 (adjacency SID) | Et0/2 (10.0.0.11) |
| 17 | Pop | 10.0.0.13 (adjacency SID) | Et0/3 (10.0.0.13) |
| 18 | No label (VRF) | IPv4 VRF, `aggregate/CE-RTR1` | Lookup in the VRF |
| 16002 | Swap to 16002 | 10.0.0.2/32 | Et0/2 (P1) and Et0/3 (P3) |
| 16011 | Pop | 10.0.0.11/32 | Et0/2 |
| 16012 | Swap to 16012 | 10.0.0.12/32 | Et0/2 and Et0/3 |
| 16013 | Pop | 10.0.0.13/32 | Et0/3 |
| 16014 | Swap to 16014 | 10.0.0.14/32 | Et0/2 and Et0/3 |

`core-p-rtr-4`:

| Local label | Action | Prefix or context | Interface (next hop) |
|---|---|---|---|
| 16 | Pop | 10.0.0.11 (adjacency SID) | Et0/2 |
| 17 | Pop | 10.0.0.2 (adjacency SID) | Et0/3 |
| 18 | Pop | 10.0.0.13 (adjacency SID) | Et0/1 |
| 16001 | Swap to 16001 | 10.0.0.1/32 | Et0/2 (P1) |
| 16002 | Pop | 10.0.0.2/32 | Et0/3 (PE2) |
| 16011 | Pop | 10.0.0.11/32 | Et0/2 |
| 16012 | Swap to 16012 | 10.0.0.12/32 | Et0/3 |
| 16013 | Pop | 10.0.0.13/32 | Et0/1 |

The labels for the other nodes have the same structure. A router pops the label when the next hop is the node that owns the prefix (PHP). The router swaps the label in all other cases.

Adjacency labels (observed):

| Node | Label 16 | Label 17 | Label 18 |
|---|---|---|---|
| `pe-rtr-1` | Et0/2 to P1 | Et0/3 to P3 | VPN label (VRF `CE-RTR1`) |
| `pe-rtr-2` | Et0/2 to P2 | Et0/3 to P4 | VPN label (VRF `CE-RTR1`) |
| `core-p-rtr-1` | Et0/1 to PE1 | Et0/2 to P2 | Et0/3 to P4 |
| `core-p-rtr-2` | Et0/1 to P1 | Et0/3 to PE2 | Et0/2 to P3 |
| `core-p-rtr-3` | Et0/1 to PE1 | Et0/2 to P4 | Et0/3 to P2 |
| `core-p-rtr-4` | Et0/2 to P1 | Et0/3 to PE2 | Et0/1 to P3 |

The router assigns adjacency labels in the order in which the IS-IS adjacencies come up. The order is not the order of the interface numbers. Read the table on the node to find the mapping.

#### 5.3.4 MPLS without LDP

The interfaces show MPLS as operational, and LDP is off. Observed:

```
pe-rtr-1#show mpls interfaces
Interface              IP            Tunnel   BGP Static Operational
Ethernet0/2            No            No       No  No     Yes
Ethernet0/3            No            No       No  No     Yes
```

The column `IP` is the LDP state. IS-IS SR makes the interfaces operational. The lab does not have `mpls ip`.

### 5.4 VRF and BGP VPNv4

#### 5.4.1 VRF

Each PE has one VRF with the same name and the same route targets:

| Item | Value |
|---|---|
| VRF name | `CE-RTR1` |
| Route distinguisher | `65001:1` |
| Route target export and import | `65001:1` |
| VRF interface | `Ethernet0/1` (link to the CE) |
| VPN label mode | Per VRF (`mpls label mode all-vrfs protocol bgp-vpnv4 per-vrf`) |

Both PE routers use the same VRF name and route target. Each router imports the routes that the other PE exports.

#### 5.4.2 iBGP between the PE routers

| Item | Value |
|---|---|
| AS | 65001 (both PE routers) |
| Neighbor address | The IPv4 loopback of the other PE (`10.0.0.1` and `10.0.0.2`) |
| Update source | `Loopback0` |
| Address family | `vpnv4` only (`no bgp default ipv4-unicast`) |
| Community | `send-community extended` (carries the route target) |

The BGP session runs between the loopbacks. IS-IS makes these loopback addresses reachable. The core sends this traffic with labels too (section 11).

#### 5.4.3 VPN label

The command `mpls label mode all-vrfs protocol bgp-vpnv4 per-vrf` makes one label for the whole VRF. Observed on `pe-rtr-1`:

```
pe-rtr-1#show ip vrf detail CE-RTR1
  VRF label allocation mode: per-vrf (Label 18)

pe-rtr-1#show mpls forwarding-table
18         No Label   IPv4 VRF[V]      48540         aggregate/CE-RTR1
```

The PE sends the label in the VPNv4 route. The remote PE keeps it with the route. IOS shows the label as `mpls labels in/out`.

Observed on `pe-rtr-1` for the route `172.21.1.1/32`, learned from `pe-rtr-2`:

```
10.0.0.2 (metric 40) (via default) from 10.0.0.2 (10.0.0.2)
  Extended Community: RT:65001:1
  mpls labels in/out nolabel/18
```

The out label is 18. This is the VPN label of `pe-rtr-2`. `pe-rtr-1` pushes it on the packet.

### 5.5 PE-CE eBGP

| Site | CE | CE AS | PE address | CE address | Prefix that the CE announces |
|---|---|---|---|---|---|
| 1 | `ipsec-rtr1` | 65250 | 10.1.1.2 | 10.1.1.1 | 172.20.1.1/32 |
| 2 | `ipsec-rtr2` | 65351 | 10.2.2.2 | 10.2.2.1 | 172.21.1.1/32 |

Each CE announces only its tunnel source loopback (`Loopback100`). The provider network carries the traffic between the two tunnel endpoints. The provider network does not carry the customer LAN routes. This part is the same as in `lab-srv6`.

### 5.6 IPsec overlay

The two CE routers make a GRE tunnel and protect it with IPsec. This part is the same as in `lab-srv6`.

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

The IPsec traffic is a normal IPv4 flow between the two loopbacks. The BGP routes in the VRF and the SR-MPLS core carry it.

### 5.7 Hosts

The hosts are IOL routers. They have `Ethernet0/1` in the customer LAN and a default route to the CE. Their management port `Ethernet0/0` is in `vrf definition MGMT`. This VRF keeps the management network out of the test path.

If the management port is not in a VRF, a host sends lab traffic through `Ethernet0/0`. The ping then works but does not use the lab.

### 5.8 How the VPNv4 customer service works

This section explains the customer service for a network engineer who knows MPLS L3VPN. It follows one route, `172.21.1.1/32`, from `ipsec-rtr2` to `ipsec-rtr1`. All output in this section is observed.

In this lab the VPN service is a normal MPLS L3VPN. The transport label comes from IS-IS SR and not from LDP. The VPN label comes from BGP.

#### 5.8.1 What the service does

The customer has two sites. Each site has one CE router. The service gives the two CE routers IPv4 reachability to each other across the provider network.

- Each PE keeps the customer routes in a VRF. The other customers, and the provider, do not see these routes.
- The two PE routers exchange the customer routes with MP-BGP (address family VPNv4).
- The core carries the customer packets under two MPLS labels.
- In this lab, the customer uses the service to connect the two tunnel loopbacks (`172.20.1.1/32` and `172.21.1.1/32`). The customer builds the IPsec tunnel on top of this service (section 5.6).

What each device knows:

| Device | Customer routes | Provider routes | Observed |
|---|---|---|---|
| CE | Own site and the remote loopback | None | The CE has one eBGP neighbor: the PE (AS 65001). |
| PE | In VRF `CE-RTR1` and in the VPNv4 table | In the global IPv4 table and the LFIB | The global table has no customer route. |
| P | None | In the global IPv4 table and the LFIB | BGP is not running. |

Observed on `pe-rtr-1`:

```
pe-rtr-1#show ip route vrf CE-RTR1 bgp
B        172.20.1.1 [20/0] via 10.1.1.1
B        172.21.1.1 [200/0] via 10.0.0.2
```

#### 5.8.2 The three tables on a PE

| Table | What it holds | Command |
|---|---|---|
| Global IPv4 table and LFIB | Core loopbacks (IS-IS) and labels | `show ip route isis`, `show mpls forwarding-table` |
| VRF IPv4 table | Customer routes of the VRF | `show ip route vrf CE-RTR1` |
| VPNv4 BGP table | Customer routes with RD, RT, and VPN label | `show bgp vpnv4 unicast all` |

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
  VRF label allocation mode: per-vrf (Label 18)
```

#### 5.8.3 Route advertisement: CE2 to CE1

The route `172.21.1.1/32` is the loopback of `ipsec-rtr2`. It travels in eight steps.

| Step | Device | Action |
|---|---|---|
| 1 | `ipsec-rtr2` | The `network 172.21.1.1 mask 255.255.255.255` command puts the prefix in BGP. The CE sends it to the PE with eBGP. |
| 2 | `pe-rtr-2` | The PE receives the route in VRF `CE-RTR1`. It installs the route with next hop `10.2.2.1` and distance 20 (eBGP). |
| 3 | `pe-rtr-2` | The PE exports the route into VPNv4. It adds the RD (`65001:1`), the export RT (`65001:1`), and the VPN label of the VRF (18). It sets the next hop to its own loopback (`10.0.0.2`). |
| 4 | `pe-rtr-2` | The PE sends the VPNv4 update to `pe-rtr-1`. The TCP session (port 179) runs between the loopbacks. |
| 5 | `pe-rtr-1` | The PE checks the RT in the update. `RT:65001:1` matches the import RT of VRF `CE-RTR1`. The PE accepts the route and keeps the label. |
| 6 | `pe-rtr-1` | The PE installs the route in the VRF with distance 200 (iBGP). The next hop is `10.0.0.2`. |
| 7 | `pe-rtr-1` | The PE sends the route to `ipsec-rtr1` with eBGP. It adds its own AS (65001) to the AS path. |
| 8 | `ipsec-rtr1` | The CE installs the route with next hop `10.1.1.2` and distance 20 (eBGP). |

The same route in each table:

| Device | Table | Entry (observed) |
|---|---|---|
| `pe-rtr-2` | VRF route table | `B 172.21.1.1 [20/0] via 10.2.2.1` |
| `pe-rtr-2` | VPNv4 table | `65001:1:172.21.1.1/32`, exported with `RT:65001:1` and the VPN label 18 |
| `pe-rtr-1` | VPNv4 table | `65001:1:172.21.1.1/32`, next hop `10.0.0.2`, `mpls labels in/out nolabel/18` |
| `pe-rtr-1` | VRF route table | `B 172.21.1.1 [200/0] via 10.0.0.2` |
| `ipsec-rtr1` | Route table | `B 172.21.1.1 [20/0] via 10.1.1.2` |

#### 5.8.4 How routes move between the VRF and VPNv4

A PE uses two BGP address families for the customer service. One faces the CE. The other faces the other PE. The VRF definition connects them. No `redistribute` command and no route map move the routes. The RD and the route targets of the VRF control the movement.

| Part | Configuration | Faces | Carries |
|---|---|---|---|
| VRF IPv4 address family | `address-family ipv4 vrf CE-RTR1` under `router bgp 65001` | The CE (eBGP, `10.1.1.1` on `pe-rtr-1`) | Plain IPv4 prefixes of the customer |
| VPNv4 address family | `address-family vpnv4` under `router bgp 65001` | The other PE (iBGP, `10.0.0.2` on `pe-rtr-1`) | VPNv4 prefixes (RD plus IPv4 prefix), route targets, and the VPN label |
| VRF definition | `vrf definition CE-RTR1` with `rd`, `route-target export`, `route-target import` | No neighbor | The rules that move routes between the two address families |

Two terms describe the movement:

- **Export** moves a route from the VRF IPv4 address family to VPNv4. The PE that learns the route from its CE does this.
- **Import** moves a route from VPNv4 to the VRF IPv4 address family. The PE that receives the route from the other PE does this.

**The VRF view.** The command `show bgp vpnv4 unicast vrf CE-RTR1` shows the routes of the VRF. It shows the routes from the CE and the routes that the PE imported. Observed on `pe-rtr-1`:

```
pe-rtr-1#show bgp vpnv4 unicast vrf CE-RTR1
Route Distinguisher: 65001:1 (default for vrf CE-RTR1)
 *>   172.20.1.1/32    10.1.1.1                 0             0 65250 i
 *>i  172.21.1.1/32    10.0.0.2
```

The first route came from the CE. The PE exports it. The second route came from the other PE (the letter `i` means iBGP). The PE imported it. Both PE routers use RD 65001:1, so both routes show under the same RD. Concept: if the PE routers use different RD values, an imported route keeps the RD of the PE that exported it. The VRF routing table uses only the IPv4 prefix.

##### Export: VRF IPv4 to VPNv4

The route is `172.20.1.1/32` (the loopback of `ipsec-rtr1`). `pe-rtr-1` exports it.

| Step | Action of the PE | Observed |
|---|---|---|
| 1 | Receive the route from the CE with eBGP. Put it in the BGP table of the VRF. | `show bgp vpnv4 unicast all 172.20.1.1/32` shows `10.1.1.1 (via vrf CE-RTR1) from 10.1.1.1` and `external`. |
| 2 | Add the RD. The IPv4 prefix becomes a VPNv4 prefix. | The entry name is `65001:1:172.20.1.1/32`. |
| 3 | Add the export route target. The CE did not send it. | `Extended Community: RT:65001:1` |
| 4 | Add the service identifier of the VRF: the VPN label of the VRF (18). | `mpls labels in/out IPv4 VRF Aggr:18/nolabel` |
| 5 | Send the route to the VPNv4 neighbor. | `show bgp vpnv4 unicast all neighbors 10.0.0.2 advertised-routes` lists one prefix: `172.20.1.1/32`. |
| 6 | Set the BGP next hop to the own loopback in the update. | `pe-rtr-2` receives the next hop `10.0.0.1`. The local view of the advertised route still shows the CE address `10.1.1.1`. |
| 7 | Keep the AS path. iBGP adds no AS number. | The path is `65250`. |

##### Import: VPNv4 to VRF IPv4

The route is the same route, `172.20.1.1/32`. `pe-rtr-2` imports it.

| Step | Action of the PE | Observed |
|---|---|---|
| 1 | Receive the VPNv4 update from the iBGP neighbor. | `show bgp vpnv4 unicast all neighbors 10.0.0.1 routes` on `pe-rtr-2` lists `172.20.1.1/32`. |
| 2 | Check that the BGP next hop is reachable in the IGP. | `10.0.0.1 (metric 40)` |
| 3 | Compare the route targets in the update with the import route targets of the VRFs. One match is enough. | The update has `RT:65001:1`. The VRF `CE-RTR1` imports `RT:65001:1`. The route is imported. |
| 4 | Discard the route if no VRF matches. | Not seen in the normal state. See the export exercise below: the neighbor shows `Total number of prefixes 0`. |
| 5 | Use the IPv4 prefix in the VRF. The RD is not used in the VRF routing table. | The route table shows `172.20.1.1`. |
| 6 | Keep the VPN label for forwarding. | `mpls labels in/out nolabel/18` |
| 7 | Select the best path. Install it in the VRF routing table. | `B 172.20.1.1 [200/0] via 10.0.0.1` (distance 200 means iBGP) |
| 8 | Advertise the route to the CE with eBGP. Add the AS 65001. Set the next hop to the PE address on the PE-CE link. Do not send the route target. | `ipsec-rtr2` shows `172.20.1.1/32` with next hop `10.2.2.2` and path `65001 65250`. The entry has no route target. |

The command `show bgp vpnv4 unicast vrf CE-RTR1 neighbors 10.2.2.1 advertised-routes` on `pe-rtr-2` shows the route that the PE sends to the CE. The output shows the route before the outbound changes. It still has the next hop `10.0.0.1` and the path `65250`. The CE receives the next hop `10.2.2.2` and the path `65001 65250`.

##### The same route, step by step

Observed values for `172.20.1.1/32`, from `ipsec-rtr1` to `ipsec-rtr2`:

| Point | Prefix | RD | Route target | Next hop | AS path | Label |
|---|---|---|---|---|---|---|
| `ipsec-rtr1` sends | `172.20.1.1/32` | none | none | `10.1.1.1` | `65250` | none |
| `pe-rtr-1` VRF table (from the CE) | `172.20.1.1/32` | none | none | `10.1.1.1` | `65250` | none |
| `pe-rtr-1` VPNv4 table (after export) | `65001:1:172.20.1.1/32` | `65001:1` | `RT:65001:1` (added) | `10.1.1.1` in the local view. `10.0.0.1` in the update. | `65250` | in label 18 |
| `pe-rtr-2` VPNv4 table (received) | `65001:1:172.20.1.1/32` | `65001:1` | `RT:65001:1` | `10.0.0.1` | `65250` | out label 18 |
| `pe-rtr-2` VRF routing table (after import) | `172.20.1.1/32` | not used | not used | `10.0.0.1` | `65250` | used for forwarding |
| `ipsec-rtr2` receives | `172.20.1.1/32` | none | none | `10.2.2.2` | `65001 65250` | none |

Read the table from top to bottom. The RD and the route target exist only between the two PE routers. The CE routers see plain IPv4 routes.

##### Rules

| Rule | Observed or concept |
|---|---|
| Export takes the routes that the CE sent. A route that the PE imported is not exported again. | Observed: `neighbors 10.0.0.2 advertised-routes` on `pe-rtr-1` lists only `172.20.1.1/32`. The imported route `172.21.1.1/32` is not in the list. |
| A route is imported when at least one route target in the update matches at least one import route target of the VRF. | Concept. The VRF can have many `route-target import` lines. |
| A route carries all export route targets of the VRF. | Concept. The VRF can have many `route-target export` lines. |
| Export and import are separate. The export route target is what the other PE sees. The import route target is what this PE accepts. | Observed in the two exercises (import: section 5.8.6, export: below). |
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
| Route with RD, RT, and label after export | `show bgp vpnv4 unicast all 172.20.1.1/32` | `pe-rtr-1` |
| Routes sent to the other PE (export) | `show bgp vpnv4 unicast all neighbors 10.0.0.2 advertised-routes` | `pe-rtr-1` |
| Routes received from the other PE (before import) | `show bgp vpnv4 unicast all neighbors 10.0.0.1 routes` | `pe-rtr-2` |
| Route imported into the VRF | `show bgp vpnv4 unicast vrf CE-RTR1` and `show ip route vrf CE-RTR1 bgp` | `pe-rtr-2` |
| Route sent to the CE | `show bgp vpnv4 unicast vrf CE-RTR1 neighbors 10.2.2.1 advertised-routes` | `pe-rtr-2` |
| Route received by the CE | `show ip bgp` | `ipsec-rtr2` |
| Route targets of the VRF | `show ip vrf detail CE-RTR1` | Both PE routers |

##### Exercise: break the export route target

The exercise in section 5.8.6 breaks the import side. This exercise breaks the export side. It uses `pe-rtr-2`, which exports `172.21.1.1/32`. The restore steps give back the original configuration.

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
| `pe-rtr-1`: `neighbors 10.0.0.2 routes` | 1 prefix | `Total number of prefixes 0` |
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

#### 5.8.5 Read one VPNv4 route

Observed on `pe-rtr-1`:

```
pe-rtr-1#show bgp vpnv4 unicast all 172.21.1.1/32
BGP routing table entry for 65001:1:172.21.1.1/32, version 4
Paths: (1 available, best #1, table CE-RTR1)
  65351
    10.0.0.2 (metric 40) (via default) from 10.0.0.2 (10.0.0.2)
      Origin IGP, metric 0, localpref 100, valid, internal, best
      Extended Community: RT:65001:1
      mpls labels in/out nolabel/18
```

| Field | Value | Meaning |
|---|---|---|
| Entry name | `65001:1:172.21.1.1/32` | RD plus prefix. This is the VPNv4 prefix. |
| `table CE-RTR1` | VRF name | The router imported the route into this VRF. |
| Path `65351` | AS path | The AS of `ipsec-rtr2`. The PE routers are in the same AS, so iBGP adds nothing. |
| `10.0.0.2` | BGP next hop | The loopback of `pe-rtr-2`. |
| `(metric 40)` | IGP cost to the next hop | IS-IS cost to `10.0.0.2/32`. |
| `internal` | iBGP | The route came from a PE in the same AS. |
| `RT:65001:1` | Route target | The value that the import RT of the VRF must match. |
| `mpls labels in/out nolabel/18` | Labels | No in label (the route is remote). Out label 18: the VPN label of `pe-rtr-2`. |

For the local route, IOS shows the VRF label as the in label. Observed on `pe-rtr-1` for `172.20.1.1/32`: `mpls labels in/out IPv4 VRF Aggr:18/nolabel`.

The BGP next hop and the VPN label have different jobs. The next hop is the destination of the transport label. The VPN label selects the VRF on that node.

#### 5.8.6 Exercise: break the route target

This exercise shows how the RT controls the service. It uses `pe-rtr-1`. The restore steps give back the original configuration.

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
| `show bgp vpnv4 unicast all 172.21.1.1/32` | The route with the label | `Paths: (0 available, no best path)` |
| `show ip route vrf CE-RTR1 bgp` | Two BGP routes | Only `172.20.1.1` (from the CE) |
| `show bgp vpnv4 unicast all summary` (neighbor `10.0.0.2`) | `State/PfxRcd` 1 | `State/PfxRcd` 0, session still up |
| `ping 172.21.1.1 source 172.20.1.1` on `ipsec-rtr1` | 100 percent | 0 percent |

The BGP session stays up. The PE receives the update, and no local VRF imports it (the RT does not match). The customer loses the service, and the IPsec tunnel is down.

**Step 3.** Restore the configuration:

```
pe-rtr-1# configure terminal
pe-rtr-1(config)# vrf definition CE-RTR1
pe-rtr-1(config-vrf)# no route-target import 65001:2
pe-rtr-1(config-vrf)# route-target import 65001:1
pe-rtr-1(config-vrf)# end
```

**Step 4.** Wait 20 seconds. Check that the route `B 172.21.1.1 [200/0] via 10.0.0.2` is in `show ip route vrf CE-RTR1 bgp` and that the ping works.

Use this exercise to learn the symptom. The remote route is missing from the VRF, the BGP session is up, and the core is fine. Check the RT first.

#### 5.8.7 Lookups on each device

| Device | Lookup | Result |
|---|---|---|
| `ipsec-rtr1` | IPv4 route to `172.21.1.1` | eBGP route, next hop `10.1.1.2` |
| `pe-rtr-1` | 1. VRF `CE-RTR1` route to `172.21.1.1` | Next hop `10.0.0.2` with VPN label 18 |
| `pe-rtr-1` | 2. Route to `10.0.0.2` | Transport label 16002. Two ECMP next hops. |
| P router | LFIB entry for label 16002 | Swap (or pop at the penultimate hop). The router does not open the inner packet. |
| `pe-rtr-2` | LFIB entry for label 18 | `aggregate/CE-RTR1`. The PE removes the label and looks up the VRF. |
| `pe-rtr-2` | VRF `CE-RTR1` route to `172.21.1.1` | eBGP route, next hop `10.2.2.1` |
| `ipsec-rtr2` | Local address | The packet is for `Loopback100`. The CE processes the ESP packet. |

Section 7 and section 8 give the label details and the packet captures.

#### 5.8.8 Design points

- **The CE routers use different AS numbers.** `ipsec-rtr1` is AS 65250 and `ipsec-rtr2` is AS 65351. Concept: if both CE routers used the same AS, each CE would reject the remote route (BGP loop check). To fix this, use `neighbor <CE> as-override` on the PE, or `neighbor <PE> allowas-in` on the CE.
- **The PE routers use one AS (65001).** This makes an iBGP session between them. Concept: with more than two PE routers, use a full mesh or a route reflector.
- **`send-community extended` is required.** Without it, the update has no RT. The remote PE then cannot import the route. Concept.
- **The customer announces only the loopbacks.** The provider does not learn `192.168.1.0/24` or `192.168.2.0/24`.
- **Each PE makes its own VPN label.** Both PE routers use label 18 in this lab. Each PE allocates from its own dynamic pool in the same order.
- **The BGP next hop must have a label path.** If IS-IS has no route and no prefix SID for `10.0.0.2`, the PE cannot forward to the remote site.
- **The transport label is not in the BGP update.** The router builds it from IS-IS for the BGP next hop. Only the VPN label is in BGP.

#### 5.8.9 Where to check the service

| Question | Command | Node | Section |
|---|---|---|---|
| Is the PE-CE session up? | `show ip bgp summary` | CE | 9.9 |
| Does the PE receive the customer prefix? | `show ip route vrf CE-RTR1 bgp` | PE | 9.8 |
| Is the VPNv4 session up? | `show bgp vpnv4 unicast all summary` | PE | 9.6 |
| Does the route have RD, RT, and VPN label? | `show bgp vpnv4 unicast all <prefix>` | PE | 9.7 |
| Do the RT values match? | `show ip vrf detail CE-RTR1` | PE | 5.8.6 |
| Did the PE export the route? | `show bgp vpnv4 unicast all neighbors 10.0.0.2 advertised-routes` | Sending PE | 5.8.4 |
| Did the PE accept the route (import)? | `show bgp vpnv4 unicast all neighbors 10.0.0.1 routes` | Receiving PE | 5.8.4 |
| Does the FIB push the labels? | `show ip cef vrf CE-RTR1 <prefix> detail` | PE | 9.8 |

## 6. Configuration explained

The configurations are in `configs/`. `gen_configs.py` makes them. Each block below has the code and the explanation. The examples use `pe-rtr-1` and `ipsec-rtr1`.

### 6.1 Management block (all nodes)

```
username admin privilege 15 secret admin
ip domain name lab.local
ip ssh version 2
crypto key generate rsa modulus 2048
interface Ethernet0/0
 ip address 172.100.211.13 255.255.255.0
 no shutdown
line vty 0 4
 login local
 transport input ssh
ip route 172.19.0.0 255.255.0.0 172.100.211.1
```

This block gives SSH access. The lab needs a domain name and an RSA key to start the SSH server. The last line is a return route for access from Windows (see `../lab-srv6/LAB_Access.MD`).

### 6.2 PE: VRF and label mode

```
vrf definition CE-RTR1
 rd 65001:1
 route-target export 65001:1
 route-target import 65001:1
 address-family ipv4
 exit-address-family
!
mpls label mode all-vrfs protocol bgp-vpnv4 per-vrf
```

| Line | Explanation |
|---|---|
| `rd 65001:1` | Makes the customer prefix unique in VPNv4 |
| `route-target export/import` | Controls which routes go to and come from other PE routers |
| `address-family ipv4` | Turns on IPv4 in the VRF |
| `mpls label mode ... per-vrf` | One VPN label for the whole VRF |

### 6.3 PE and P: loopback and core interfaces

```
interface Loopback0
 ip address 10.0.0.1 255.255.255.255
 ip router isis 1
!
interface Ethernet0/2
 ip unnumbered Loopback0
 ip router isis 1
 isis network point-to-point
 no shutdown
```

| Line | Explanation |
|---|---|
| `ip address 10.0.0.1 ...` | The node address. It is also the prefix that gets the prefix SID. |
| `ip router isis 1` | Puts the interface in IS-IS |
| `ip unnumbered Loopback0` | The link has no address. It uses the loopback address. |
| `isis network point-to-point` | Uses the point-to-point IS-IS hello. No DIS election. |

### 6.4 PE and P: SR-MPLS and IS-IS

```
segment-routing mpls
 connected-prefix-sid-map
  address-family ipv4
   10.0.0.1/32 index 1 range 1
  exit-address-family
!
router isis 1
 net 49.0001.0000.0000.0001.00
 is-type level-2-only
 metric-style wide
 segment-routing mpls
```

| Line | Explanation |
|---|---|
| `segment-routing mpls` (global) | Turns on SR-MPLS on the router. The router uses the default SRGB 16000 to 23999. |
| `connected-prefix-sid-map` | Gives a prefix SID to a connected prefix |
| `10.0.0.1/32 index 1 range 1` | The loopback gets index 1. The label is 16000 + 1 = 16001. `range 1` means one prefix. |
| `net ...` | IS-IS address. `0000.0000.0001` is the system ID. |
| `segment-routing mpls` (IS-IS) | Tells IS-IS to advertise the SRGB and the prefix SID, and to program the labels |

The global block must come before the IS-IS command. If the order is wrong, IOS rejects the IS-IS command with the message `SR feature is not configured yet, please enable Segment-routing first.`

### 6.5 PE: CE-facing interface

```
interface Ethernet0/1
 vrf forwarding CE-RTR1
 ip address 10.1.1.2 255.255.255.252
 no shutdown
```

`vrf forwarding` puts the interface in the customer VRF. Enter it before the IP address, because the command removes an existing address.

### 6.6 PE: BGP

```
router bgp 65001
 bgp router-id 10.0.0.1
 no bgp default ipv4-unicast
 neighbor 10.0.0.2 remote-as 65001
 neighbor 10.0.0.2 update-source Loopback0
 address-family vpnv4
  neighbor 10.0.0.2 activate
  neighbor 10.0.0.2 send-community extended
 address-family ipv4 vrf CE-RTR1
  neighbor 10.1.1.1 remote-as 65250
  neighbor 10.1.1.1 activate
```

| Line | Explanation |
|---|---|
| `neighbor 10.0.0.2 ...` | iBGP to the other PE, over the loopback |
| `address-family vpnv4` | The session carries VPNv4 routes |
| `send-community extended` | Sends the route target |
| `address-family ipv4 vrf CE-RTR1` | Runs the eBGP session to the CE inside the VRF |

Compared with the SRv6 lab, the VRF address family has no `segment-routing srv6` block. The VPN label mode is a global command (section 6.2).

### 6.6.1 P router

A P router has the same core configuration as a PE (sections 6.3 and 6.4). It has no VRF, no BGP, and no CE-facing interface. It has three core interfaces.

### 6.7 CE: IPsec and tunnel

The CE configuration is the same as in `lab-srv6`, except for the pre-shared key.

```
crypto isakmp policy 10
 encryption aes 256
 hash sha256
 authentication pre-share
 group 14
crypto isakmp key srmpls-lab-psk address 172.21.1.1
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

### 6.8 CE: eBGP and routes

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

### 6.9 Host

```
vrf definition MGMT
interface Ethernet0/0
 vrf forwarding MGMT
 ip address 172.100.211.11 255.255.255.0
interface Ethernet0/1
 ip address 192.168.1.10 255.255.255.0
ip route 0.0.0.0 0.0.0.0 192.168.1.1
```

### 6.10 Differences between the nodes

| Item | Value that changes |
|---|---|
| Mgmt IP | `172.100.211.<11..20>` |
| Loopback, NET, and prefix-SID index | Node number `<n>` (section 4) |
| PE-CE subnet and AS | Site 1: `10.1.1/30`, AS 65250. Site 2: `10.2.2/30`, AS 65351. |
| BGP neighbor of the PE | The other PE loopback |
| P interfaces | `Ethernet0/1`, `0/2`, `0/3` (all core) |
| PE interfaces | `Ethernet0/1` (CE), `0/2` and `0/3` (core) |

## 7. Forwarding model

### 7.1 Route to labels: how the PE chooses the encapsulation

Observed on `pe-rtr-1`:

```
pe-rtr-1#show ip cef vrf CE-RTR1 172.21.1.1/32 detail
172.21.1.1/32, epoch 0, flags [rib defined all labels]
  recursive via 10.0.0.2 label 18
    nexthop 10.0.0.11 Ethernet0/2 label 16002-(local:16002)
    nexthop 10.0.0.13 Ethernet0/3 label 16002-(local:16002)

pe-rtr-1#show ip cef 10.0.0.2 detail
10.0.0.2/32, epoch 0, per-destination sharing
  sr local label info: global/16002 [0x1B]
  nexthop 10.0.0.11 Ethernet0/2 label 16002-(local:16002)
  nexthop 10.0.0.13 Ethernet0/3 label 16002-(local:16002)
```

The output has two levels of lookup:

1. The customer prefix `172.21.1.1/32` points to the BGP next hop `10.0.0.2` and the VPN label 18.
2. The next hop `10.0.0.2` has the prefix-SID label 16002. It has two ECMP next hops: `Ethernet0/2` to P1 and `Ethernet0/3` to P3.

The PE pushes the VPN label first (bottom of stack). It then pushes the transport label 16002 (top of stack).

### 7.2 Label stack

| Position | Label | Meaning | Made by |
|---|---|---|---|
| Top | 16002 | Transport: go to `pe-rtr-2` | IS-IS SR |
| Bottom (S bit set) | 18 | VPN: use VRF `CE-RTR1` on `pe-rtr-2` | BGP VPNv4 |

Each MPLS label has 4 bytes: label (20 bits), traffic class (3 bits), bottom-of-stack bit (1 bit), and TTL (8 bits). Two labels add 8 bytes to the packet.

### 7.3 What the P routers do

A P router looks only at the top label. It does not look at the VPN label or at the IPv4 packet.

- **Swap.** The label is for a remote node that is not a direct neighbor. The router replaces the label with the label that the next hop expects. In SR-MPLS with the same SRGB on all nodes, the new label has the same value (16002 to 16002). The router decrements the label TTL.
- **Pop (PHP).** The next hop is the node that owns the prefix. The router removes the transport label and sends the packet. The next router sees the VPN label at the top.

Observed on `core-p-rtr-4` (its neighbor is `pe-rtr-2`):

```
16001      16001      10.0.0.1/32      0             Et0/2      10.0.0.11
16002      Pop Label  10.0.0.2/32      51182         Et0/3      10.0.0.2
```

A P router keeps no customer state. It needs no VRF and no BGP.

### 7.4 What the egress PE does

The packet arrives at `pe-rtr-2` with only the VPN label 18 (the transport label is gone after PHP). The router does these steps:

1. Find label 18 in the LFIB: `IPv4 VRF[V]`, `aggregate/CE-RTR1`.
2. Remove the label.
3. Look up the inner IPv4 destination in VRF `CE-RTR1`.
4. Forward the packet to the CE (`10.2.2.1` on `Ethernet0/1`).

Observed on `pe-rtr-2`:

```
18         No Label   IPv4 VRF[V]      50226         aggregate/CE-RTR1
```

### 7.5 Concept: an explicit label stack

This lab does not use this function. It is important to know for SR-MPLS.

A prefix SID is global. A sender can push more than one node label to force a path. To go through P3 and P2 to reach PE2, a PE can push this stack (top first):

```
16013   16012   16002   18
 P3      P2      PE2    VPN
```

Each router pops the top label when the packet arrives at the node that owns it. The next label is then the top label, and the router forwards the packet toward that node. In this lab, the shortest path is enough. The stack has only the transport label 16002 and the VPN label 18.

## 8. Packet walk

### 8.1 Test flow

`host1` sends an ICMP echo request to `host2`:

```
host1# ping 192.168.2.10
```

The capture tool is `tcpdump` in the container `wbitt/network-multitool`. Each capture uses the network namespace of the node. See section 9.2.

The tables below use one real test. The path can be different in your test (section 3.4).

### 8.2 Forward direction: host1 to host2

Observed path: `host1` > `ipsec-rtr1` > `pe-rtr-1` > `core-p-rtr-3` > `core-p-rtr-4` > `pe-rtr-2` > `ipsec-rtr2` > `host2`.

| Step | Where | What happens | Packet on the wire after this step |
|---|---|---|---|
| 1 | `host1` Et0/1 | The host uses its default route. It sends the packet to the CE. | IPv4 `192.168.1.10 > 192.168.2.10`, ICMP echo request |
| 2 | `ipsec-rtr1` | The CE looks up `192.168.2.10`. The static route points to `Tunnel100`. The CE adds a GRE header. IPsec then encrypts the GRE packet in ESP. | IPv4 `172.20.1.1 > 172.21.1.1`, protocol 50 (ESP), IP length 188 |
| 3 | `ipsec-rtr1` Et0/1 to `pe-rtr-1` Et0/1 | The CE uses its BGP route to `172.21.1.1` (next hop `10.1.1.2`). The ESP packet leaves on the PE-CE link. | Same as step 2, TTL 255 |
| 4 | `pe-rtr-1` | The packet arrives in VRF `CE-RTR1`. The PE decrements the IPv4 TTL. It pushes the VPN label 18 and the transport label 16002. It chooses `Ethernet0/3` (ECMP). | Labels `[16002, 18]`, then IPv4 ESP with TTL 254. Both labels have TTL 254 (observed at the first P router). |
| 5 | `core-p-rtr-3` | The P router finds label 16002 in the LFIB. It swaps 16002 to 16002. It decrements the label TTL. It chooses `Ethernet0/2` (ECMP). | Labels `[16002, 18]`, label TTL 254 (seen on arrival) |
| 6 | `core-p-rtr-4` | The next hop is `pe-rtr-2`, the owner of 16002. The router pops the transport label (PHP). It decrements the TTL. It sends the packet on `Ethernet0/3`. | Label `[18]` only. Label TTL 252 at `pe-rtr-2`. |
| 7 | `pe-rtr-2` | Label 18 is the local VRF label. The PE removes it. It looks up `172.21.1.1` in VRF `CE-RTR1`. It sends the packet to the CE. | IPv4 `172.20.1.1 > 172.21.1.1`, ESP, TTL 254 |
| 8 | `ipsec-rtr2` | The CE decrypts the ESP packet. It removes the GRE header. The packet arrives on `Tunnel100`. The CE looks up `192.168.2.10` and sends the packet to the LAN. | IPv4 `192.168.1.10 > 192.168.2.10`, ICMP echo request |
| 9 | `host2` | The host receives the echo request. It sends an echo reply. | |

Numbers that show the header size:

- The IPv4 ESP packet has 188 bytes at the IP layer (steps 2, 3, 7).
- With two labels, the packet has 196 bytes on the core links (steps 4, 5). This is 8 bytes more.
- With one label, the packet has 192 bytes on the last core link (step 6). This is 4 bytes more.

Two TTL facts:

- The IPv4 TTL of the ESP packet is 254 in the core. It does not change between `pe-rtr-1` and `pe-rtr-2`. Only the label TTL changes in the core.
- The customer traceroute does not show the core routers. The customer sees `192.168.1.1`, then `172.30.1.2`, then `192.168.2.10`.

### 8.3 Return direction: host2 to host1

The return packet follows the same steps in reverse. The core path can be different because each router uses its own hash. Observed return path: `pe-rtr-2` > `core-p-rtr-2` > `core-p-rtr-1` > `pe-rtr-1`.

| Step | Where | Packet |
|---|---|---|
| 1 | `host2` to `ipsec-rtr2` | IPv4 `192.168.2.10 > 192.168.1.10`, ICMP echo reply |
| 2 | `ipsec-rtr2` to `pe-rtr-2` | IPv4 `172.21.1.1 > 172.20.1.1`, ESP |
| 3 | `pe-rtr-2` (push) | Labels `[16001, 18]`, inner TTL 254 |
| 4 | `core-p-rtr-2` | Swap 16001 to 16001. Label TTL 254 on arrival. |
| 5 | `core-p-rtr-1` | The next hop is `pe-rtr-1`, the owner of 16001. Pop (PHP). Label TTL 253 on arrival. |
| 6 | `pe-rtr-1` | Label `[18]` only, label TTL 252. The PE removes it and looks up the VRF. |
| 7 | `ipsec-rtr1` | The CE decrypts the packet and sends the echo reply to `host1` |

The two directions use different SPI values. Example: `0xc0ddee4f` (CE1 to CE2) and `0x8f88b99c` (CE2 to CE1).

### 8.4 Capture evidence (observed)

These lines come from one test on 2026-09-21. The `length` value includes a 20-byte capture header. Subtract 20 to get the packet size.

Between `pe-rtr-1` and the CE (ESP, IPv4, no label):

```
IP (tos 0x0, ttl 255, proto ESP (50), length 188) 172.20.1.1 > 172.21.1.1: ESP(spi=0xc0ddee4f,seq=0xdd)
```

In the core, forward direction:

```
core-p-rtr-3  eth1  MPLS, length 216: MPLS (label 16002, tc 0, ttl 254)
                                       (label 18, tc 0, [S], ttl 254)
                                       IPv4 (ttl 254, proto ESP) 172.20.1.1 > 172.21.1.1: ESP(spi=0xc0ddee4f)
core-p-rtr-4  eth1  MPLS, length 216: MPLS (label 16002, tc 0, ttl 253)
                                       (label 18, tc 0, [S], ttl 254)
                                       IPv4 (ttl 254, proto ESP) 172.20.1.1 > 172.21.1.1: ESP(spi=0xc0ddee4f)
pe-rtr-2      eth3  MPLS, length 212: MPLS (label 18, tc 0, [S], ttl 252)
                                       IPv4 (ttl 254, proto ESP) 172.20.1.1 > 172.21.1.1: ESP(spi=0xc0ddee4f)
```

In the core, return direction:

```
core-p-rtr-2  eth3  MPLS, length 216: MPLS (label 16001, tc 0, ttl 254) (label 18, tc 0, [S], ttl 254) IPv4 ESP 172.21.1.1 > 172.20.1.1
core-p-rtr-1  eth2  MPLS, length 216: MPLS (label 16001, tc 0, ttl 253) (label 18, tc 0, [S], ttl 254) IPv4 ESP 172.21.1.1 > 172.20.1.1
pe-rtr-1      eth2  MPLS, length 212: MPLS (label 18, tc 0, [S], ttl 252) IPv4 ESP 172.21.1.1 > 172.20.1.1
```

The captures show:

- The top label stays 16002 (or 16001) on all core hops (swap to the same value).
- The VPN label 18 does not change in the core.
- The transport label is gone on the last core link (PHP).
- The inner IPv4 TTL stays 254.
- The VPN label keeps TTL 254 while it is under the transport label. The transport label TTL decreases at each hop (254, 253). After PHP, the VPN label is at the top. It shows TTL 252 at `pe-rtr-2`.

The captures on the core links also show short labeled frames with label 16001 or 16002, one label, and traffic class 6. They are not customer traffic. They are probably control traffic between the PE loopbacks (for example BGP keepalives). The lab did not decode them.

## 9. Hop-by-hop validation

Use this section to check each part of the design, in order. Each step has a command, the expected result, and the meaning. Log in with `ssh admin@clab-iol-srmpls-<node>`.

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
| 3 | IS-IS routes | Do the routers have the loopback routes? |
| 4 | SR-MPLS | Does each router have its prefix SID, and the labels of the other nodes? |
| 5 | BGP | Is the VPNv4 session up? |
| 6 | VPN route | Does the PE have the remote route with a VPN label? |
| 7 | FIB | Does the FIB push the correct labels? |
| 8 | PE-CE | Does the CE announce and learn the tunnel loopbacks? |
| 9 | IPsec | Are the security associations up? |
| 10 | End to end | Does the host ping work, and does the packet use the core? |

### 9.2 Packet capture method

The IOL containers do not have `tcpdump`. Attach a helper container to the namespace of a node:

```
docker run --rm --net container:clab-iol-srmpls-core-p-rtr-3 --cap-add NET_RAW \
  --entrypoint tcpdump wbitt/network-multitool -i any -nn -e -v -c 5 'not ip and not ip6 and not arp'
```

| Part | Meaning |
|---|---|
| `--net container:<name>` | Uses the network namespace of the node |
| `-i any` | Captures on all interfaces. The output shows `ethN` for each packet. |
| `not ip and not ip6 and not arp` | Shows the labeled frames. Look for `ethertype MPLS unicast (0x8847)`. |
| `esp` | Filter for ESP packets (IPv4, on the PE-CE links) |
| `icmp` | Filter for the plain ICMP packets on the LAN |
| `-Q in` | Shows only the received packets (one line per hop) |
| `-v` | Shows the full label stack |

The filter `mpls` does not work with `-i any`. Use the filter in the table. IS-IS frames can also appear in the output. Ignore them.

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

The IP Address column shows the loopback address of the neighbor. This is correct for unnumbered links.

Command: `show ip interface brief`. Expected: each core interface shows the loopback address (`10.0.0.<n>`).

### 9.4 Step 3: IS-IS routes

Command on `pe-rtr-1`:

```
show ip route isis
```

Expected: one `i L2` route for each remote loopback (`10.0.0.2`, `.11`, `.12`, `.13`, `.14`).

Observed (first path of each route):

```
i L2     10.0.0.2 [115/40] via 10.0.0.13, Ethernet0/3
i L2     10.0.0.11 [115/20] via 10.0.0.11, Ethernet0/2
i L2     10.0.0.12 [115/30] via 10.0.0.13, Ethernet0/3
i L2     10.0.0.13 [115/20] via 10.0.0.13, Ethernet0/3
i L2     10.0.0.14 [115/30] via 10.0.0.13, Ethernet0/3
```

| What to check | Meaning |
|---|---|
| Metric of `10.0.0.2` is 40 | Three links of metric 10 plus the loopback metric 10 |
| The next hop is a neighbor loopback | The core links are unnumbered |
| Routes with two next hops | ECMP. Use the full output to see them. |

To see the SR data that IS-IS holds, use `show isis rib`. Each route shows `prefix SID index`, the SRGB, and the label.

### 9.5 Step 4: SR-MPLS prefix SIDs and labels

Commands on each PE and P node:

```
show segment-routing mpls connected-prefix-sid-map ipv4
show isis segment-routing
show mpls forwarding-table
```

Expected for the prefix-SID map on `pe-rtr-1`:

```
PREFIX_SID_CONN_MAP ALGO_0
    Prefix/masklen   SID Type Range Flags SRGB
       10.0.0.1/32     1 Indx     1         Y
```

Expected for `show isis segment-routing`: `SR State:SR_ENABLED`, `SRGB Start:16000, Range:8000`, and `Address-family IPv4 unicast SR is configured`, `Operational state:Enabled`.

Expected for the LFIB (observed on `pe-rtr-1`):

```
Local      Outgoing   Prefix           Bytes Label   Outgoing   Next Hop
Label      Label      or Tunnel Id     Switched      interface
16         Pop Label  10.0.0.11-A      0             Et0/2      10.0.0.11
17         Pop Label  10.0.0.13-A      0             Et0/3      10.0.0.13
18         No Label   IPv4 VRF[V]      48540         aggregate/CE-RTR1
16002      16002      10.0.0.2/32      0             Et0/2      10.0.0.11
                      16002 ...                      Et0/3      10.0.0.13
16011      Pop Label  10.0.0.11/32     0             Et0/2      10.0.0.11
...
```

| What to check | Meaning |
|---|---|
| Own index in the prefix-SID map | The node advertises its prefix SID |
| Five remote prefix-SID labels (16001 to 16014, except the own label) | IS-IS SR works. `verify.py` checks this. |
| `Pop Label` for a neighbor prefix | PHP is on for that prefix |
| `IPv4 VRF[V]` entry (PE only) | The VPN label of the VRF |
| Adjacency labels marked `-A` | IS-IS made the adjacency SIDs |

A P router has the prefix-SID labels and the adjacency labels. It has no `IPv4 VRF[V]` entry.

### 9.6 Step 5: VPNv4 session

Command on `pe-rtr-1`:

```
show bgp vpnv4 unicast all summary
```

Expected: the neighbor `10.0.0.2` (AS 65001) has a number in the `State/PfxRcd` column (not `Idle` or `Active`). The neighbor `10.1.1.1` (AS 65250) also has a number.

If the session does not come up, ping the remote loopback: `ping 10.0.0.2 source Loopback0`. Then check step 3 and step 4. The session traffic uses the labels.

### 9.7 Step 6: VPN route with the label

Command on `pe-rtr-1`:

```
show bgp vpnv4 unicast all
show bgp vpnv4 unicast all 172.21.1.1/32
```

Expected: the route `172.21.1.1/32` has the next hop `10.0.0.2`, the route target `RT:65001:1`, and the line `mpls labels in/out nolabel/18`.

The out label must be equal to the VRF label in the LFIB of `pe-rtr-2` (`18 ... aggregate/CE-RTR1`, step 4). If the route has no label, check `mpls label mode ... per-vrf` on `pe-rtr-2`.

### 9.8 Step 7: VRF route and FIB

Commands on `pe-rtr-1`:

```
show ip route vrf CE-RTR1 bgp
show ip cef vrf CE-RTR1 172.21.1.1/32 detail
show ip cef 10.0.0.2 detail
```

Expected in the route table: `B 172.21.1.1 [200/0] via 10.0.0.2`.

Expected in the CEF output:

- `recursive via 10.0.0.2 label 18` (the VPN label)
- `nexthop ... label 16002-(local:16002)` for each ECMP path (the transport label)
- `sr local label info: global/16002` for `10.0.0.2`

Then check the P routers. Command on each P router:

```
show mpls forwarding-table labels 16002
```

Expected: an entry for label 16002. It is a swap, or a `Pop Label` if the next hop is `pe-rtr-2`.

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
- The ping has a success rate of 100 percent. This ping crosses the SR-MPLS core without IPsec.

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

If the ISAKMP entry does not appear, the IKE packets do not cross the core. Go back to step 8.

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

1. Start a capture with the filter `not ip and not ip6 and not arp` on all four P routers and on both PE routers. See section 9.2.
2. Send a short ping from `host1` (`repeat 3`).
3. Read the captures. The routers that show labeled packets are on the path.
4. Check that the label TTL of the top label decreases by 1 on each router, and that the inner IPv4 TTL does not change.
5. Check that the transport label is gone on the last core link.

Use this table as the check list for one direction:

| Capture point | Filter | Expected packet |
|---|---|---|
| `ipsec-rtr1` `eth2` (LAN side) | `icmp` | Plain ICMP, `192.168.1.10 > 192.168.2.10` |
| `pe-rtr-1` `eth1` | `esp` | IPv4 ESP, `172.20.1.1 > 172.21.1.1`, TTL 255, no label |
| Each P router (ingress) | `not ip and not ip6 and not arp` | Labels `[16002, 18]`, top label TTL 1 lower on each hop |
| `pe-rtr-2` (ingress from the core) | `not ip and not ip6 and not arp` | Label `[18]` only (after PHP) |
| `pe-rtr-2` `eth1` | `esp` | IPv4 ESP, no label, TTL 254 |
| `ipsec-rtr2` `eth2` | `icmp` | Plain ICMP |

Also check the counters. The LFIB counts the bytes that each label entry switches. `verify.py` sums the column `Bytes Label Switched` on the P routers before and after the test:

```
show mpls forwarding-table
```

The counter of the entry for the label 16001 or 16002 increases on the P routers in the path.

### 9.12 Full test

`verify.py` runs 26 checks:

| Group | Checks |
|---|---|
| IS-IS | Adjacency count on 6 nodes |
| SR-MPLS | Own prefix SID and the five remote labels in the LFIB, on 6 nodes |
| BGP | VPNv4 session, remote route with VPN label, local VRF label in the LFIB, on 2 PE routers |
| IPsec | ISAKMP SA on 2 CE routers |
| Data plane | CE loopback ping, tunnel ping, IPsec counters |
| End to end | Ping in both directions, core byte counters |

Run it with `uv run verify.py`. The exit code is 0 when all checks pass.

## 10. Fault finding

| Symptom | Likely cause | How to check |
|---|---|---|
| No IS-IS neighbor | `ip unnumbered Loopback0` or `ip router isis 1` is missing. The interface is down. | `show isis neighbors`, `show ip interface brief` |
| No SR labels in the LFIB | `segment-routing mpls` is missing under IS-IS, or the global block is missing | `show isis segment-routing`, `show run \| section segment-routing` |
| IOS rejects `segment-routing mpls` under IS-IS | The global `segment-routing mpls` block is not configured yet | Configure the global block first (section 6.4) |
| A remote node has no label | The remote node has no `connected-prefix-sid-map` entry | `show isis rib`, `show segment-routing mpls connected-prefix-sid-map ipv4` on the remote node |
| Two nodes have the same label | Two nodes have the same index | `show isis rib` (look for two prefixes with one index) |
| No VPN label for the VRF | The label mode command is missing | `show ip vrf detail CE-RTR1` (must show `per-vrf (Label n)`) |
| VPNv4 session is `Idle` or `Active` | No route to the remote loopback. Wrong `update-source`. | `ping 10.0.0.2 source Loopback0` |
| VPNv4 route has no `out` label | The remote PE has no label for the VRF | `show bgp vpnv4 unicast all <prefix>` on both PE routers |
| Remote route is missing in the VRF, session is up | The route target does not match | `show ip vrf detail CE-RTR1` on both PE routers (section 5.8.6) |
| Sending PE has the route, receiving PE has none, session is up | The export RT on the sending PE does not match the import RT on the receiving PE | `neighbors 10.0.0.1 routes` on the receiving PE (0 prefixes), `show ip vrf detail CE-RTR1` on both PE routers (section 5.8.4) |
| Route in the VRF, but ping fails | The FIB has no label path. The core has no label for the next hop. | `show ip cef vrf CE-RTR1 <prefix> detail`, `show mpls forwarding-table labels <label>` on each P router |
| Packet leaves the PE but does not arrive | A P router has no LFIB entry for the top label, or the label TTL is 0 | Capture on each hop (section 9.11) |
| ISAKMP does not start | Loopback ping fails, or the pre-shared keys are different | `ping 172.21.1.1 source 172.20.1.1`, `show crypto isakmp sa` |
| Host ping works, but no core traffic | The host management port carries the traffic (no `MGMT` VRF) | `show ip arp` on the host |
| SSH to a node fails | The node is still in boot (about 2 minutes) | `docker logs clab-iol-srmpls-<node>` |

## 11. Lab limits

- **IOL cannot change the MTU.** The interface MTU is 1500 bytes. The GRE, ESP, and MPLS headers add bytes. The lab uses `ip tcp adjust-mss 1360` to prevent TCP fragmentation. Large non-TCP packets can be fragmented.
- **The lab has only one VRF and one route target.** It does not show route-target filtering (except in the exercise).
- **The lab has no traffic engineering.** Each packet uses the shortest path. The lab does not use an explicit label stack (section 7.5), TI-LFA, or SR policy.
- **The hash decides the ECMP path.** A path can change between tests.
- **Traffic to a loopback uses labels.** Traffic from one PE loopback to another follows the same label paths as the customer traffic. The core links have no IP address, so this traffic uses the loopback addresses.
- **The pre-shared key is in the configuration in clear text.** This is a lab setting.
- **The hosts are IOL routers.** They are not Linux hosts.
- **Adjacency labels can change.** They come from the dynamic pool. A redeploy can give other values.

## 12. Quick command list

| Purpose | Command | Node |
|---|---|---|
| IS-IS neighbors | `show isis neighbors` | Core |
| IS-IS IPv4 routes | `show ip route isis` | Core |
| IS-IS routes with SR data | `show isis rib` | Core |
| SR state and SRGB | `show isis segment-routing` | PE, P |
| Own prefix SID | `show segment-routing mpls connected-prefix-sid-map ipv4` | PE, P |
| Label table (LFIB) | `show mpls forwarding-table` | PE, P |
| One label | `show mpls forwarding-table labels <label>` | PE, P |
| MPLS interfaces | `show mpls interfaces` | PE, P |
| VPNv4 sessions | `show bgp vpnv4 unicast all summary` | PE |
| VPNv4 routes | `show bgp vpnv4 unicast all` | PE |
| One VPNv4 route with the VPN label | `show bgp vpnv4 unicast all <prefix>` | PE |
| VRF routes | `show ip route vrf CE-RTR1` | PE |
| VRF settings and VPN label | `show ip vrf detail CE-RTR1` | PE |
| Labels in the FIB for a VRF prefix | `show ip cef vrf CE-RTR1 <prefix> detail` | PE |
| Labels in the FIB for a loopback | `show ip cef <loopback> detail` | PE, P |
| ISAKMP state | `show crypto isakmp sa` | CE |
| IPsec state and counters | `show crypto ipsec sa` | CE |
| Tunnel state | `show interfaces Tunnel100` | CE |
| Start the lab | `clab deploy -t lab-sr-mpls.clab.yml` | Host |
| Stop the lab | `clab destroy -t lab-sr-mpls.clab.yml --cleanup` | Host |

## 13. Related files

| File | Content |
|---|---|
| `COMPARE.md` | Side-by-side comparison with `lab-srv6` |
| `../lab-srv6/HLD.md` | HLD of the SRv6 lab (same structure as this file) |
| `../lab-srv6/LAB_Access.MD` | How to connect from Windows to the lab. Use the network `172.100.211.0/24` for this lab. |
