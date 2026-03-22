"""Process and TCP connection discovery for game/app monitoring."""

import subprocess
from dataclasses import dataclass
from typing import List, Optional

from PySide6.QtCore import QObject, QTimer, Signal


@dataclass
class ProcessInfo:
    pid: int
    name: str


def get_running_processes() -> List[ProcessInfo]:
    """Return a deduplicated, name-sorted list of running processes."""
    try:
        result = subprocess.run(
            ['tasklist', '/FO', 'CSV', '/NH'],
            capture_output=True, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=10,
        )
        seen: dict[str, ProcessInfo] = {}
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.strip('"').split('","')
            if len(parts) < 2:
                continue
            name = parts[0]
            try:
                pid = int(parts[1])
            except ValueError:
                continue
            if name not in seen:
                seen[name] = ProcessInfo(pid=pid, name=name)
        return sorted(seen.values(), key=lambda p: p.name.lower())
    except Exception:
        return []


def get_pids_for_name(process_name: str) -> List[int]:
    """Return all PIDs currently running under the given image name."""
    try:
        result = subprocess.run(
            ['tasklist', '/FO', 'CSV', '/NH', '/FI', f'IMAGENAME eq {process_name}'],
            capture_output=True, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=10,
        )
        pids = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.strip('"').split('","')
            if len(parts) >= 2:
                try:
                    pids.append(int(parts[1]))
                except ValueError:
                    pass
        return pids
    except Exception:
        return []


def get_process_connections(pids: List[int]) -> List[str]:
    """Return unique, routable remote IPs for all ESTABLISHED TCP connections
    belonging to any of the given PIDs."""
    if not pids:
        return []
    try:
        result = subprocess.run(
            ['netstat', '-ano'],
            capture_output=True, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=10,
        )
        pid_set = {str(p) for p in pids}
        ips: set[str] = set()
        for line in result.stdout.splitlines():
            parts = line.split()
            # Format: Proto  LocalAddr  RemoteAddr  State  PID
            if len(parts) < 5:
                continue
            if parts[0].upper() != 'TCP':
                continue
            if parts[3].upper() != 'ESTABLISHED':
                continue
            if parts[4] not in pid_set:
                continue
            remote = parts[2]
            # Strip port (last colon); handle [IPv6]:port
            ip = remote.rsplit(':', 1)[0].strip('[]')
            # Filter unroutable addresses
            if ip in ('0.0.0.0', '::', '::1') or ip.startswith('127.'):
                continue
            ips.add(ip)
        return sorted(ips)
    except Exception:
        return []


class ProcessWatcher(QObject):
    """Poll every 2 s for a named process and emit its TCP connections as they appear.

    Workflow:
      1. Call watch(name) to start watching.
      2. process_found emits once the process appears (or immediately if already running).
      3. connections_found emits whenever new ESTABLISHED remote IPs are detected.
      4. Call stop() to halt polling.
    """

    process_found = Signal(str, int)   # process_name, first_pid
    connections_found = Signal(list)   # list[str] of newly detected remote IPs

    def __init__(self, parent=None):
        super().__init__(parent)
        self._name: Optional[str] = None
        self._pids: List[int] = []
        self._known: set[str] = set()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)

    def watch(self, process_name: str):
        """Begin watching for process_name.  Safe to call while already watching."""
        self._name = process_name
        self._pids = []
        self._known = set()
        self._timer.start(2000)

    def stop(self):
        self._timer.stop()
        self._name = None

    @property
    def is_watching(self) -> bool:
        return self._timer.isActive()

    def _poll(self):
        if not self._name:
            return

        # Step 1: find the process if not yet seen
        if not self._pids:
            pids = get_pids_for_name(self._name)
            if pids:
                self._pids = pids
                self.process_found.emit(self._name, pids[0])

        # Step 2: scan connections for all known PIDs
        if self._pids:
            ips = get_process_connections(self._pids)
            new_ips = [ip for ip in ips if ip not in self._known]
            if new_ips:
                self._known.update(new_ips)
                self.connections_found.emit(new_ips)
