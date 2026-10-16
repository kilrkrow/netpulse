"""Load a JSON trace fixture into a PathSnapshot."""

import json
import os

from core.rc.model import SEG_PC, HopView, PathSnapshot, Sample

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def load_snapshot(name: str, now: float = 1_800_000_000.0) -> PathSnapshot:
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        rec = json.load(f)
    hops = [HopView(ttl=0, ip=rec.get("source"), segment=SEG_PC, label_source="fixed", ever_ok=True)]
    for h in rec["hops"]:
        hv = HopView(ttl=h["ttl"], ip=h["ip"], segment=h["segment"], is_target=h["is_target"],
                     ever_ok=h["ever_ok"], total_sent=h.get("total_sent", len(h["samples"])))
        for t, ok, rtt in h["samples"]:
            hv.samples.append(Sample(now + t, bool(ok), rtt, h["ip"] if ok else None, ""))
        hops.append(hv)
    return PathSnapshot(ts=now, target=rec["target"], hops=hops, route_ok=rec["route_ok"],
                        gateway_ip=rec["gateway"], source_ip=rec["source"], mapped=rec["mapped"],
                        started_ts=now - 200)


def make_trace(spec, n=60, now=1_800_000_000.0, target="1.1.1.1", mapped=True):
    """Build a snapshot from a compact spec: [(ttl, ip, segment, is_target, pattern)], where pattern is a
    function i -> (ok, rtt) for sample i (0 = oldest, n-1 = newest)."""
    hops = [HopView(ttl=0, ip="192.168.1.50", segment=SEG_PC, label_source="fixed", ever_ok=True)]
    for ttl, ip, seg, is_t, pat in spec:
        hv = HopView(ttl=ttl, ip=ip, segment=seg, is_target=is_t)
        for i in range(n):
            ok, rtt = pat(i)
            hv.samples.append(Sample(now - (n - 1 - i), ok, rtt if ok else None, ip if ok else None, ""))
        hv.total_sent = n
        hv.ever_ok = any(s.ok for s in hv.samples)
        hops.append(hv)
    return PathSnapshot(ts=now, target=target, hops=hops, route_ok=True, gateway_ip="192.168.1.1",
                        source_ip="192.168.1.50", mapped=mapped, started_ts=now - n)
