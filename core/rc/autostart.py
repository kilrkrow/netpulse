"""Start with Windows (HKCU Run key) and Add to Start menu (a .lnk). Both are per-user, no admin.

Neither toggle starts a child process: the Run key uses winreg and the shortcut is written through
the Shell's IShellLinkW COM interface via ctypes, so no console window can flash.
"""

from __future__ import annotations

import ctypes
import os
import sys
from typing import Optional

RUN_SUBKEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "NetPulse"
LNK_NAME = "NetPulse.lnk"
BACKGROUND_ARG = "--background"


def launch_command(frozen: Optional[bool] = None) -> "tuple[str, str]":
    """(program, arguments) that start NetPulse; arguments exclude --background."""
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    if frozen:
        return sys.executable, ""
    main = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "main.py"))
    exe = sys.executable
    w = os.path.join(os.path.dirname(exe), "pythonw.exe")
    return (w if os.path.exists(w) else exe), f'"{main}"'


def start_menu_dir() -> str:
    appdata = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
    return os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs")


# ----------------------------------------------------------------------------- Run key

def run_key_command() -> str:
    prog, args = launch_command()
    cmd = f'"{prog}"' + (f" {args}" if args else "")
    return f"{cmd} {BACKGROUND_ARG}"


def run_key_enabled(subkey: str = RUN_SUBKEY) -> bool:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, subkey, 0, winreg.KEY_READ) as k:
            winreg.QueryValueEx(k, RUN_VALUE)
            return True
    except FileNotFoundError:
        return False


def set_run_key(enabled: bool, subkey: str = RUN_SUBKEY, command: Optional[str] = None) -> None:
    import winreg
    if enabled:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, subkey, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, RUN_VALUE, 0, winreg.REG_SZ, command or run_key_command())
    else:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, subkey, 0, winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, RUN_VALUE)
        except FileNotFoundError:
            pass


# ----------------------------------------------------------------------------- Start menu shortcut

def shortcut_path(folder: Optional[str] = None) -> str:
    return os.path.join(folder or start_menu_dir(), LNK_NAME)


def shortcut_enabled(folder: Optional[str] = None) -> bool:
    return os.path.exists(shortcut_path(folder))


def _guid(text: str):
    from ctypes import wintypes

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                    ("Data4", ctypes.c_ubyte * 8)]

    g = GUID()
    ole32 = ctypes.OleDLL("ole32")
    ole32.IIDFromString(text, ctypes.byref(g))
    return g


def create_shortcut(lnk: str, target: str, arguments: str = "", icon: Optional[str] = None,
                    description: str = "NetPulse network diagnostics") -> None:
    from ctypes import WINFUNCTYPE, POINTER, byref, c_int, c_void_p, c_wchar_p, HRESULT
    ole32 = ctypes.OleDLL("ole32")
    ole32.CoInitialize(None)
    clsid = _guid("{00021401-0000-0000-C000-000000000046}")
    iid_link = _guid("{000214F9-0000-0000-C000-000000000046}")
    iid_file = _guid("{0000010B-0000-0000-C000-000000000046}")
    link = c_void_p()
    ole32.CoCreateInstance(byref(clsid), None, 1, byref(iid_link), byref(link))
    persist = c_void_p()
    try:
        def method(ptr, index, *argtypes):
            vtbl = ctypes.cast(ptr, POINTER(POINTER(c_void_p)))
            return WINFUNCTYPE(HRESULT, c_void_p, *argtypes)(vtbl[0][index])

        method(link, 20, c_wchar_p)(link, target)                       # SetPath
        if arguments:
            method(link, 11, c_wchar_p)(link, arguments)                # SetArguments
        method(link, 9, c_wchar_p)(link, os.path.dirname(target))       # SetWorkingDirectory
        method(link, 7, c_wchar_p)(link, description)                   # SetDescription
        method(link, 17, c_wchar_p, c_int)(link, icon or target, 0)     # SetIconLocation
        method(link, 0, c_void_p, POINTER(c_void_p))(link, ctypes.cast(byref(iid_file), c_void_p), byref(persist))
        os.makedirs(os.path.dirname(lnk), exist_ok=True)
        method(persist, 6, c_wchar_p, c_int)(persist, lnk, 1)           # IPersistFile::Save
    finally:
        if persist:
            method(persist, 2)(persist)
        if link:
            method(link, 2)(link)


def set_shortcut(enabled: bool, folder: Optional[str] = None) -> None:
    lnk = shortcut_path(folder)
    if enabled:
        prog, args = launch_command()
        create_shortcut(lnk, prog, args)
    else:
        try:
            os.remove(lnk)
        except FileNotFoundError:
            pass
