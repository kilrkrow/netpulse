"""Builds a controller wired to a simulated scenario and fast-forwards its history."""

from __future__ import annotations

from typing import Optional

from core.rc.controller import RcController
from core.rc.db import Database
from core.rc.settings import SettingsStore
from core.rc.sim import SIM_TARGET, Scenario, SimClock, SimProber, sim_route


def build_sim_controller(scenario: Scenario, settings: SettingsStore, db: Database, version: str,
                         start_epoch: Optional[float] = None, **kwargs) -> RcController:
    import time
    now = start_epoch if start_epoch is not None else time.time()
    clock = SimClock(now - scenario.history_s)
    prober = SimProber(scenario, clock, origin=now)
    settings.value.target = SIM_TARGET
    ctl = RcController(settings, db, prober, version, clock=clock.time, route_fn=sim_route,
                       simulate=True, **kwargs)
    ctl.sim_clock = clock
    # Fast-forward: one engine cycle per simulated second, no sleeping.
    on_update, ctl.on_update = ctl.on_update, None
    ctl.store.recover_interrupted()
    for _ in range(scenario.history_s):
        ctl.engine.run_once()
        clock.advance(1.0)
    ctl.on_update = on_update
    clock.go_live()
    return ctl
