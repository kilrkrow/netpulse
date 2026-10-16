"""Regenerates the simulated trace fixtures in this folder from core.rc.sim scenarios.

    python tests/fixtures/make_fixtures.py

Fixtures hold only simulated addresses: RFC1918, CGNAT, the documentation ranges 192.0.2.0/24,
198.51.100.0/24 and 203.0.113.0/24, and the public DNS target 1.1.1.1. The recorded fixture
(recorded_*.json) is a real trace taken on a dev PC with every address replaced by the same kind of
simulated address by tools/sanitize_trace.py; no home public IP or ISP-assigned address is kept.
"""

import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from core.rc.db import Database              # noqa: E402
from core.rc.settings import SettingsStore   # noqa: E402
from core.rc.sim import SCENARIOS            # noqa: E402
from core.rc.simrun import build_sim_controller  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def dump(name: str, snap, extra=None):
    t0 = snap.ts
    rec = {
        "name": name, "target": snap.target, "gateway": snap.gateway_ip, "source": snap.source_ip,
        "mapped": snap.mapped, "route_ok": snap.route_ok,
        "hops": [{
            "ttl": h.ttl, "ip": h.ip, "segment": h.segment, "is_target": h.is_target, "ever_ok": h.ever_ok,
            "total_sent": h.total_sent,
            "samples": [[round(s.ts - t0, 1), 1 if s.ok else 0, None if s.rtt_ms is None else round(s.rtt_ms, 1)]
                        for s in h.samples[-150:]],
        } for h in snap.hops if h.ttl >= 1],
    }
    if extra:
        rec.update(extra)
    with open(os.path.join(HERE, f"sim_{name}.json"), "w") as f:
        json.dump(rec, f, separators=(",", ":"))


def main():
    for name, sc in SCENARIOS.items():
        if name == "history":
            continue
        d = tempfile.mkdtemp()
        ctl = build_sim_controller(sc, SettingsStore(os.path.join(d, "s.json")), Database(os.path.join(d, "x.db")),
                                   "fixture", start_epoch=1_800_000_000.0)
        dump(name.replace("-", "_"), ctl.engine.snapshot())


if __name__ == "__main__":
    main()
