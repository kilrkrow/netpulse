"""Persisted user settings (JSON under %LOCALAPPDATA%\\NetPulse)."""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, field
from typing import Dict

from core.rc.model import SEGMENTS


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
