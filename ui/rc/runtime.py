"""Builds the root-cause controller (real or simulated) and bridges its worker-thread callbacks to Qt signals."""

from __future__ import annotations

import os
import sys
from typing import Optional

from PySide6.QtCore import QObject, Signal

from core.rc import paths
from core.rc.controller import RcController
from core.rc.db import Database
from core.rc.settings import SettingsStore
from core.rc.sim import SIM_TARGET, resolve_scenario


class RcBridge(QObject):
    updated = Signal(object, object)       # PathSnapshot, Verdict (emitted from the probe thread; queued to the GUI)
    outages_changed = Signal()
    identified = Signal(str)


def resource_path(rel: str) -> str:
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, rel)


class RcRuntime:
    def __init__(self, version: str, simulate: Optional[str] = None):
        self.version = version
        self.simulate = simulate
        self.scenario = resolve_scenario(simulate) if simulate else None
        if simulate and self.scenario is None:
            raise ValueError(f"unknown simulation scenario: {simulate}")
        sim = self.scenario is not None
        dbp, setp = paths.db_path(sim), paths.settings_path(sim)
        if sim and not os.environ.get("NETPULSE_SIM_KEEP"):
            for p in (dbp, dbp + "-wal", dbp + "-shm", setp):
                try:
                    os.remove(p)
                except OSError:
                    pass
        self.settings = SettingsStore(setp)
        self.db = Database(dbp)
        self.bridge = RcBridge()
        self.error = ""
        common = dict(on_update=self.bridge.updated.emit, on_outages_changed=self.bridge.outages_changed.emit,
                      on_identified=self.bridge.identified.emit)
        if sim:
            from core.rc.simrun import build_sim_controller
            self.ctl = build_sim_controller(self.scenario, self.settings, self.db, version, **common)
        else:
            from core.rc.icmp import IcmpProber, IcmpUnavailable
            try:
                prober = IcmpProber()
            except IcmpUnavailable as exc:
                prober = None
                self.error = str(exc)
            self.ctl = RcController(self.settings, self.db, prober, version, **common)

    @property
    def is_sim(self) -> bool:
        return self.scenario is not None

    def start(self) -> None:
        if self.error:
            return
        self.ctl.start()

    def stop(self) -> None:
        try:
            self.ctl.stop()
        finally:
            self.db.close() if hasattr(self.db, "close") else None

    def apply_settings(self) -> None:
        s = self.settings.value
        cfg = self.ctl.engine.cfg
        cfg.interval_s = s.interval_s
        cfg.dish_lan_ip = s.dish_lan_ip
        if not self.is_sim:
            self.ctl.engine.set_target(s.target)
