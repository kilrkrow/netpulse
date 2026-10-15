"""Continuous per-hop probing engine (Qt-free).

How it works (the "mtr" method, all unprivileged):
  * Discovery: send echo requests to the target with TTL 1..N in parallel. A router that drops a
    packet answers "TTL expired" with its address, which maps the path. The first TTL at which the
    target itself answers marks the end of the path.
  * Probing: every hop is probed every interval with the same TTL-limited echo, so each hop gets
    its own latency, loss and jitter series, rolling windows included.
  * The path is kept (not forgotten) when the network dies, so an outage can be located.
  * Route changes (new gateway or source address) restart discovery from scratch.
"""

from __future__ import annotations

import threading
import time
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable, Deque, Dict, List, Optional, Protocol

from core.rc.ipclass import STARLINK_DISH_IP
from core.rc.labeler import label_path
from core.rc.model import (SEG_DISH, SEG_GATEWAY, SEG_INTERNET, SEG_PC, HopView, PathSnapshot, Sample)
from core.rc.netinfo import RouteInfo, get_route


class Prober(Protocol):
    def echo(self, dest_ip: str, ttl: int = 64, timeout_ms: int = 1000): ...


@dataclass
class ProbeConfig:
    target: str = "1.1.1.1"
    interval_s: float = 1.0
    timeout_ms: int = 1000
    max_hops: int = 20
    history: int = 900
    rediscover_s: float = 90.0
    route_check_s: float = 5.0
    dish_lan_ip: str = STARLINK_DISH_IP
    discovery_tries: int = 2


class _Track:
    """Mutable per-hop state inside the engine."""

    def __init__(self, ttl: int, mode: str, probe_ip: str, history: int, is_target: bool = False):
        self.ttl = ttl
        self.mode = mode                  # "ttl" (TTL-limited echo to target) or "direct"
        self.probe_ip = probe_ip          # destination for the echo
        self.is_target = is_target
        self.samples: Deque[Sample] = deque(maxlen=history)
        self.recent_ips: Deque[str] = deque(maxlen=20)
        self.seen: Counter = Counter()
        self.ever_ok = False
        self.total_sent = 0

    def best_ip(self) -> Optional[str]:
        if self.recent_ips:
            return Counter(self.recent_ips).most_common(1)[0][0]
        return self.seen.most_common(1)[0][0] if self.seen else None


