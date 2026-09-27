# SR-MPLS vs SRv6: Same Lab, Two Data Planes

`lab-sr-mpls` uses the same 10 nodes, the same 12 links and the same customer side as `lab-srv6`. Only the provider core changes. Use this file to compare the two labs. The full design is in `HLD.md` (this lab) and `../lab-srv6/HLD.md` (SRv6 lab).

**Source of the data.** "Observed" values come from running labs (IOS-XE 17.18.2, IOL). The SRv6 values come from `lab-srv6` and the SR-MPLS values from `lab-sr-mpls`. The ECMP path differs between tests. Compare the header sizes and the behavior, not the path.

## 1. What is the same and what is different

| Item | `lab-srv6` | `lab-sr-mpls` |
|---|---|---|
| Nodes, names, links, interface numbers | Same | Same |
| Customer side (hosts, CE routers, eBGP, IPsec, `Tunnel100`) | Same | Same |
| PE VRF, RD, RT | `CE-RTR1`, `65001:1` | Same |
| Core IGP | IS-IS level 2, IPv6 (multi-topology) | IS-IS level 2, IPv4 |
| Core link addressing | IPv6 link-local only (`ipv6 enable`) | IPv4 unnumbered (`ip unnumbered Loopback0`) |
| Core forwarding | IPv6 with SRv6 uSID | MPLS with SR-MPLS labels |
| Node identifier | Locator `FCBB:BB00:<n>::/48` | Prefix-SID index `<n>`, label `16000 + <n>` |
| Service identifier | `uDT4` SID in the IPv6 destination address | VPN label from BGP |
| BGP VPNv4 peering | IPv6 loopbacks (`2001:DB8:FFFF::<n>`) | IPv4 loopbacks (`10.0.0.<n>`) |
| Management network | 172.100.210.0/24 | 172.100.211.0/24 |
| Container prefix | `clab-iol-srv6-` | `clab-iol-srmpls-` |
| Verify script | 26 checks | 26 checks (same groups) |

Unnumbered IPv4 is the closest match to "link-local only". IS-IS forms adjacencies over the unnumbered links and shows the neighbor loopback address.

## 2. Core configuration side by side

PE `pe-rtr-1`, core part only.

| Purpose | SRv6 uSID | SR-MPLS |
|---|---|---|
| Core interface | `ipv6 enable`<br>`ipv6 router isis 1`<br>`isis network point-to-point` | `ip unnumbered Loopback0`<br>`ip router isis 1`<br>`isis network point-to-point` |
| Loopback | `ip address 10.0.0.1`<br>`ipv6 address 2001:DB8:FFFF::1/128` | `ip address 10.0.0.1` |
| Global SR block | `segment-routing srv6`<br>` encapsulation / source-address ...`<br>` locators / locator LOC1`<br>`  prefix FCBB:BB00:1::/48`<br>`  format usid-f3216` | `segment-routing mpls`<br>` connected-prefix-sid-map`<br>`  address-family ipv4`<br>`   10.0.0.1/32 index 1 range 1` |
| IS-IS | `address-family ipv6`<br>` multi-topology`<br>` segment-routing srv6 / locator LOC1` | `segment-routing mpls` |
| VPN service in BGP | `segment-routing srv6`<br>` locator LOC1`<br>` alloc-mode per-vrf`<br>(under `address-family ipv4 vrf`) | `mpls label mode all-vrfs protocol bgp-vpnv4 per-vrf`<br>(global command) |
| BGP neighbor | `2001:DB8:FFFF::2` | `10.0.0.2` |

Config size (non-blank lines): `pe-rtr-1` 95 (SRv6) and 80 (SR-MPLS). `core-p-rtr-1` 70 (SRv6) and 55 (SR-MPLS). SR-MPLS is shorter here because the lab has no IPv6 addressing and no encapsulation source.

## 3. Identifiers

| Node | SRv6 (locator and SIDs) | SR-MPLS (prefix-SID label) |
|---|---|---|
| `pe-rtr-1` | `FCBB:BB00:1::/48` | 16001 (index 1) |
| `pe-rtr-2` | `FCBB:BB00:2::/48` | 16002 (index 2) |
| `core-p-rtr-1` | `FCBB:BB00:11::/48` | 16011 (index 11) |
| `core-p-rtr-2` | `FCBB:BB00:12::/48` | 16012 (index 12) |
| `core-p-rtr-3` | `FCBB:BB00:13::/48` | 16013 (index 13) |
| `core-p-rtr-4` | `FCBB:BB00:14::/48` | 16014 (index 14) |
| Adjacency (link) SIDs | `uA` `:<n>:E000::`, `E001::`, `E002::` (one per core interface) | Dynamic labels 16, 17, 18 (marked `-A` in `show mpls forwarding-table`) |
| VPN service on the PE | `uDT4` `FCBB:BB00:<n>:E002::` | Label 18 (`aggregate/CE-RTR1`) |

