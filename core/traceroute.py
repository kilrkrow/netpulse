"""Traceroute engine using Windows tracert."""

import subprocess
import re
import threading
from dataclasses import dataclass, field
from typing import Optional, List
import datetime

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


def _parse_rtt(s: str) -> Optional[float]:
    s = s.strip()
    if s == '*':
        return None
    if s.startswith('<'):
        return 0.5   # <1ms
    m = re.match(r'(\d+)', s)
    return float(m.group(1)) if m else None


def _parse_tracert_line(line: str) -> Optional[TracerouteHop]:
    """Parse one tracert output line into a TracerouteHop."""
    # Pattern: "  N  RTT1  RTT2  RTT3  host [ip]"  or "  N  *  *  *  Request timed out."
    m = re.match(
        r'^\s*(\d+)\s+'
        r'([<\d]+\s*ms|\*)\s+'
        r'([<\d]+\s*ms|\*)\s+'
        r'([<\d]+\s*ms|\*)\s+'
        r'(.*?)\s*$',
        line,
        re.IGNORECASE,
    )
    if not m:
        return None

    hop_num = int(m.group(1))
    r1_raw = m.group(2).replace('ms', '').strip()
    r2_raw = m.group(3).replace('ms', '').strip()
    r3_raw = m.group(4).replace('ms', '').strip()
    host_part = m.group(5).strip()

    rtt1 = _parse_rtt(r1_raw)
    rtt2 = _parse_rtt(r2_raw)
    rtt3 = _parse_rtt(r3_raw)

    timed_out = (rtt1 is None and rtt2 is None and rtt3 is None)
    rtts = [r for r in [rtt1, rtt2, rtt3] if r is not None]
    avg_rtt = sum(rtts) / len(rtts) if rtts else None

    # Extract IP and hostname
    ip: Optional[str] = None
    hostname: Optional[str] = None

    if 'timed out' in host_part.lower() or 'request timed out' in host_part.lower():
        pass  # timed_out already set
    elif host_part:
        # "hostname [ip]" or just "ip"
        ip_m = re.search(r'\[(\d+\.\d+\.\d+\.\d+)\]', host_part)
        if ip_m:
            ip = ip_m.group(1)
            hostname = host_part[:ip_m.start()].strip()
        else:
            ip_only = re.match(r'^(\d+\.\d+\.\d+\.\d+)$', host_part)
            if ip_only:
                ip = ip_only.group(1)
            else:
                hostname = host_part

    return TracerouteHop(
        hop_num=hop_num,
        ip=ip,
        hostname=hostname or None,
        rtt1=rtt1,
        rtt2=rtt2,
        rtt3=rtt3,
        avg_rtt=avg_rtt,
        timed_out=timed_out,
    )


class TracerouteEngine(QObject):
    """Run tracert in a background thread and emit results hop by hop."""

    hop_found = Signal(object)       # TracerouteHop
    finished = Signal(list)          # List[TracerouteHop]
    error_occurred = Signal(str)
    started = Signal()

    def __init__(self):
        super().__init__()
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def run(self, host: str, max_hops: int = 30):
        if self._running:
            return
        self._thread = threading.Thread(
            target=self._do_traceroute, args=(host, max_hops), daemon=True
        )
        self._thread.start()

    def _do_traceroute(self, host: str, max_hops: int):
        self._running = True
        self.started.emit()
        hops: List[TracerouteHop] = []
        try:
            proc = subprocess.Popen(
                ['tracert', '-w', '2000', '-h', str(max_hops), host],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            for line in proc.stdout:
                if not self._running:
                    proc.terminate()
                    break
                hop = _parse_tracert_line(line)
                if hop:
                    hops.append(hop)
                    self.hop_found.emit(hop)
            proc.wait()
        except Exception as e:
            self.error_occurred.emit(str(e))
        finally:
            self._running = False
            self.finished.emit(hops)

    def abort(self):
        self._running = False
