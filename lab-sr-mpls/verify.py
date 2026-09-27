# /// script
# dependencies = ["paramiko"]
# ///
"""Verify the SR-MPLS lab end to end. Usage: uv run verify.py"""
import re, sys
from cli import run

PES = ["pe-rtr-1", "pe-rtr-2"]
CORE = ["core-p-rtr-1", "core-p-rtr-2", "core-p-rtr-3", "core-p-rtr-4"]
NODE_IDX = {"pe-rtr-1": 1, "pe-rtr-2": 2, "core-p-rtr-1": 11, "core-p-rtr-2": 12,
            "core-p-rtr-3": 13, "core-p-rtr-4": 14}
EXPECT_ISIS = {"pe-rtr-1": 2, "pe-rtr-2": 2, **{p: 3 for p in CORE}}
SRGB_BASE = 16000
PING_COUNT = 100
MIN_SUCCESS = 95
MIN_BYTES_PER_PING = 100
results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")


def core_bytes():
    """Sum of 'Bytes Label Switched' in the LFIB of all P routers."""
    total = 0
    for p in CORE:
        o = run(p, ["show mpls forwarding-table"])
        for line in o.splitlines():
            m = re.match(r"^\s*(?:\d+\s+)?\S+\s+\S+.*?\s(\d+)\s+(?:Et\S+|aggregate\S*)\s", line)
            if m and ("/32" in line or "-A" in line):
                total += int(m.group(1))
    return total


for n, want in EXPECT_ISIS.items():
    o = run(n, ["show isis neighbors"])
    check(f"IS-IS adjacencies {n}", len(re.findall(r"\bUP\b", o)) == want, f"(want {want})")
    o = run(n, ["show segment-routing mpls connected-prefix-sid-map ipv4", "show mpls forwarding-table"])
    mine = NODE_IDX[n]
    others = [i for j, i in NODE_IDX.items() if j != n]
    labels_ok = all(str(SRGB_BASE + i) in o for i in others)
    check(f"SR-MPLS prefix-SID {n}", f"{mine} Indx" in o and labels_ok, f"(own index {mine}, {len(others)} remote labels in LFIB)")

for pe in PES:
    o = run(pe, ["show bgp vpnv4 unicast all summary"])
    check(f"VPNv4 session {pe}", bool(re.search(r"10\.0\.0\.\d\s+4\s+65001.*\s1\s*$", o.replace("\r", ""), re.M)))
    o = run(pe, ["show bgp vpnv4 unicast all 172.20.1.1/32" if pe == "pe-rtr-2" else "show bgp vpnv4 unicast all 172.21.1.1/32"])
    check(f"remote VPNv4 route w/ VPN label {pe}", bool(re.search(r"mpls labels in/out \S+/\d+", o)))
    o = run(pe, ["show mpls forwarding-table"])
    check(f"local VRF label in LFIB {pe}", "aggregate/CE-RTR1" in o)

for ce in ("ipsec-rtr1", "ipsec-rtr2"):
    o = run(ce, ["show crypto isakmp sa"])
    check(f"ISAKMP SA {ce}", o.count("QM_IDLE") >= 1)

before = core_bytes()
o = run("ipsec-rtr1", ["ping 172.21.1.1 source 172.20.1.1 repeat 20", "ping 172.30.1.2 repeat 20"])
check("CE loopback ping via VPNv4/SR-MPLS", "Success rate is 100" in o.split("172.30.1.2")[0])
check("Tunnel100 ping", "Success rate is 100" in o.split("172.30.1.2")[-1])
o = run("ipsec-rtr1", ["show crypto ipsec sa | include encaps|decaps"])
enc = int(re.search(r"encaps: (\d+)", o).group(1)); dec = int(re.search(r"decaps: (\d+)", o).group(1))
check("IPsec encaps/decaps counters", enc > 0 and dec > 0, f"(encaps={enc} decaps={dec})")

for src, dst in (("host1", "192.168.2.10"), ("host2", "192.168.1.10")):
    o = run(src, [f"ping {dst} repeat {PING_COUNT}"])
    m = re.search(r"Success rate is (\d+) percent", o)
    check(f"{src} -> {dst}", bool(m) and int(m.group(1)) >= MIN_SUCCESS, f"({m.group(0) if m else 'no result'})")
after = core_bytes()
check("traffic traversed SR-MPLS core", after - before >= PING_COUNT * MIN_BYTES_PER_PING, f"(+{after - before} bytes label-switched by P routers)")

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