Both PE routers use the same value (`E002` and `18`) by chance. Each PE allocates its own value.

Notes:

- SRv6 prefix-SIDs are prefixes. One locator gives all the SIDs of a node. SR-MPLS uses one label per node, in the SRGB (16000 to 23999, the default).
- In SR-MPLS the VPN label 18 comes from the dynamic label pool. It is the same pool as the adjacency SIDs (16 and 17 on `pe-rtr-2`).

## 4. Control plane

| Step | SRv6 | SR-MPLS |
|---|---|---|
| IGP advertises the node identifier | SRv6 Locator TLV (locator, End SID, SID structure) | Prefix-SID sub-TLV (index, SRGB) |
| Router installs the transport path | IPv6 route to the locator `/48` (`I2`) | IPv4 route to the loopback `/32` plus a label entry in the LFIB |
| PE advertises the VPN service | BGP VPNv4 route with the `uDT4` SID (`srv6 out-sid`) | BGP VPNv4 route with the VPN label (`mpls labels in/out nolabel/18`) |
| BGP next hop | `2001:DB8:FFFF::2` | `10.0.0.2` |
| PE resolves the route | VRF route to SID, then IPv6 route to the locator | VRF route to next hop plus VPN label, then label 16002 to the neighbor |

Observed on `pe-rtr-1` for `172.21.1.1/32`:

```
SRv6:     recursive via FCBB:BB00:2:E002::
            recursive via FCBB:BB00:2::/48
              nexthop FE80::...  Ethernet0/2
              nexthop FE80::...  Ethernet0/3

SR-MPLS:  recursive via 10.0.0.2 label 18
            nexthop 10.0.0.11 Ethernet0/2 label 16002-(local:16002)
            nexthop 10.0.0.13 Ethernet0/3 label 16002-(local:16002)
```

Both labs use ECMP over the same four equal-cost paths. The cost is 30 to the SRv6 locator and 40 to the SR-MPLS loopback. The loopback route adds a metric of 10.

## 5. Data plane: one packet, hop by hop

The flow is `host1` to `host2`. The customer packet becomes an IPv4 ESP packet on `ipsec-rtr1` (188 bytes at the IP layer). The PE adds the core encapsulation.

### 5.1 SRv6 (observed path PE1, P3, P2, PE2)

| Hop | Packet in the core | Router action |
|---|---|---|
| `pe-rtr-1` | IPv6 `2001:DB8:FFFF::1 > FCBB:BB00:2:E002::`, next header 4, hop limit 64, then IPv4 ESP | Encapsulate. No SRH. |
| `core-p-rtr-3` | Same, hop limit 63 | Route lookup for `FCBB:BB00:2::/48`. Forward. |
| `core-p-rtr-2` | Same, hop limit 62 | Same |
| `pe-rtr-2` | Same | The destination matches the local `uDT4` SID. Remove the IPv6 header. Look up the VRF. |

### 5.2 SR-MPLS (observed path PE1, P3, P4, PE2)

| Hop | Packet in the core | Router action |
|---|---|---|
| `pe-rtr-1` | Label stack `[16002, 18]`, then IPv4 ESP | Push the VPN label 18 and the transport label 16002 |
| `core-p-rtr-3` | `[16002, 18]`, label TTL 254 | Swap 16002 to 16002. Forward. |
| `core-p-rtr-4` | `[16002, 18]`, label TTL 253 | Penultimate hop pop: remove 16002. Forward. |
| `pe-rtr-2` | `[18]`, label TTL 252 | Label 18 is the local VRF label (`aggregate/CE-RTR1`). Remove it. Look up the VRF. |

Observed on the return direction (`pe-rtr-2`, P2, P1, `pe-rtr-1`): the stack is `[16001, 18]` on the core links and `[18]` on the last link.

### 5.3 Differences

| Item | SRv6 | SR-MPLS |
|---|---|---|
| Overhead in the core (observed, IP layer, on a 188-byte ESP packet) | 40 bytes (228 total) | 8 bytes (196 total) with two labels. 4 bytes (192) on the last link after PHP. |
| What the P router does to the packet | Route lookup. Decrement hop limit. It does not change the packet otherwise. | Label swap (or pop at the penultimate hop). Decrement label TTL. |
| Penultimate hop pop | Not used. The egress PE removes the IPv6 header. | Used. `core-p-rtr-4` pops the transport label. |
| Hop counter in the core | IPv6 hop limit (64, 63, 62) | Label TTL (254, 253, 252) |
| Inner IPv4 TTL in the core | 254, unchanged | 254, unchanged |
| Identifier on the wire | IPv6 destination address | Label |
| Extra headers | None (one SID, no SRH) | None |

