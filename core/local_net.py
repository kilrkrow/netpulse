"""Local interface / DNS helpers for NetPulse Pro footer and verbs."""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple


@dataclass
class LocalNetInfo:
    iface: str = "-"
    ipv4: str = "-"
    ipv6: str = "-"
    gateway: str = "-"
    dns: List[str] = field(default_factory=list)


def _run(cmd: List[str], timeout: float = 8.0) -> Tuple[int, str]:
    try:
        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        out = (p.stdout or "") + (p.stderr or "")
        return p.returncode, out
    except Exception as e:
        return 1, str(e)


def gather_local_net() -> LocalNetInfo:
    info = LocalNetInfo()
    try:
        ps = (
            "$c = Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -ne $null } | "
            "Select-Object -First 1; "
            "if (-not $c) { $c = Get-NetIPConfiguration | Select-Object -First 1 }; "
            "[pscustomobject]@{ "
            "Iface = $c.InterfaceAlias; "
            "IPv4 = ($c.IPv4Address | Select-Object -First 1 -ExpandProperty IPAddress); "
            "IPv6 = ($c.IPv6Address | Where-Object { $_.AddressState -eq 'Preferred' "
            "-and $_.IPAddress -notlike 'fe80*' } | Select-Object -First 1 -ExpandProperty IPAddress); "
            "Gateway = ($c.IPv4DefaultGateway | Select-Object -First 1 -ExpandProperty NextHop); "
            "DNS = @($c.DNSServer.ServerAddresses) "
            "} | ConvertTo-Json -Compress"
        )
        code, out = _run(["powershell", "-NoProfile", "-Command", ps], timeout=12.0)
        if code == 0 and out.strip():
            data = json.loads(out.strip().splitlines()[-1])
            info.iface = str(data.get("Iface") or "-") or "-"
            info.ipv4 = str(data.get("IPv4") or "-") or "-"
            info.ipv6 = str(data.get("IPv6") or "-") or "-"
            info.gateway = str(data.get("Gateway") or "-") or "-"
            dns = data.get("DNS") or []
            if isinstance(dns, str):
                dns = [dns]
            info.dns = [str(x) for x in dns if x]
    except Exception:
        pass
    if info.ipv4 == "-":
        try:
            info.ipv4 = socket.gethostbyname(socket.gethostname())
        except Exception:
            pass
    return info


def flush_dns() -> Tuple[bool, str]:
    code, out = _run(["ipconfig", "/flushdns"])
    low = out.lower()
    ok = code == 0 and ("successfully" in low or "flushed" in low or True)
    if code == 0:
        return True, "DNS resolver cache flushed."
    return False, out.strip() or "Flush DNS failed (may need elevation)."


def renew_dhcp() -> Tuple[bool, str]:
    _run(["ipconfig", "/release"], timeout=20.0)
    c2, o2 = _run(["ipconfig", "/renew"], timeout=30.0)
    if c2 == 0:
        return True, "DHCP renew requested."
    return False, (o2 or "").strip() or "DHCP renew failed (often needs elevation)."


def arp_neighbors() -> List[Tuple[str, str, str]]:
    code, out = _run(["arp", "-a"])
    rows: List[Tuple[str, str, str]] = []
    if code != 0:
        return rows
    for line in out.splitlines():
        m = re.match(r"\s*(\d+\.\d+\.\d+\.\d+)\s+([-0-9a-fA-F:]+)\s+(\w+)", line)
        if m:
            rows.append((m.group(1), m.group(2), m.group(3)))
    return rows


def find_wireshark() -> Optional[str]:
    for c in (
        r"C:\Program Files\Wireshark\Wireshark.exe",
        r"C:\Program Files (x86)\Wireshark\Wireshark.exe",
    ):
        if os.path.isfile(c):
            return c
    return None


def start_timed_capture(seconds: int = 30) -> Tuple[bool, str]:
    ws = find_wireshark()
    if not ws:
        return False, "Wireshark not found. Install Wireshark to start a timed capture."
    try:
        subprocess.Popen([ws])
        return True, f"Launched Wireshark. Timed capture ({seconds}s) is manual in this spike."
    except Exception as e:
        return False, str(e)


def app_data_dir() -> Path:
    base = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
    d = base / "NetPulse"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_json(name: str, default):
    p = app_data_dir() / name
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(name: str, data) -> None:
    (app_data_dir() / name).write_text(json.dumps(data, indent=2), encoding="utf-8")
