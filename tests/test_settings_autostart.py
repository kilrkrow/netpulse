"""Settings persistence; Start with Windows / Start menu toggles (Windows only, temp locations)."""

import os
import sys

import pytest

from core.rc.settings import SettingsStore

win_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


def test_settings_round_trip_and_bad_values_are_ignored(tmp_path):
    p = str(tmp_path / "s.json")
    s = SettingsStore(p)
    s.value.target = "8.8.8.8"
    s.set_override("ip:198.51.100.9", "dish")
    s.set_override("ttl:4", "not-a-segment")           # invalid: ignored
    s.value.lookups_allowed = True
    s.save()
    s2 = SettingsStore(p)
    assert s2.value.target == "8.8.8.8" and s2.value.lookups_allowed
    assert s2.value.label_overrides == {"ip:198.51.100.9": "dish"}
    open(p, "w").write('{"target": 5, "label_overrides": {"ip:1.2.3.4": "bogus"}}')
    s3 = SettingsStore(p)
    assert s3.value.target == "1.1.1.1" and s3.value.label_overrides == {}


@win_only
def test_run_key_toggle_adds_and_removes_its_entry():
    from core.rc import autostart
    sub = r"Software\NetPulse-test\Run"
    try:
        assert not autostart.run_key_enabled(sub)
        autostart.set_run_key(True, sub, command='"C:\\x\\NetPulse.exe" --background')
        assert autostart.run_key_enabled(sub)
        autostart.set_run_key(False, sub)
        assert not autostart.run_key_enabled(sub)
        autostart.set_run_key(False, sub)              # removing twice is fine
    finally:
        import winreg
        for k in (sub, r"Software\NetPulse-test"):
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, k)
            except OSError:
                pass


@win_only
def test_start_menu_shortcut_toggle_adds_and_removes_the_lnk(tmp_path):
    from core.rc import autostart
    folder = str(tmp_path / "Programs")
    assert not autostart.shortcut_enabled(folder)
    autostart.set_shortcut(True, folder)
    lnk = autostart.shortcut_path(folder)
    assert os.path.exists(lnk) and os.path.getsize(lnk) > 100
    autostart.set_shortcut(False, folder)
    assert not os.path.exists(lnk)


@win_only
def test_unprivileged_icmp_works_without_admin():
    from core.rc.icmp import IcmpProber
    from core.rc.winutil import is_elevated
    assert is_elevated() is False or os.environ.get("NETPULSE_TEST_ALLOW_ELEVATED")
    p = IcmpProber()
    r = p.echo("127.0.0.1", 64, 1000)
    assert r.ok and r.reached and r.address == "127.0.0.1" and r.rtt_ms is not None
