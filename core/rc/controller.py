"""Ties the probe engine, verdict engine, outage tracker, settings and IP research together (no Qt)."""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional

from core.rc.db import Database
from core.rc.ipclass import lookup_allowed
from core.rc.ipinfo import IpReport, IpResearch
from core.rc.model import PathSnapshot, Verdict
from core.rc.outages import OutageStore, OutageTracker, build_report
from core.rc.probe import ProbeConfig, ProbeEngine, Prober
from core.rc.settings import SettingsStore
from core.rc.verdict import VerdictEngine


class RcController:
    def __init__(self, settings: SettingsStore, db: Database, prober: Prober, version: str,
                 clock: Callable[[], float] = time.time, route_fn=None, simulate: bool = False,
                 on_update: Optional[Callable[[PathSnapshot, Verdict], None]] = None,
                 on_outages_changed: Optional[Callable[[], None]] = None,
                 on_identified: Optional[Callable[[str], None]] = None,
                 http_get=None):
        self.settings = settings
        self.db = db
        self.version = version
        self.clock = clock
        self.simulate = simulate
        self.on_update = on_update
        self.on_identified = on_identified
        s = settings.value
        cfg = ProbeConfig(target=s.target, interval_s=s.interval_s, dish_lan_ip=s.dish_lan_ip)
        kwargs = {}
        if route_fn is not None:
            kwargs["route_fn"] = route_fn
        self.engine = ProbeEngine(prober, cfg, clock=clock,
                                  overrides_fn=lambda: self.settings.value.label_overrides,
                                  asn_fn=self._asn, on_snapshot=self._on_snapshot, **kwargs)
        self.verdicts = VerdictEngine()
        self.store = OutageStore(db)
        self.tracker = OutageTracker(self.store, on_change=on_outages_changed)
        self.research = IpResearch(db, **({"http_get": http_get} if http_get else {}))
        self.snapshot: Optional[PathSnapshot] = None
        self.verdict: Optional[Verdict] = None
        self._lock = threading.Lock()
        self._ident_tried = set()
        self._ident_busy = False

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        if not self.simulate:                  # a simulated run already recovered before its fast-forward
            self.store.recover_interrupted()
        self.engine.start()

    def stop(self) -> None:
        try:
            self.tracker.finish(self.clock())
        except Exception:
            pass
        self.engine.stop()

    # ------------------------------------------------------------------ pipeline
    def process(self, snap: PathSnapshot) -> Verdict:
        verdict = self.verdicts.evaluate(snap)
        with self._lock:
            self.snapshot, self.verdict = snap, verdict
        self.tracker.feed(verdict, snap)
        self._auto_identify(snap)
        if self.on_update:
            self.on_update(snap, verdict)
        return verdict

    def _on_snapshot(self, snap: PathSnapshot) -> None:
        self.process(snap)

    # ------------------------------------------------------------------ IP research
    def _asn(self, ip: str) -> Optional[int]:
        s = self.settings.value
        if not (s.lookups_allowed and s.auto_identify_hops):
            return None
        return self.research.cached_asn(ip)

    def _auto_identify(self, snap: PathSnapshot) -> None:
        """Resolve the owner (ASN) of public hops in the background so Starlink hops can be labeled.
        Only after the user accepted the lookup notice, and only for public addresses."""
        s = self.settings.value
        if self.simulate or not (s.lookups_allowed and s.auto_identify_hops) or self._ident_busy:
            return
        todo = [h.ip for h in snap.hops if h.ip and h.ttl >= 1 and h.ip not in self._ident_tried
                and lookup_allowed(h.ip)]
        if not todo:
            return
        self._ident_busy = True

        def work():
            try:
                for ip in todo:
                    self._ident_tried.add(ip)
                    if self.research.cached_asn(ip) is None:
                        self.research.lookup(ip)
                    if self.on_identified:
                        self.on_identified(ip)
            finally:
                self._ident_busy = False

        threading.Thread(target=work, name="np-ident", daemon=True).start()

    def lookup_ip(self, ip: str, force: bool = False) -> IpReport:
        return self.research.lookup(ip, force)

    # ------------------------------------------------------------------ report
    def report_text(self) -> str:
        with self._lock:
            snap, verdict = self.snapshot, self.verdict
        return build_report(verdict, snap, self.store.list(15), self.version, self.clock())