class ProbeEngine:
    def __init__(
        self,
        prober: Prober,
        config: Optional[ProbeConfig] = None,
        clock: Callable[[], float] = time.time,
        route_fn: Callable[[str], RouteInfo] = get_route,
        overrides_fn: Callable[[], Dict[str, str]] = lambda: {},
        asn_fn: Callable[[str], Optional[int]] = lambda ip: None,
        on_snapshot: Optional[Callable[[PathSnapshot], None]] = None,
    ):
        self.prober = prober
        self.cfg = config or ProbeConfig()
        self.clock = clock
        self.route_fn = route_fn
        self.overrides_fn = overrides_fn
        self.asn_fn = asn_fn
        self.on_snapshot = on_snapshot

        self._lock = threading.RLock()
        self._tracks: Dict[int, _Track] = {}
        self._side: Dict[str, _Track] = {}
        self._route = RouteInfo(False)
        self._mapped = False
        self._started_ts = clock()
        self._last_discovery = 0.0
        self._last_route_check = 0.0
        self._executor: Optional[ThreadPoolExecutor] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._paused = False
        self.last_discovery_error = ""

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._executor = ThreadPoolExecutor(max_workers=self.cfg.max_hops + 4, thread_name_prefix="np-probe")
        self._thread = threading.Thread(target=self._loop, name="np-engine", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        if self._executor:
            self._executor.shutdown(wait=False, cancel_futures=True)
        self._thread = None

    def set_paused(self, paused: bool) -> None:
        self._paused = paused

    def set_target(self, target: str) -> None:
        with self._lock:
            if target != self.cfg.target:
                self.cfg.target = target
                self._reset()

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _loop(self) -> None:
        while not self._stop.is_set():
            t0 = time.monotonic()
            if not self._paused:
                try:
                    self.run_once()
                except Exception as exc:   # keep the engine alive; surface in discovery_error
                    self.last_discovery_error = f"engine: {exc!r}"
            wait = self.cfg.interval_s - (time.monotonic() - t0)
            if wait > 0:
                self._stop.wait(wait)

    # ------------------------------------------------------------------ one cycle
    def run_once(self) -> PathSnapshot:
        """Route check, (re)discovery when due, probe every hop once, publish a snapshot."""
        now = self.clock()
        if now - self._last_route_check >= self.cfg.route_check_s or not self._tracks:
            self._check_route(now)
        if self._needs_discovery(now):
            self.discover()
        self._probe_all(now)
        snap = self.snapshot()
        if self.on_snapshot:
            try:
                self.on_snapshot(snap)
            except Exception:
                pass
        return snap

    def _check_route(self, now: float) -> None:
        self._last_route_check = now
        route = self.route_fn(self.cfg.target)
        with self._lock:
            old = self._route
            self._route = route
            changed = route.ok and old.ok and (route.gateway != old.gateway or route.source != old.source)
            if changed:
                self._reset()

    def _needs_discovery(self, now: float) -> bool:
        with self._lock:
            if not self._route.ok:
                return False
            if not self._tracks:
                return True
            if not self._mapped and now - self._last_discovery >= 10.0:
                return True
            if self._mapped and now - self._last_discovery >= self.cfg.rediscover_s:
                tgt = self._target_track()
                if tgt and tgt.samples and all(s.ok for s in list(tgt.samples)[-3:]):
                    return True
            return False

    def _reset(self) -> None:
        self._tracks.clear()
        self._side.clear()
        self._mapped = False
        self._last_discovery = 0.0
        self._started_ts = self.clock()

    def _target_track(self) -> Optional[_Track]:
        for t in self._tracks.values():
            if t.is_target:
                return t
        return None

    # ------------------------------------------------------------------ discovery
    def discover(self) -> None:
        """Map the path with TTL-limited echo requests, all TTLs in parallel."""
        cfg = self.cfg
        self._last_discovery = self.clock()
        route = self._route
        results: Dict[int, object] = {}

        def probe(ttl: int):
            best = None
            for _ in range(cfg.discovery_tries):
                r = self.prober.echo(cfg.target, ttl, cfg.timeout_ms)
                if r.ok:
                    return ttl, r
                best = best or r
            return ttl, best

        ex = self._executor
        try:
            it = ex.map(probe, range(1, cfg.max_hops + 1)) if ex else map(probe, range(1, cfg.max_hops + 1))
            for ttl, r in it:
                results[ttl] = r
        except Exception as exc:
            self.last_discovery_error = f"discovery: {exc!r}"
            return

        target_ttl = None
        for ttl in sorted(results):
            r = results[ttl]
            if r is not None and r.ok and r.reached:
                target_ttl = ttl
                break
        responders = [t for t in sorted(results) if results[t] is not None and results[t].ok]
        with self._lock:
            if self._mapped and self._tracks and target_ttl is None:
                # Re-discovery during trouble must not erase the known-good path: keep it.
                self.last_discovery_error = "re-discovery did not reach the target; kept the known path"
                return
            new_tracks: Dict[int, _Track] = {}
            if responders and (target_ttl is not None or len(responders) >= 1):
                last_ttl = target_ttl if target_ttl is not None else max(responders)
                for ttl in range(1, last_ttl + 1):
                    r = results.get(ttl)
                    is_target = (target_ttl is not None and ttl == target_ttl)
                    mode = "direct" if is_target else "ttl"
                    ip = cfg.target
                    new_tracks[ttl] = self._merge(ttl, mode, ip, is_target)
                    if r is not None and r.ok and r.address:
                        new_tracks[ttl].seen[r.address] += 1
                if target_ttl is None:
                    ttl = last_ttl + 1
                    new_tracks[ttl] = self._merge(ttl, "direct", cfg.target, True)
                self._mapped = target_ttl is not None or len(responders) > 1
            else:
                # Nothing answered: still probe the gateway and the target directly.
                gw = self._route.gateway
                i = 1
                if gw:
                    t = self._merge(1, "direct", gw, False)
                    t.seen[gw] += 1
                    new_tracks[1] = t
                    i = 2
                new_tracks[i] = self._merge(i, "direct", cfg.target, True)
                self._mapped = False
            self._tracks = new_tracks
            self.last_discovery_error = "" if responders else "no hop answered the discovery probes"

        # Dish management address (reachable on the LAN only on some setups).
        if cfg.dish_lan_ip and cfg.dish_lan_ip != self._route.gateway:
            known = {ip for t in self._tracks.values() for ip in t.seen}
            if cfg.dish_lan_ip not in known and "dish-lan" not in self._side:
                try:
                    r = self.prober.echo(cfg.dish_lan_ip, 64, 800)
                except Exception:
                    r = None
                if r is not None and r.ok:
                    self._side["dish-lan"] = _Track(0, "direct", cfg.dish_lan_ip, cfg.history)

    def _merge(self, ttl: int, mode: str, probe_ip: str, is_target: bool) -> _Track:
        old = self._tracks.get(ttl)
        if old and old.mode == mode and old.is_target == is_target and old.probe_ip == probe_ip:
            return old
        return _Track(ttl, mode, probe_ip, self.cfg.history, is_target)

    # ------------------------------------------------------------------ probing
    def _probe_all(self, now: float) -> None:
        with self._lock:
            tracks = list(self._tracks.values()) + list(self._side.values())
        if not tracks:
            return

        def do(track: _Track):
            ts = self.clock()
            try:
                ttl = track.ttl if track.mode == "ttl" else 64
                r = self.prober.echo(track.probe_ip, ttl, self.cfg.timeout_ms)
            except Exception as exc:   # treat API failure as a failed probe
                return track, Sample(ts, False, None, None, f"error:{exc.__class__.__name__}")
            if r.ok:
                return track, Sample(ts, True, r.rtt_ms, r.address, r.status)
            return track, Sample(ts, False, None, r.address, r.status)

        ex = self._executor
        pairs = list(ex.map(do, tracks)) if ex else [do(t) for t in tracks]
        with self._lock:
            for track, sample in pairs:
                track.samples.append(sample)
                track.total_sent += 1
                if sample.ok:
                    track.ever_ok = True
                if sample.ip and sample.ok:
                    track.recent_ips.append(sample.ip)
                    track.seen[sample.ip] += 1

    # ------------------------------------------------------------------ snapshot
    def snapshot(self) -> PathSnapshot:
        with self._lock:
            route = self._route
            hops: List[HopView] = [HopView(
                ttl=0, ip=route.source, segment=SEG_PC, label_source="fixed", ever_ok=True)]
            for ttl in sorted(self._tracks):
                t = self._tracks[ttl]
                ip = t.best_ip()
                if t.is_target:
                    ip = self.cfg.target
                hv = HopView(
                    ttl=ttl, ip=ip, segment=SEG_INTERNET, is_target=t.is_target,
                    samples=list(t.samples), ever_ok=t.ever_ok, total_sent=t.total_sent,
                    seen_ips=[i for i, _ in t.seen.most_common(4)],
                )
                hops.append(hv)
            side = {}
            for name, t in self._side.items():
                side[name] = HopView(
                    ttl=-1, ip=t.probe_ip, segment=SEG_DISH, label_source="fixed",
                    samples=list(t.samples), ever_ok=t.ever_ok, total_sent=t.total_sent, note=name)
            snap = PathSnapshot(
                ts=self.clock(), target=self.cfg.target, hops=hops, route_ok=route.ok,
                gateway_ip=route.gateway, source_ip=route.source, mapped=self._mapped,
                side_probes=side, started_ts=self._started_ts)
        asn_map = {}
        for h in snap.hops:
            if h.ip:
                a = self.asn_fn(h.ip)
                if a:
                    asn_map[h.ip] = a
                    h.asn = a
        label_path(snap.hops, snap.gateway_ip, self.overrides_fn(), asn_map)
        # The target is always the end of the internet segment unless the user overrode it.
        # A hop is the gateway when it is the first router and no address is known yet.
        if snap.gateway_ip is None:
            first = next((h for h in snap.hops if h.ttl == 1), None)
            if first is not None and first.label_source != "override":
                first.segment = SEG_GATEWAY
        return snap
