"""Simulation mode: scripted traces fed through the real probe engine, verdict engine and UI.

Hidden developer switch only (--simulate <scenario> or NETPULSE_SIMULATE=<scenario>); there is no
menu entry for it. Simulated hops use RFC1918, CGNAT and documentation addresses plus the public
DNS target 1.1.1.1; nothing here touches the network.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from core.rc.icmp import IP_REQ_TIMED_OUT, IP_SUCCESS, IP_TTL_EXPIRED_TRANSIT, EchoResult
from core.rc.netinfo import RouteInfo

SIM_SOURCE = "192.168.1.50"
SIM_GATEWAY = "192.168.1.1"
SIM_DISH_LAN = "192.168.100.1"
SIM_TARGET = "1.1.1.1"

# (address, normal round trip in ms). Hop 1 = gateway, hop 2 = dish side (CGNAT), then the internet.
SIM_PATH: List[Tuple[str, float]] = [
    (SIM_GATEWAY, 0.9),
    ("100.64.0.1", 27.0),
    ("198.51.100.1", 29.0),
    ("198.51.100.17", 31.0),
    ("203.0.113.9", 33.0),
    (SIM_TARGET, 35.0),
]


@dataclass
class Effect:
    kind: str                 # "down" | "loss" | "lat" | "hop-loss" | "silent" | "dish-lan-down"
    first_ttl: int            # the effect applies to this hop and every hop after it (except hop-loss/silent: only it)
    t0: float                 # scenario seconds relative to "now" (negative = in the past)
    t1: float                 # end (use 1e9 for "forever")
    value: float = 0.0        # loss probability, or added milliseconds


@dataclass
class Scenario:
    name: str
    title: str
    effects: List[Effect] = field(default_factory=list)
    history_s: int = 150      # seconds of simulated history generated at start-up


FOREVER = 1e9


def _s(name, title, effects, history_s=150):
    return Scenario(name, title, effects, history_s)


SCENARIOS: Dict[str, Scenario] = {s.name: s for s in [
    _s("healthy", "Healthy network", []),
    _s("gateway-outage", "Gateway outage: nothing past the router answers",
       [Effect("down", 1, -25, FOREVER)]),
    _s("dish-outage", "Dish outage: router fine, dish and everything past it silent",
       [Effect("down", 2, -25, FOREVER), Effect("dish-lan-down", 0, -25, FOREVER)]),
    _s("internet-outage", "Internet-side outage: router and dish fine, nothing past the dish",
       [Effect("down", 3, -25, FOREVER)]),
    _s("cant-tell", "Thin evidence: only the router and the target are visible, and the target stops answering",
       [Effect("silent", 2, -1e6, FOREVER), Effect("silent", 3, -1e6, FOREVER),
        Effect("silent", 4, -1e6, FOREVER), Effect("silent", 5, -1e6, FOREVER),
        Effect("down", 6, -25, FOREVER)], 150),
    _s("loss", "Packet loss starting on the dish link",
       [Effect("loss", 2, -40, FOREVER, 0.4)]),
    _s("latency", "Latency spike starting past the dish",
       [Effect("lat", 3, -20, FOREVER, 260.0)]),
    _s("ratelimit", "A router rate-limits ICMP replies: not a fault",
       [Effect("hop-loss", 4, -60, FOREVER, 0.5)]),
    _s("measuring", "Just launched: not enough probes yet", [], history_s=3),
    _s("history", "Healthy now, with three recorded outages in the past",
       [Effect("down", 2, -480, -450), Effect("down", 3, -330, -285), Effect("down", 1, -150, -138)],
       history_s=600),
]}

# Scenario aliases accepted on the command line.
ALIASES = {"dish": "dish-outage", "gateway": "gateway-outage", "internet": "internet-outage",
           "cant_tell": "cant-tell", "cantell": "cant-tell", "thin": "cant-tell", "rate-limit": "ratelimit"}


def resolve_scenario(name: str) -> Optional[Scenario]:
    key = (name or "").strip().lower()
    key = ALIASES.get(key, key)
    return SCENARIOS.get(key)


class SimClock:
    """Virtual epoch clock: can be stepped during pre-fill, then follows real time."""

    def __init__(self, start: Optional[float] = None):
        self._v = start if start is not None else time.time()
        self._live_from: Optional[float] = None

    def time(self) -> float:
        if self._live_from is None:
            return self._v
        return self._v + (time.monotonic() - self._live_from)

    def advance(self, dt: float) -> None:
        self._v += dt

    def go_live(self) -> None:
        self._live_from = time.monotonic()


class SimProber:
    """Implements the Prober protocol from a Scenario. `origin` is the clock time that scenario t=0 maps to."""

    def __init__(self, scenario: Scenario, clock: SimClock, origin: float, seed: int = 7):
        self.scenario = scenario
        self.clock = clock
        self.origin = origin
        self.seed = seed

    def _t(self) -> float:
        return self.clock.time() - self.origin

    def _rng(self, ttl: int, t: float, salt: int = 0) -> random.Random:
        return random.Random((self.seed * 1000003) ^ (ttl * 7919) ^ (int(t) * 104729) ^ salt)

    def _effects(self, ttl: int, t: float):
        for e in self.scenario.effects:
            if not (e.t0 <= t < e.t1):
                continue
            if e.kind in ("hop-loss", "silent"):
                if ttl == e.first_ttl:
                    yield e
            elif e.kind == "dish-lan-down":
                continue
            elif ttl >= e.first_ttl:
                yield e

    def _timeout(self) -> EchoResult:
        return EchoResult(False, False, None, None, "timeout", IP_REQ_TIMED_OUT)

    def echo(self, dest_ip: str, ttl: int = 64, timeout_ms: int = 1000) -> EchoResult:
        t = self._t()
        if dest_ip == SIM_DISH_LAN:
            for e in self.scenario.effects:
                if e.kind == "dish-lan-down" and e.t0 <= t < e.t1:
                    return self._timeout()
                if e.kind == "down" and e.first_ttl <= 2 and e.t0 <= t < e.t1:
                    return self._timeout()
            return EchoResult(True, True, 1.6, SIM_DISH_LAN, "reply", IP_SUCCESS)
        if dest_ip == SIM_GATEWAY:
            hop = 1
            ttl_eff = 1
            direct = True
        elif dest_ip == SIM_TARGET:
            hop = min(ttl, len(SIM_PATH))
            direct = ttl >= len(SIM_PATH)
        else:
            return self._timeout()
        addr, base = SIM_PATH[hop - 1]
        rng = self._rng(hop, t, 1)
        rtt = base * (1.0 + rng.uniform(-0.04, 0.06)) + rng.random() * 0.6
        for e in self._effects(hop, t):
            if e.kind == "down" or e.kind == "silent":
                return self._timeout()
            if e.kind in ("loss", "hop-loss") and self._rng(hop, t, 2).random() < e.value:
                return self._timeout()
            if e.kind == "lat":
                rtt += e.value * (0.85 + 0.3 * rng.random())
        if hop == len(SIM_PATH) or (direct and dest_ip == SIM_TARGET):
            return EchoResult(True, True, rtt, SIM_TARGET, "reply", IP_SUCCESS)
        return EchoResult(True, False, rtt, addr, "ttl-expired", IP_TTL_EXPIRED_TRANSIT)


def sim_route(_dest: str) -> RouteInfo:
    return RouteInfo(True, SIM_GATEWAY, SIM_SOURCE, 1)
