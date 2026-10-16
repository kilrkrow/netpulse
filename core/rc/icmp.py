"""Unprivileged ICMP on Windows via the IP Helper API (IcmpCreateFile / IcmpSendEcho).

No raw sockets, no administrator rights, no child processes (so no console window can flash).
IcmpSendEcho is documented at
https://learn.microsoft.com/en-us/windows/win32/api/icmpapi/nf-icmpapi-icmpsendecho
Setting IP_OPTION_INFORMATION.Ttl lets one echo request double as a traceroute probe:
a router that drops the packet answers with status IP_TTL_EXPIRED_TRANSIT (11013) and its
own address in ICMP_ECHO_REPLY.Address.
"""

from __future__ import annotations

import ctypes
import socket
import struct
import sys
import threading
import time
from dataclasses import dataclass
from typing import Optional

IP_SUCCESS = 0
IP_DEST_NET_UNREACHABLE = 11002
IP_DEST_HOST_UNREACHABLE = 11003
IP_DEST_PROT_UNREACHABLE = 11004
IP_DEST_PORT_UNREACHABLE = 11005
IP_REQ_TIMED_OUT = 11010
IP_TTL_EXPIRED_TRANSIT = 11013
IP_GENERAL_FAILURE = 11050

_STATUS_TEXT = {
    IP_SUCCESS: "reply",
    IP_DEST_NET_UNREACHABLE: "net-unreachable",
    IP_DEST_HOST_UNREACHABLE: "host-unreachable",
    IP_DEST_PROT_UNREACHABLE: "protocol-unreachable",
    IP_DEST_PORT_UNREACHABLE: "port-unreachable",
    IP_REQ_TIMED_OUT: "timeout",
    IP_TTL_EXPIRED_TRANSIT: "ttl-expired",
    IP_GENERAL_FAILURE: "general-failure",
    11001: "buffer-too-small",
    11050: "general-failure",
}


@dataclass
class EchoResult:
    """Outcome of one echo request."""

    ok: bool                      # True when something useful answered (reply or TTL-expired router)
    reached: bool                 # True when the destination itself answered (status 0)
    rtt_ms: Optional[float]       # round trip in ms (sub-ms resolution when measurable)
    address: Optional[str]        # who answered (router for TTL-expired, target for a reply)
    status: str                   # short text
    code: int = -1                # raw IP_STATUS


class IcmpUnavailable(RuntimeError):
    pass


if sys.platform == "win32":
    from ctypes import wintypes

    class _IP_OPTION_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("Ttl", ctypes.c_ubyte),
            ("Tos", ctypes.c_ubyte),
            ("Flags", ctypes.c_ubyte),
            ("OptionsSize", ctypes.c_ubyte),
            ("OptionsData", ctypes.c_void_p),
        ]

    class _ICMP_ECHO_REPLY(ctypes.Structure):
        _fields_ = [
            ("Address", ctypes.c_uint32),
            ("Status", ctypes.c_uint32),
            ("RoundTripTime", ctypes.c_uint32),
            ("DataSize", ctypes.c_ushort),
            ("Reserved", ctypes.c_ushort),
            ("Data", ctypes.c_void_p),
            ("Options", _IP_OPTION_INFORMATION),
        ]

    _iphlp = ctypes.WinDLL("iphlpapi", use_last_error=True)
    _iphlp.IcmpCreateFile.restype = wintypes.HANDLE
    _iphlp.IcmpCreateFile.argtypes = []
    _iphlp.IcmpCloseHandle.restype = wintypes.BOOL
    _iphlp.IcmpCloseHandle.argtypes = [wintypes.HANDLE]
    _iphlp.IcmpSendEcho.restype = wintypes.DWORD
    _iphlp.IcmpSendEcho.argtypes = [
        wintypes.HANDLE, ctypes.c_uint32, ctypes.c_void_p, wintypes.WORD,
        ctypes.POINTER(_IP_OPTION_INFORMATION), ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
    ]
    _INVALID_HANDLE = ctypes.c_void_p(-1).value
else:  # pragma: no cover - the module still imports on other platforms for unit tests
    _iphlp = None
    _INVALID_HANDLE = None


def _ip_to_dword(ip: str) -> int:
    """Dotted quad -> IPAddr (network byte order stored in a native DWORD)."""
    return struct.unpack("<I", socket.inet_aton(ip))[0]


def _dword_to_ip(v: int) -> str:
    return socket.inet_ntoa(struct.pack("<I", v))


class IcmpProber:
    """Thread-safe echo prober: one ICMP handle per thread (created lazily)."""

    PAYLOAD = b"NetPulse-RC-probe-01234567"  # 26 bytes, ASCII

    def __init__(self) -> None:
        if _iphlp is None:
            raise IcmpUnavailable("Windows IP Helper API not available on this platform")
        self._local = threading.local()
        self._buf_size = ctypes.sizeof(_ICMP_ECHO_REPLY) + len(self.PAYLOAD) + 8 + 64

    def _handle(self):
        h = getattr(self._local, "h", None)
        if h is None:
            h = _iphlp.IcmpCreateFile()
            if h is None or h == _INVALID_HANDLE:
                raise IcmpUnavailable(f"IcmpCreateFile failed (error {ctypes.get_last_error()})")
            self._local.h = h
            self._local.buf = ctypes.create_string_buffer(self._buf_size)
        return h, self._local.buf

    def close_thread_handle(self) -> None:
        h = getattr(self._local, "h", None)
        if h is not None:
            _iphlp.IcmpCloseHandle(h)
            self._local.h = None

    def echo(self, dest_ip: str, ttl: int = 64, timeout_ms: int = 1000) -> EchoResult:
        """Send one echo request to dest_ip with the given TTL."""
        h, buf = self._handle()
        opt = _IP_OPTION_INFORMATION(Ttl=max(1, min(255, ttl)), Tos=0, Flags=0, OptionsSize=0, OptionsData=None)
        t0 = time.perf_counter()
        n = _iphlp.IcmpSendEcho(
            h, _ip_to_dword(dest_ip), self.PAYLOAD, len(self.PAYLOAD),
            ctypes.byref(opt), buf, self._buf_size, int(timeout_ms),
        )
        elapsed = (time.perf_counter() - t0) * 1000.0
        if n == 0:
            err = ctypes.get_last_error()
            return EchoResult(False, False, None, None, _STATUS_TEXT.get(err, f"error-{err}"), err)
        reply = ctypes.cast(buf, ctypes.POINTER(_ICMP_ECHO_REPLY)).contents
        code = int(reply.Status)
        addr = _dword_to_ip(reply.Address)
        reported = float(reply.RoundTripTime)
        # The API reports whole milliseconds. The wall time of the synchronous call is a finer
        # reading when it agrees with the reported value.
        rtt = elapsed if (elapsed >= reported and elapsed - reported < 1.5) else max(reported, 0.0)
        text = _STATUS_TEXT.get(code, f"status-{code}")
        if code == IP_SUCCESS:
            return EchoResult(True, True, rtt, addr, text, code)
        if code == IP_TTL_EXPIRED_TRANSIT:
            return EchoResult(True, False, rtt, addr, text, code)
        # destination/host unreachable etc.: a router answered but the path is broken
        return EchoResult(False, False, rtt, addr, text, code)
