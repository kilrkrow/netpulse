"""Continuous ping engine with real-time statistics."""

import subprocess
import re
import time
import statistics
from collections import deque
from dataclasses import dataclass, field
from typing import Optional, List, Deque
import datetime

from PySide6.QtCore import QObject, QThread, Signal, Slot


@dataclass
class PingResult:
    timestamp: datetime.datetime
    host: str
    seq: int
    rtt_ms: Optional[float]   # None = timeout/error
    ttl: Optional[int]
    resolved_ip: Optional[str] = None
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.rtt_ms is not None


@dataclass
class PingStats:
    host: str
    samples: int = 0
    received: int = 0
    lost: int = 0
    loss_pct: float = 0.0
    rtt_min: Optional[float] = None
    rtt_max: Optional[float] = None
    rtt_avg: Optional[float] = None
    rtt_stddev: Optional[float] = None
    jitter: Optional[float] = None   # Mean absolute diff between consecutive RTTs
    last_rtt: Optional[float] = None
    last_ttl: Optional[int] = None
    last_ip: Optional[str] = None
    session_start: Optional[datetime.datetime] = None


def _parse_ping_output(output: str, host: str, seq: int,
                       ts: datetime.datetime) -> 'PingResult':
    rtt: Optional[float] = None
    ttl: Optional[int] = None
    resolved_ip: Optional[str] = None
    error: Optional[str] = None

    # Sub-millisecond response
    if re.search(r'time<1ms', output, re.IGNORECASE):
        rtt = 0.5
    else:
        m = re.search(r'time=(\d+)ms', output, re.IGNORECASE)
        if m:
            rtt = float(m.group(1))

    m = re.search(r'TTL=(\d+)', output, re.IGNORECASE)
    if m:
        ttl = int(m.group(1))

    # IP from "Reply from x.x.x.x"
    m = re.search(r'Reply from (\d+\.\d+\.\d+\.\d+)', output, re.IGNORECASE)
    if m:
        resolved_ip = m.group(1)
    if not resolved_ip:
        m = re.search(r'\[(\d+\.\d+\.\d+\.\d+)\]', output)
        if m:
            resolved_ip = m.group(1)

    if rtt is None:
        lower = output.lower()
        if 'timed out' in lower:
            error = 'Request timed out'
        elif 'unreachable' in lower:
            error = 'Host unreachable'
        elif 'could not find host' in lower or 'unknown host' in lower:
            error = 'Host not found'
        elif 'general failure' in lower:
            error = 'General failure'
        else:
            error = 'No reply'

    return PingResult(timestamp=ts, host=host, seq=seq, rtt_ms=rtt,
                      ttl=ttl, resolved_ip=resolved_ip, error=error)


class _PingWorker(QObject):
    result_ready = Signal(object)   # PingResult
    stats_updated = Signal(object)  # PingStats

    def __init__(self, host: str, interval_ms: int, timeout_ms: int, window: int):
        super().__init__()
        self.host = host
        self.interval_ms = interval_ms
        self.timeout_ms = timeout_ms
        self.window = window
        self._running = False
        self._seq = 0
        self._history: Deque[PingResult] = deque(maxlen=window)
        self._session_start: Optional[datetime.datetime] = None

    @Slot()
    def run(self):
        self._running = True
        self._session_start = datetime.datetime.now()
        while self._running:
            t_start = time.monotonic()
            result = self._ping_once()
            self._history.append(result)
            self.result_ready.emit(result)
            self.stats_updated.emit(self._compute_stats())
            elapsed = time.monotonic() - t_start
            remaining = self.interval_ms / 1000.0 - elapsed
            if remaining > 0:
                end = time.monotonic() + remaining
                while self._running and time.monotonic() < end:
                    time.sleep(0.05)

    def stop(self):
        self._running = False

    def _ping_once(self) -> PingResult:
        self._seq += 1
        ts = datetime.datetime.now()
        try:
            proc = subprocess.run(
                ['ping', '-n', '1', '-w', str(self.timeout_ms), self.host],
                capture_output=True, text=True,
                timeout=self.timeout_ms / 1000 + 3,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            output = proc.stdout + proc.stderr
            return _parse_ping_output(output, self.host, self._seq, ts)
        except subprocess.TimeoutExpired:
            return PingResult(ts, self.host, self._seq, None, None,
                              error='Process timeout')
        except Exception as e:
            return PingResult(ts, self.host, self._seq, None, None, error=str(e))

    def _compute_stats(self) -> PingStats:
        history = list(self._history)
        samples = len(history)
        successful = [r for r in history if r.rtt_ms is not None]
        received = len(successful)
        lost = samples - received
        rtts = [r.rtt_ms for r in successful]
        loss_pct = (lost / samples * 100) if samples else 0.0

        rtt_min = rtt_max = rtt_avg = rtt_stddev = jitter = None
        if rtts:
            rtt_min = min(rtts)
            rtt_max = max(rtts)
            rtt_avg = statistics.mean(rtts)
            if len(rtts) > 1:
                rtt_stddev = statistics.stdev(rtts)
                jitter = statistics.mean(
                    abs(rtts[i] - rtts[i - 1]) for i in range(1, len(rtts))
                )
            else:
                rtt_stddev = 0.0
                jitter = 0.0

        last = history[-1] if history else None
        return PingStats(
            host=self.host,
            samples=samples,
            received=received,
            lost=lost,
            loss_pct=loss_pct,
            rtt_min=rtt_min,
            rtt_max=rtt_max,
            rtt_avg=rtt_avg,
            rtt_stddev=rtt_stddev,
            jitter=jitter,
            last_rtt=last.rtt_ms if last else None,
            last_ttl=last.ttl if last else None,
            last_ip=last.resolved_ip if last else None,
            session_start=self._session_start,
        )


class PingEngine(QObject):
    """Public API: manages a background ping worker thread."""

    result_ready = Signal(object)   # PingResult
    stats_updated = Signal(object)  # PingStats

    def __init__(self, host: str, interval_ms: int = 1000,
                 timeout_ms: int = 2000, window: int = 3600):
        super().__init__()
        self._host = host
        self._interval_ms = interval_ms
        self._timeout_ms = timeout_ms
        self._window = window
        self._worker: Optional[_PingWorker] = None
        self._thread: Optional[QThread] = None

    def start(self):
        if self._thread and self._thread.isRunning():
            return
        self._worker = _PingWorker(
            self._host, self._interval_ms, self._timeout_ms, self._window
        )
        self._thread = QThread()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.result_ready.connect(self.result_ready)
        self._worker.stats_updated.connect(self.stats_updated)
        self._thread.start()

    def stop(self):
        if self._worker:
            self._worker.stop()
        if self._thread:
            self._thread.quit()
            self._thread.wait(5000)
        self._thread = None
        self._worker = None

    def update_settings(self, interval_ms: int, timeout_ms: int):
        was_running = self.is_running
        if was_running:
            self.stop()
        self._interval_ms = interval_ms
        self._timeout_ms = timeout_ms
        if was_running:
            self.start()

    @property
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.isRunning())

    @property
    def host(self) -> str:
        return self._host
