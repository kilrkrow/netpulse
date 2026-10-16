"""Where NetPulse keeps its data: %LOCALAPPDATA%\\NetPulse (never the repo)."""

from __future__ import annotations

import os


def data_dir() -> str:
    override = os.environ.get("NETPULSE_DATA_DIR")
    if override:
        base = override
    else:
        root = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".local", "share")
        base = os.path.join(root, "NetPulse")
    os.makedirs(base, exist_ok=True)
    return base


def db_path(simulate: bool = False) -> str:
    return os.path.join(data_dir(), "netpulse-sim.db" if simulate else "netpulse.db")


def settings_path(simulate: bool = False) -> str:
    return os.path.join(data_dir(), "settings-sim.json" if simulate else "settings.json")
