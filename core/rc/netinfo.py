"""Local routing facts: default gateway and source address for a destination (no admin needed)."""

from __future__ import annotations

import ctypes
import socket
import struct
import sys
from dataclasses import dataclass
from typing import Optional


@dataclass
class RouteInfo:
    ok: bool
    gateway: Optional[str] = None     # next hop toward the destination (None when on-link)
    source: Optional[str] = None      # this PC's address used to reach the destination
    if_index: int = 0
    error: str = ""


if sys.platform == "win32":
    from ctypes import wintypes

    class _MIB_IPFORWARDROW(ctypes.Structure):
        _fields_ = [(n, wintypes.DWORD) for n in (
            "dwForwardDest", "dwForwardMask", "dwForwardPolicy", "dwForwardNextHop",
            "dwForwardIfIndex", "dwForwardType", "dwForwardProto", "dwForwardAge",
            "dwForwardNextHopAS", "dwForwardMetric1", "dwForwardMetric2", "dwForwardMetric3",
            "dwForwardMetric4", "dwForwardMetric5")]

    _iphlp = ctypes.WinDLL("iphlpapi")
    _iphlp.GetBestRoute.restype = wintypes.DWORD
    _iphlp.GetBestRoute.argtypes = [wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(_MIB_IPFORWARDROW)]
else:  # pragma: no cover
    _iphlp = None


def _source_for(dest: str) -> Optional[str]:
    """UDP connect() picks a route and source address without sending anything."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((dest, 9))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def get_route(dest: str) -> RouteInfo:
    """Best route to dest: gateway (next hop) and the local source address."""
    src = _source_for(dest)
    if src is None or src == "0.0.0.0":
        return RouteInfo(False, error="no route to the internet (no usable network adapter)")
    if _iphlp is None:  # pragma: no cover
        return RouteInfo(True, None, src)
    row = _MIB_IPFORWARDROW()
    dest_d = struct.unpack("<I", socket.inet_aton(dest))[0]
    rc = _iphlp.GetBestRoute(dest_d, 0, ctypes.byref(row))
    if rc != 0:
        return RouteInfo(False, None, src, error=f"GetBestRoute error {rc}")
    nh = socket.inet_ntoa(struct.pack("<I", row.dwForwardNextHop))
    if row.dwForwardType == 3 or nh in ("0.0.0.0", src):   # 3 = direct (on-link)
        nh = None
    return RouteInfo(True, nh, src, int(row.dwForwardIfIndex))
