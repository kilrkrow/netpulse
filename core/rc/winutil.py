"""Small Windows helpers (process token elevation check)."""

from __future__ import annotations

import ctypes
import sys


def is_elevated(pid: int = 0) -> bool:
    """True when the process (default: this one) runs with an elevated (administrator) token."""
    if sys.platform != "win32":
        return False
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    adv = ctypes.WinDLL("advapi32", use_last_error=True)
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    adv.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    adv.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
                                        ctypes.POINTER(wintypes.DWORD)]
    proc = k32.GetCurrentProcess() if pid == 0 else k32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED
    if not proc:
        raise OSError(f"cannot open process {pid}")
    tok = wintypes.HANDLE()
    try:
        if not adv.OpenProcessToken(proc, 0x8, ctypes.byref(tok)):   # TOKEN_QUERY
            raise OSError("OpenProcessToken failed")

        class TOKEN_ELEVATION(ctypes.Structure):
            _fields_ = [("TokenIsElevated", wintypes.DWORD)]

        te = TOKEN_ELEVATION()
        ret = wintypes.DWORD()
        if not adv.GetTokenInformation(tok, 20, ctypes.byref(te), ctypes.sizeof(te), ctypes.byref(ret)):
            raise OSError("GetTokenInformation failed")
        return bool(te.TokenIsElevated)
    finally:
        if tok:
            k32.CloseHandle(tok)
        if pid != 0 and proc:
            k32.CloseHandle(proc)