Observed: the inner IPv4 TTL of the ESP packet stays at 254 across the core in both labs.

## 6. State on the P routers

| Item | SRv6 (`core-p-rtr-1`) | SR-MPLS (`core-p-rtr-4`) |
|---|---|---|
| Customer routes | None | None |
| BGP | Not running | Not running |
| Forwarding table used for transit | IPv6 route table (locator routes `/48`) | LFIB (one entry per prefix-SID, plus one per adjacency) |
| Number of transit entries | One per node (5 remote locators) | One per node (5 remote labels), plus 3 adjacency labels |
| Extra protocol | None | None (no LDP, no RSVP) |

Observed LFIB on `core-p-rtr-4` (SR-MPLS): `16002 Pop Label 10.0.0.2/32` (penultimate hop), `16001 16001 10.0.0.1/32` (swap), and adjacency entries `16`, `17`, `18` with `Pop Label`.

## 7. Command map

| Question | SRv6 | SR-MPLS |
|---|---|---|
| IS-IS neighbors | `show isis neighbors` | `show isis neighbors` |
| Node identifiers | `show segment-routing srv6 locator`<br>`show segment-routing srv6 sid` | `show segment-routing mpls connected-prefix-sid-map ipv4`<br>`show isis segment-routing` |
| IS-IS routes | `show ipv6 route isis` | `show ip route isis`<br>`show isis rib` |
| Forwarding table on a P router | `show ipv6 route FCBB:BB00:2::` | `show mpls forwarding-table` |
| VPNv4 session | `show bgp vpnv4 unicast all summary` | Same |
| VPNv4 route and service ID | `show bgp vpnv4 unicast all <prefix>` (`srv6 out-sid`) | Same (`mpls labels in/out`) |
| PE forwarding for a VRF prefix | `show ip cef vrf CE-RTR1 <prefix> detail` | Same |
| Local service identifier | `show segment-routing srv6 sid` (`uDT4`) | `show mpls forwarding-table` (`aggregate/CE-RTR1`) |
| Core traffic counter | `show ipv6 traffic \| include forwarded` | `show mpls forwarding-table` (Bytes Label Switched) |
| Packet capture filter | `ip6 proto 4` | `not ip and not ip6 and not arp` (then look for `MPLS`) |

Capture method for both labs (IOL has no `tcpdump`):

```
docker run --rm --net container:clab-iol-srmpls-core-p-rtr-3 --cap-add NET_RAW \
  --entrypoint tcpdump wbitt/network-multitool -i any -nn -e -v -c 5 'not ip and not ip6 and not arp'
```

The `mpls` filter does not work with `-i any`. Use the filter above.

## 8. Run and test

```
cd ~/network-labs/IOL/lab-sr-mpls
clab deploy -t lab-sr-mpls.clab.yml        # wait about 2 minutes
uv run verify.py                            # 26 checks
uv run cli.py pe-rtr-1 "show mpls forwarding-table"
clab destroy -t lab-sr-mpls.clab.yml --cleanup
```

Management IPs are `172.100.211.11` to `.20` (same last octet as the SRv6 lab: `host1` .11, `ipsec-rtr1` .12, `pe-rtr-1` .13, P routers .14 to .17, `pe-rtr-2` .18, `ipsec-rtr2` .19, `host2` .20). SSH login is `admin` / `admin`. To use PuTTY from Windows, add a Windows route for `172.100.211.0/24` in the same way as in `../lab-srv6/LAB_Access.MD`. The nodes already have the return route to `172.19.0.0/16`.

Both labs can run at the same time. They use different management networks and container names.

## 9. Configuration notes from the build

- The global `segment-routing mpls` block must come before `segment-routing mpls` under `router isis`. Otherwise IOS rejects it with `SR feature is not configured yet`.
- IS-IS and SR-MPLS work over `ip unnumbered Loopback0` on IOL. The core links need no IPv4 address.
- No `mpls ip` or LDP is needed. IS-IS programs the labels.
- The VPN label is per VRF because of `mpls label mode all-vrfs protocol bgp-vpnv4 per-vrf`.
- Short labeled frames with one label and traffic class 6 also appear on the core links. They are probably control traffic between the PE loopbacks (for example BGP keepalives). The lab did not decode them.
