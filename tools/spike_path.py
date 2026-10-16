"""SPIKE: hop discovery + live per-hop probing + a plain text diagram, on the real PC. No admin."""
import ctypes, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.rc.icmp import IcmpProber
from core.rc.probe import ProbeEngine, ProbeConfig
from core.rc.verdict import VerdictEngine

from core.rc.winutil import is_elevated as elevated

secs = int(sys.argv[1]) if len(sys.argv) > 1 else 25
target = sys.argv[2] if len(sys.argv) > 2 else "1.1.1.1"
print("process elevated:", elevated())
eng = ProbeEngine(IcmpProber(), ProbeConfig(target=target))
eng.start()
t0 = time.time()
ve = VerdictEngine()
snap = None
try:
    while time.time() - t0 < secs:
        time.sleep(2.0)
        snap = eng.snapshot()
        n = min((len(h.samples) for h in snap.hops if h.ttl >= 1), default=0)
        print(f"t+{time.time()-t0:4.1f}s samples/hop={n} mapped={snap.mapped} route_ok={snap.route_ok}")
finally:
    eng.stop()
snap = eng.snapshot()
v = ve.evaluate(snap)
print()
print("PATH (plain diagram)")
print("  [PC]", end="")
for h in snap.hops[1:]:
    print(f" --> [{h.segment.upper()} #{h.ttl}]", end="")
print()
print(f"  {'ttl':<4}{'segment':<10}{'address':<18}{'sent':>5}{'loss%':>7}{'avg ms':>9}{'min':>7}{'max':>7}{'jitter':>8}")
for h in snap.hops[1:]:
    st = h.stats()
    f = lambda x: "-" if x is None else f"{x:.1f}"
    print(f"  {h.ttl:<4}{h.segment:<10}{(h.ip or '*'):<18}{st.sent:>5}{st.loss_pct:>7.0f}{f(st.avg_rtt):>9}{f(st.min_rtt):>7}{f(st.max_rtt):>7}{f(st.jitter):>8}")
print()
print("VERDICT:", v.kind, "|", v.headline)
print(v.explanation)
out = os.environ.get("SPIKE_OUT")
if out:
    rec = {"target": snap.target, "gateway": snap.gateway_ip, "source": snap.source_ip,
           "hops": [{"ttl": h.ttl, "ip": h.ip, "segment": h.segment, "is_target": h.is_target,
                     "samples": [[round(s.ts - t0, 2), 1 if s.ok else 0, None if s.rtt_ms is None else round(s.rtt_ms, 2)] for s in h.samples]}
                    for h in snap.hops if h.ttl >= 1]}
    with open(out, "w") as fh:
        json.dump(rec, fh)
