"""Persisted user settings (JSON under %LOCALAPPDATA%\\NetPulse)."""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, field
from typing import Dict

from core.rc.model import SEGMENTS


# Monitor tab ping defaults (were the Interval / Timeout / Graph bar): (min, max, default)
PING_INTERVAL_MS = (100, 60000, 1000)
PING_TIMEOUT_MS = (200, 10000, 2000)
GRAPH_POINTS = (30, 3600, 300)


@dataclass
class RcSettings:
    target: str = "1.1.1.1"
    interval_s: float = 1.0
    label_overrides: Dict[str, str] = field(default_factory=dict)   # "ip:1.2.3.4" / "ttl:3" -> segment
    lookups_allowed: bool = False       # the user has accepted that lookups send an IP to outside services
    lookups_notice_seen: bool = False
    auto_identify_hops: bool = True     # use the ASN of public hops to recognize Starlink (needs lookups_allowed)
    notifications: bool = True
    dish_lan_ip: str = "192.168.100.1"
    ping_interval_ms: int = PING_INTERVAL_MS[2]     # Monitor tab: defaults for new ping sessions
    ping_timeout_ms: int = PING_TIMEOUT_MS[2]
    graph_points: int = GRAPH_POINTS[2]


class SettingsStore:
    def __init__(self, path: str):
        self.path = path
        self._lock = threading.RLock()
        self.value = RcSettings()
        self.load()

    def load(self) -> None:
        with self._lock:
            try:
                with open(self.path, encoding="utf-8") as f:
                    raw = json.load(f)
            except (OSError, ValueError):
                return
            s = RcSettings()
            for k, v in raw.items():
                if hasattr(s, k) and isinstance(v, type(getattr(s, k))):
                    setattr(s, k, v)
            for name, (lo, hi, dflt) in (("ping_interval_ms", PING_INTERVAL_MS), ("ping_timeout_ms", PING_TIMEOUT_MS),
                                         ("graph_points", GRAPH_POINTS)):
                v = getattr(s, name)
                if isinstance(v, bool) or not lo <= v <= hi:       # a hand-edited file never feeds the engine garbage
                    setattr(s, name, dflt)
            s.label_overrides = {k: v for k, v in s.label_overrides.items() if v in SEGMENTS}
            self.value = s

    def save(self) -> None:
        with self._lock:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(asdict(self.value), f, indent=2)
            os.replace(tmp, self.path)

    def set_override(self, key: str, segment: str) -> None:
        with self._lock:
            if segment in SEGMENTS:
                self.value.label_overrides[key] = segment
            else:
                self.value.label_overrides.pop(key, None)
            self.save()
