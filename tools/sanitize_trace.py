"""Turn a raw trace captured by the spike script into a safe fixture.

    python tools/sanitize_trace.py raw.json tests/fixtures/recorded_<name>.json

Every address is replaced by a simulated one of the same kind: the gateway and this PC become
192.168.1.1 / 192.168.1.50, other private hops 10.254.0.x, CGNAT hops 100.64.0.x, public hops
documentation-range addresses (198.51.100.x, 203.0.113.x, 192.0.2.x). Only the well-known public
DNS targets 1.1.1.1 / 8.8.8.8 are kept. Timestamps become seconds relative to the end of the trace.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.rc.ipclass import CAT_CGNAT, CAT_PRIVATE, classify_ip   # noqa: E402
from core.rc.labeler import label_path                             # noqa: E402
from core.rc.model import SEG_PC, HopView                          # noqa: E402

KEEP = {"1.1.1.1", "8.8.8.8", "8.8.4.4", "9.9.9.9"}
DOC = ["198.51.100", "203.0.113", "192.0.2"]


def main(src, dst):
    raw = json.load(open(src))
    mapping, counters = {}, {"priv": 0, "cgnat": 0, "pub": 0}

    def sim(ip):
        if ip is None or ip in KEEP:
            return ip
        if ip in mapping:
            return mapping[ip]
        if ip == raw.get("gateway"):
            out = "192.168.1.1"
        elif ip == raw.get("source"):
            out = "192.168.1.50"
        else:
            cat = classify_ip(ip)
            if cat == CAT_CGNAT:
                counters["cgnat"] += 1
                out = "100.64.0.1" if counters["cgnat"] == 1 else f"100.64.0.{counters['cgnat']}"
            elif cat == CAT_PRIVATE:
                counters["priv"] += 1
                out = f"10.254.0.{counters['priv']}"
            else:
                n = counters["pub"]
                counters["pub"] += 1
                out = f"{DOC[(n // 200) % 3]}.{n % 200 + 1}"
        mapping[ip] = out
        return out

    end = max((s[0] for h in raw["hops"] for s in h["samples"]), default=0.0)
    hops = []
    for h in raw["hops"]:
        hv = HopView(ttl=h["ttl"], ip=sim(h["ip"]), segment="internet", is_target=h["is_target"])
        hops.append((hv, h))
    views = [HopView(ttl=0, ip="192.168.1.50", segment=SEG_PC, label_source="fixed")] + [v for v, _ in hops]
    label_path(views, "192.168.1.1")
    out = {"name": os.path.basename(dst), "target": sim(raw["target"]), "gateway": "192.168.1.1",
           "source": "192.168.1.50", "mapped": True, "route_ok": True, "hops": []}
    for hv, h in hops:
        out["hops"].append({
            "ttl": hv.ttl, "ip": hv.ip, "segment": hv.segment, "is_target": hv.is_target,
            "ever_ok": any(s[1] for s in h["samples"]), "total_sent": len(h["samples"]),
            "samples": [[round(s[0] - end, 1), s[1], s[2]] for s in h["samples"]]})
    json.dump(out, open(dst, "w"), separators=(",", ":"))
    print("wrote", dst, "hops:", len(out["hops"]))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
