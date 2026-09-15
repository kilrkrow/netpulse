"""Fast TTL/ICMP path walker for Command Center (1 probe/hop).

Uses Windows `ping -n 1 -i <ttl> -w <ms>` - no admin / raw sockets.
Stock `tracert` stays available as Classic fallback via TracerouteEngine.
"""

from __future__ import annotations

import re
import socket
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Tuple

from PySide6.QtCore import QObject, Signal

from core.traceroute import TracerouteHop, classify_role


def _kill_proc(proc: Optional[subprocess.Popen]) -> None:
    if not proc or proc.poll() is not None:
        return
    try:
        proc.terminate()
    except Exception:
        pass
    try:
        proc.kill()
    except Exception:
        pass
    try:
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            timeout=2,
        )
    except Exception:
        pass


def _parse_ping(output: str) -> Tuple[Optional[str], Optional[float], bool]:
    """Return (ip, rtt_ms, timed_out)."""
    low = output.lower()
    ip = None
    rtt = None
    m = re.search(r"Reply from (\d+\.\d+\.\d+\.\d+)", output, re.I)
    if m:
        ip = m.group(1)
    m2 = re.search(r"time[<=](\d+)\s*ms", output, re.I)
    if m2:
        rtt = float(m2.group(1))
    elif re.search(r"time<\s*1\s*ms", output, re.I):
        rtt = 0.5
    expired = "ttl expired" in low
    timed_out = (
        "request timed out" in low
        or ("100% loss" in low and ip is None)
        or (ip is None and "reply from" not in low and not expired)
    )
    if ip is None:
        return None, None, True
    if expired and rtt is None:
        return ip, None, False
    return ip, rtt, False


def _resolve_dest(host: str) -> Tuple[str, Optional[str]]:
    host = host.strip()
    if re.match(r"^\d+\.\d+\.\d+\.\d+$", host):
        return host, None
    try:
        return socket.gethostbyname(host), None
    except Exception as e:
        return host, str(e)


def _ptr_ok(name: Optional[str], ip: str) -> Optional[str]:
    if not name:
        return None
    n = name.rstrip(".").strip()
    low = n.lower()
    if not n or n == ip:
        return None
    if low in ("localhost", "undefined.hostname.localhost"):
        return None
    if low.endswith(".localhost"):
        return None
    return n


