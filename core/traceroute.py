"""Traceroute engine using Windows tracert - hop-progress + cancel."""

from __future__ import annotations

import re
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import List, Optional

from PySide6.QtCore import QObject, Signal


@dataclass
class TracerouteHop:
    hop_num: int
    ip: Optional[str]
    hostname: Optional[str]
    rtt1: Optional[float]
    rtt2: Optional[float]
    rtt3: Optional[float]
    avg_rtt: Optional[float]
    timed_out: bool = False
    role: Optional[str] = None  # This PC / LAN / CGNAT / gateway / public
    state: str = "ok"  # probing | ok | timeout | cancelled


def _parse_rtt(s: str) -> Optional[float]:
    s = s.strip()
    if s == "*":
        return None
    if s.startswith("<"):
        return 0.5
    m = re.match(r"(\d+)", s)
    return float(m.group(1)) if m else None


def classify_role(ip: Optional[str], hop_num: int = 0, gateway: Optional[str] = None) -> str:
    if hop_num == 0 or ip in ("127.0.0.1", "::1"):
        return "This PC"
    if not ip:
        return ""
    if gateway and ip == gateway:
        return "gateway"
    parts = ip.split(".")
    if len(parts) == 4 and all(p.isdigit() for p in parts):
        a, b = int(parts[0]), int(parts[1])
        if a == 10 or a == 192 and b == 168 or a == 172 and 16 <= b <= 31:
            return "LAN"
        if a == 100 and 64 <= b <= 127:
            return "CGNAT"
        if a == 169 and b == 254:
            return "link-local"
    return "public"


def _parse_tracert_line(line: str) -> Optional[TracerouteHop]:
    m = re.match(
        r"^\s*(\d+)\s+"
        r"([<\d]+\s*ms|\*)\s+"
        r"([<\d]+\s*ms|\*)\s+"
        r"([<\d]+\s*ms|\*)\s+"
        r"(.*?)\s*$",
        line,
        re.IGNORECASE,
    )
    if not m:
        return None

    hop_num = int(m.group(1))
    r1_raw = m.group(2).replace("ms", "").strip()
    r2_raw = m.group(3).replace("ms", "").strip()
    r3_raw = m.group(4).replace("ms", "").strip()
    host_part = m.group(5).strip()

    rtt1 = _parse_rtt(r1_raw)
    rtt2 = _parse_rtt(r2_raw)
    rtt3 = _parse_rtt(r3_raw)

    timed_out = rtt1 is None and rtt2 is None and rtt3 is None
    rtts = [r for r in (rtt1, rtt2, rtt3) if r is not None]
    avg_rtt = sum(rtts) / len(rtts) if rtts else None

    ip: Optional[str] = None
    hostname: Optional[str] = None

    if "timed out" in host_part.lower():
        pass
    elif host_part:
        ip_m = re.search(r"\[(\d+\.\d+\.\d+\.\d+)\]", host_part)
        if ip_m:
            ip = ip_m.group(1)
            hostname = host_part[: ip_m.start()].strip() or None
        else:
            ip_only = re.match(r"^(\d+\.\d+\.\d+\.\d+)$", host_part)
            if ip_only:
                ip = ip_only.group(1)
            else:
                hostname = host_part

    role = classify_role(ip, hop_num)
    state = "timeout" if timed_out else "ok"
    return TracerouteHop(
        hop_num=hop_num,
        ip=ip,
        hostname=hostname,
        rtt1=rtt1,
        rtt2=rtt2,
        rtt3=rtt3,
        avg_rtt=avg_rtt,
        timed_out=timed_out,
        role=role,
        state=state,
    )


class TracerouteEngine(QObject):
    """Run tracert in a background thread; emit progress while waiting."""

    hop_found = Signal(object)  # TracerouteHop
    finished = Signal(list)  # List[TracerouteHop]
    error_occurred = Signal(str)
    started = Signal()
    cancelled = Signal()
    # (hop_num being probed, elapsed_sec, hint)
    probing = Signal(int, float, str)

    def __init__(self):
        super().__init__()
        self._running = False
        self._cancelled = False
        self._thread: Optional[threading.Thread] = None
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._t0 = 0.0
        self._gateway: Optional[str] = None

    def set_gateway(self, gateway: Optional[str]):
        self._gateway = gateway if gateway and gateway != "-" else None

    @property
    def is_running(self) -> bool:
        return self._running

    def run(self, host: str, max_hops: int = 30):
        with self._lock:
            if self._running:
                return
            self._running = True
            self._cancelled = False
        self._thread = threading.Thread(
            target=self._do_traceroute, args=(host, max_hops), daemon=True
        )
        self._thread.start()

    def abort(self):
        self._cancelled = True
        self._running = False
        proc = self._proc
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
            try:
                proc.kill()
            except Exception:
                pass
            try:
                import subprocess as _sp
                _sp.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    capture_output=True,
                    creationflags=getattr(_sp, "CREATE_NO_WINDOW", 0),
                    timeout=2,
                )
            except Exception:
                pass

    def _elapsed(self) -> float:
        return time.monotonic() - self._t0 if self._t0 else 0.0

    def _do_traceroute(self, host: str, max_hops: int):
        self._t0 = time.monotonic()
        self.started.emit()
        hops: List[TracerouteHop] = []
        next_probe = 1
        self.probing.emit(1, 0.0, "Starting tracert...")
        try:
            # -w 1000 keeps per-probe waits shorter so UI ticks feel alive
            self._proc = subprocess.Popen(
                ["tracert", "-d", "-w", "1000", "-h", str(max_hops), host],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            proc = self._proc
            assert proc.stdout is not None

            # Tick probing while waiting for the next line
            def _reader():
                return proc.stdout.readline()

            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                while True:
                    if self._cancelled:
                        break
                    fut = pool.submit(_reader)
                    while not fut.done():
                        if self._cancelled:
                            self.abort()
                            break
                        hint = ""
                        if self._elapsed() > 2.5 and next_probe > 1:
                            hint = "Slow hop - often ICMP filtered or distant."
                        self.probing.emit(next_probe, self._elapsed(), hint)
                        time.sleep(0.35)
                    if self._cancelled:
                        break
                    line = fut.result()
                    if not line:
                        break
                    # Header lines: still probing hop 1
                    if "tracing route" in line.lower() or "over a maximum" in line.lower():
                        self.probing.emit(1, self._elapsed(), "Resolving / starting path...")
                        continue
                    hop = _parse_tracert_line(line)
                    if not hop:
                        continue
                    if self._gateway and hop.ip:
                        hop.role = classify_role(hop.ip, hop.hop_num, self._gateway)
                    hops.append(hop)
                    self.hop_found.emit(hop)
                    next_probe = hop.hop_num + 1
                    if next_probe <= max_hops and not self._cancelled:
                        self.probing.emit(next_probe, self._elapsed(), "")
            try:
                proc.wait(timeout=2)
            except Exception:
                self.abort()
        except Exception as e:
            if not self._cancelled:
                self.error_occurred.emit(str(e))
        finally:
            self._proc = None
            was_cancelled = self._cancelled
            self._running = False
            if was_cancelled:
                self.cancelled.emit()
            self.finished.emit(hops)
