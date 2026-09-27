# /// script
# dependencies = ["paramiko"]
# ///
"""Verify the SRv6 lab end to end. Usage: uv run verify.py"""
import re, sys
from cli import run

PES = ["pe-rtr-1", "pe-rtr-2"]
CORE = ["core-p-rtr-1", "core-p-rtr-2", "core-p-rtr-3", "core-p-rtr-4"]
EXPECT_ISIS = {"pe-rtr-1": 2, "pe-rtr-2": 2, **{p: 3 for p in CORE}}
PING_COUNT = 100
MIN_SUCCESS = 95
results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")


def core_pkts():
    """Sum of IPv6 packets forwarded across core P routers."""
    total = 0
    for p in CORE:
        o = run(p, ["show ipv6 traffic | include forwarded"])
        m = re.findall(r"(\d+) forwarded", o)
        total += int(m[0]) if m else 0
    return total


for n, want in EXPECT_ISIS.items():
    o = run(n, ["show isis neighbors"])
    check(f"IS-IS adjacencies {n}", len(re.findall(r"\bUP\b", o)) == want, f"(want {want})")
    o = run(n, ["show segment-routing srv6 locator"])
    check(f"SRv6 uSID locator {n}", "usid-f3216" in o and "Up" in o)

for pe in PES:
    o = run(pe, ["show bgp vpnv4 unicast all summary"])
    check(f"VPNv4 session {pe}", bool(re.search(r"2001:DB8:FFFF::\d\s+4\s+65001.*\s1\s*$", o.replace("\r", ""), re.M)))
    o = run(pe, ["show bgp vpnv4 unicast all"])
    check(f"remote VPNv4 route w/ SRv6 SID {pe}", "2001:DB8:FFFF::" in o)
    o = run(pe, ["show segment-routing srv6 sid"])
    check(f"local VRF uSID allocated {pe}", "CE-RTR1" in o or "E00" in o.upper())

for ce in ("ipsec-rtr1", "ipsec-rtr2"):
    o = run(ce, ["show crypto isakmp sa"])
    check(f"ISAKMP SA {ce}", o.count("QM_IDLE") >= 1)

before = core_pkts()
o = run("ipsec-rtr1", ["ping 172.21.1.1 source 172.20.1.1 repeat 20", "ping 172.30.1.2 repeat 20"])
check("CE loopback ping via VPNv4/SRv6", "Success rate is 100" in o.split("172.30.1.2")[0])
check("Tunnel100 ping", "Success rate is 100" in o.split("172.30.1.2")[-1])
o = run("ipsec-rtr1", ["show crypto ipsec sa | include encaps|decaps"])
enc = int(re.search(r"encaps: (\d+)", o).group(1)); dec = int(re.search(r"decaps: (\d+)", o).group(1))
check("IPsec encaps/decaps counters", enc > 0 and dec > 0, f"(encaps={enc} decaps={dec})")

for src, dst in (("host1", "192.168.2.10"), ("host2", "192.168.1.10")):
    o = run(src, [f"ping {dst} repeat {PING_COUNT}"])
    m = re.search(r"Success rate is (\d+) percent", o)
    check(f"{src} -> {dst}", bool(m) and int(m.group(1)) >= MIN_SUCCESS, f"({m.group(0) if m else 'no result'})")
after = core_pkts()
check("traffic traversed SRv6 core", after - before >= PING_COUNT, f"(+{after - before} IPv6 pkts forwarded by P routers)")

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