def reverse_lookup(ip: str) -> Optional[str]:
    """Best-effort PTR: gethostbyaddr, dnspython, then nslookup."""
    if not ip:
        return None
    try:
        name = socket.gethostbyaddr(ip)[0]
        ok = _ptr_ok(name, ip)
        if ok:
            return ok
    except Exception:
        pass
    try:
        import dns.resolver
        import dns.reversename

        rev = dns.reversename.from_address(ip)
        ans = dns.resolver.resolve(rev, "PTR", lifetime=2.0)
        ok = _ptr_ok(str(ans[0]), ip)
        if ok:
            return ok
    except Exception:
        pass
    try:
        r = subprocess.run(
            ["nslookup", ip],
            capture_output=True,
            text=True,
            timeout=3,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        out = (r.stdout or "") + (r.stderr or "")
        low = out.lower()
        if "can't find" in low or "non-existent" in low:
            return None
        m = re.search(r"Name:\s*(\S+)", out, re.I)
        if m:
            return _ptr_ok(m.group(1), ip)
    except Exception:
        pass
    return None


class FastPathEngine(QObject):
    """1-probe-per-hop TTL walker + async PTR fill-in."""

    hop_found = Signal(object)
    finished = Signal(list)
    error_occurred = Signal(str)
    started = Signal()
    cancelled = Signal()
    probing = Signal(int, float, str)

    def __init__(self, timeout_ms: int = 300, max_hops: int = 30):
        super().__init__()
        self._timeout_ms = timeout_ms
        self._max_hops = max_hops
        self._running = False
        self._cancel = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._t0 = 0.0
        self._gateway: Optional[str] = None
        self._ptr_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ptr")

    def set_gateway(self, gateway: Optional[str]):
        self._gateway = gateway if gateway and gateway != "-" else None

    def set_timeout_ms(self, ms: int):
        self._timeout_ms = max(100, int(ms))

    @property
    def is_running(self) -> bool:
        return self._running

    def run(self, host: str, max_hops: Optional[int] = None):
        with self._lock:
            if self._running:
                return
            self._running = True
            self._cancel.clear()
        hops_max = max_hops or self._max_hops
        self._thread = threading.Thread(
            target=self._walk, args=(host, hops_max), daemon=True
        )
        self._thread.start()

    def abort(self):
        self._cancel.set()
        with self._lock:
            proc = self._proc
        _kill_proc(proc)

    def _elapsed(self) -> float:
        return time.monotonic() - self._t0 if self._t0 else 0.0

    def _ptr_later(self, hop: TracerouteHop):
        if not hop.ip or hop.hostname:
            return

        def work(hop_snap: TracerouteHop = hop):
            name = reverse_lookup(hop_snap.ip or "")
            if not name:
                return
            updated = TracerouteHop(
                hop_num=hop_snap.hop_num,
                ip=hop_snap.ip,
                hostname=name,
                rtt1=hop_snap.rtt1,
                rtt2=hop_snap.rtt2,
                rtt3=hop_snap.rtt3,
                avg_rtt=hop_snap.avg_rtt,
                timed_out=hop_snap.timed_out,
                role=hop_snap.role,
                state=hop_snap.state if hop_snap.state != "probing" else "ok",
            )
            self.hop_found.emit(updated)

        try:
            self._ptr_pool.submit(work)
        except Exception:
            pass

    def _ptr_sweep(self, hops: List[TracerouteHop]):
        for hop in hops:
            if hop.ip and not hop.hostname:
                self._ptr_later(hop)

    def _walk(self, host: str, max_hops: int):
        self._t0 = time.monotonic()
        self.started.emit()
        hops: List[TracerouteHop] = []
        dest_ip, err = _resolve_dest(host)
        if err and not re.match(r"^\d+\.\d+\.\d+\.\d+$", dest_ip):
            self.error_occurred.emit(f"DNS resolve failed: {err}")
            self._running = False
            self.finished.emit([])
            return

        self.probing.emit(1, 0.0, f"Fast path to {dest_ip} (1 probe/hop)...")
        try:
            for ttl in range(1, max_hops + 1):
                if self._cancel.is_set():
                    break
                self.probing.emit(ttl, self._elapsed(), "")
                try:
                    proc = subprocess.Popen(
                        [
                            "ping",
                            "-n",
                            "1",
                            "-w",
                            str(int(self._timeout_ms)),
                            "-i",
                            str(ttl),
                            dest_ip,
                        ],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                except Exception as e:
                    self.error_occurred.emit(str(e))
                    break
                with self._lock:
                    self._proc = proc
                t_probe = time.monotonic()
                while proc.poll() is None:
                    if self._cancel.is_set():
                        _kill_proc(proc)
                        break
                    time.sleep(0.04)
                out = ""
                try:
                    if proc.stdout is not None and not self._cancel.is_set():
                        out = proc.stdout.read() or ""
                except Exception:
                    out = ""
                wall_ms = (time.monotonic() - t_probe) * 1000.0
                with self._lock:
                    self._proc = None
                if self._cancel.is_set():
                    break

                ip, rtt, timed_out = _parse_ping(out)
                if rtt is None and ip and not timed_out:
                    rtt = round(max(0.5, min(wall_ms, float(self._timeout_ms))), 1)
                if timed_out or ip is None:
                    timed_out = True
                    state = "timeout"
                else:
                    state = "ok"
                role = classify_role(ip, ttl, self._gateway)
                hop = TracerouteHop(
                    hop_num=ttl,
                    ip=ip,
                    hostname=None,
                    rtt1=rtt,
                    rtt2=None,
                    rtt3=None,
                    avg_rtt=rtt,
                    timed_out=timed_out,
                    role=role,
                    state=state,
                )
                hops.append(hop)
                self.hop_found.emit(hop)
                if ip:
                    self._ptr_later(hop)
                if (
                    ip
                    and ip == dest_ip
                    and not timed_out
                    and "ttl expired" not in out.lower()
                ):
                    break
        except Exception as e:
            if not self._cancel.is_set():
                self.error_occurred.emit(str(e))
        finally:
            with self._lock:
                _kill_proc(self._proc)
                self._proc = None
            was_cancel = self._cancel.is_set()
            self._running = False
            if was_cancel:
                self.cancelled.emit()
            self._ptr_sweep(hops)
            self.finished.emit(hops)
