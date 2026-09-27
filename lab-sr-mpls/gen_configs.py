"""Generate startup configs for the SR-MPLS lab. Run: uv run gen_configs.py

Same topology, nodes, addressing and customer side as lab-srv6.
Only the provider core differs: IPv4 IS-IS + SR-MPLS (prefix SIDs) instead of IPv6 IS-IS + SRv6 uSID.
"""
from pathlib import Path

OUT = Path(__file__).parent / "configs"
MGMT_NET = "172.100.211"
MGMT_GW = f"{MGMT_NET}.1"
WINDOWS_NET = "172.19.0.0 255.255.0.0"  # WSL2 vEthernet subnet, for PuTTY access from Windows
PE_AS = 65001
PSK = "srmpls-lab-psk"
SRGB_BASE = 16000  # IOS-XE default SRGB 16000-23999; label = base + prefix-SID index

MGMT = {"host1": 11, "ipsec-rtr1": 12, "pe-rtr-1": 13, "core-p-rtr-1": 14,
        "core-p-rtr-2": 15, "core-p-rtr-3": 16, "core-p-rtr-4": 17,
        "pe-rtr-2": 18, "ipsec-rtr2": 19, "host2": 20}
CORE = {"pe-rtr-1": 1, "core-p-rtr-1": 11, "core-p-rtr-2": 12, "core-p-rtr-3": 13,
        "core-p-rtr-4": 14, "pe-rtr-2": 2}
# core interfaces: unnumbered (borrow Loopback0), the IPv4 equivalent of "link-local only"
CORE_IF = {
    "pe-rtr-1": ["Ethernet0/2", "Ethernet0/3"],
    "core-p-rtr-1": ["Ethernet0/1", "Ethernet0/2", "Ethernet0/3"],
    "core-p-rtr-2": ["Ethernet0/1", "Ethernet0/2", "Ethernet0/3"],
    "core-p-rtr-3": ["Ethernet0/1", "Ethernet0/2", "Ethernet0/3"],
    "core-p-rtr-4": ["Ethernet0/1", "Ethernet0/2", "Ethernet0/3"],
    "pe-rtr-2": ["Ethernet0/2", "Ethernet0/3"],
}


def base(name):
    return f"""hostname {name}
!
username admin privilege 15 secret admin
ip domain name lab.local
ip ssh version 2
crypto key generate rsa modulus 2048
!
interface Ethernet0/0
 description mgmt
 ip address {MGMT_NET}.{MGMT[name]} 255.255.255.0
 no shutdown
!
line vty 0 4
 login local
 transport input ssh
!
ip route {WINDOWS_NET} {MGMT_GW}
!
"""


def core(name):
    n = CORE[name]
    is_pe = name.startswith("pe-")
    cfg = base(name)
    if is_pe:
        vrf = "CE-RTR1"
        cfg += f"""vrf definition {vrf}
 rd {PE_AS}:1
 route-target export {PE_AS}:1
 route-target import {PE_AS}:1
 address-family ipv4
 exit-address-family
!
mpls label mode all-vrfs protocol bgp-vpnv4 per-vrf
!
"""
    # The global SR block must come before "segment-routing mpls" under IS-IS, or IOS rejects it.
    cfg += f"""interface Loopback0
 ip address 10.0.0.{n} 255.255.255.255
 ip router isis 1
!
"""
    for i in CORE_IF[name]:
        cfg += f"""interface {i}
 description core link (unnumbered)
 ip unnumbered Loopback0
 ip router isis 1
 isis network point-to-point
 no shutdown
!
"""
    cfg += f"""segment-routing mpls
 connected-prefix-sid-map
  address-family ipv4
   10.0.0.{n}/32 index {n} range 1
  exit-address-family
!
router isis 1
 net 49.0001.0000.0000.{n:04d}.00
 is-type level-2-only
 metric-style wide
 segment-routing mpls
!
"""
    if is_pe:
        peer = 2 if n == 1 else 1
        ce_as = 65250 if n == 1 else 65351
        ce_net = "10.1.1" if n == 1 else "10.2.2"
        cfg += f"""interface Ethernet0/1
 description to CE
 vrf forwarding {vrf}
 ip address {ce_net}.2 255.255.255.252
 no shutdown
!
router bgp {PE_AS}
 bgp router-id 10.0.0.{n}
 bgp log-neighbor-changes
 no bgp default ipv4-unicast
 neighbor 10.0.0.{peer} remote-as {PE_AS}
 neighbor 10.0.0.{peer} update-source Loopback0
 !
 address-family vpnv4
  neighbor 10.0.0.{peer} activate
  neighbor 10.0.0.{peer} send-community extended
 exit-address-family
 !
 address-family ipv4 vrf {vrf}
  neighbor {ce_net}.1 remote-as {ce_as}
  neighbor {ce_net}.1 activate
 exit-address-family
!
"""
    return cfg


def ce(n):
    name = f"ipsec-rtr{n}"
    my_as = 65250 if n == 1 else 65351
    lo = f"172.{20 if n == 1 else 21}.1.1"
    peer_lo = f"172.{21 if n == 1 else 20}.1.1"
    tun = f"172.30.1.{n}"
    pe_net = "10.1.1" if n == 1 else "10.2.2"
    lan = f"192.168.{n}"
    peer_lan = f"192.168.{3 - n}.0 255.255.255.0"
    return base(name) + f"""crypto isakmp policy 10
 encryption aes 256
 hash sha256
 authentication pre-share
 group 14
!
crypto isakmp key {PSK} address {peer_lo}
!
crypto ipsec transform-set TS esp-aes 256 esp-sha256-hmac
 mode tunnel
!
crypto ipsec profile IPSEC-PROF
 set transform-set TS
!
interface Loopback100
 description TUN-SRC
 ip address {lo} 255.255.255.255
!
interface Tunnel100
 ip address {tun} 255.255.255.252
 tunnel source Loopback100
 tunnel destination {peer_lo}
 tunnel protection ipsec profile IPSEC-PROF
 ip tcp adjust-mss 1360
!
interface Ethernet0/1
 description to PE
 ip address {pe_net}.1 255.255.255.252
 no shutdown
!
interface Ethernet0/2
 description LAN to host
 ip address {lan}.1 255.255.255.0
 no shutdown
!
router bgp {my_as}
 bgp router-id {lo}
 neighbor {pe_net}.2 remote-as {PE_AS}
 address-family ipv4
  network {lo} mask 255.255.255.255
  neighbor {pe_net}.2 activate
!
ip route {peer_lan} Tunnel100
!
"""


def host(n):
    """Host: mgmt in its own VRF so lab traffic can only use the data interface."""
    name = f"host{n}"
    cfg = base(name).replace(
        "interface Ethernet0/0\n description mgmt\n",
        "vrf definition MGMT\n address-family ipv4\n exit-address-family\n!\n"
        "interface Ethernet0/0\n description mgmt\n vrf forwarding MGMT\n")
    cfg = cfg.replace(f"ip route {WINDOWS_NET} {MGMT_GW}", f"ip route vrf MGMT {WINDOWS_NET} {MGMT_GW}")
    return cfg + f"""interface Ethernet0/1
 ip address 192.168.{n}.10 255.255.255.0
 no shutdown
!
ip route 0.0.0.0 0.0.0.0 192.168.{n}.1
!
"""


OUT.mkdir(exist_ok=True)
for name in CORE:
    (OUT / f"{name}.cfg").write_text(core(name))
for n in (1, 2):
    (OUT / f"ipsec-rtr{n}.cfg").write_text(ce(n))
    (OUT / f"host{n}.cfg").write_text(host(n))
print("ok")
