"""Interval / Timeout / Graph live behind a Settings button (issue #7): never above the tabs, persisted, applied."""

import json
import os
import sys

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QSpinBox, QTabBar  # noqa: E402

from core.rc.settings import RcSettings, SettingsStore  # noqa: E402


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication(sys.argv[:1])
    a.setApplicationName("NetPulse")
    a.setApplicationVersion("test")
    yield a


def spin(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def make_window(tmp_path, monkeypatch):
    monkeypatch.setenv("NETPULSE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NETPULSE_SIM_KEEP", "1")        # keep settings-sim.json so a second window is a "restart"
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    from ui.main_window import MainWindow
    from ui.rc.runtime import RcRuntime
    rt = RcRuntime("test", "healthy")
    win = MainWindow(rt)
    win.resize(1280, 860)
    win.show()
    return rt, win


def close(rt, win):
    rt.stop()
    win._quitting = True
    win._tray_mgr.hide()
    win.close()


def test_defaults_are_unchanged():
    s = RcSettings()
    assert (s.ping_interval_ms, s.ping_timeout_ms, s.graph_points) == (1000, 2000, 300)


def test_ping_settings_round_trip_and_bad_values_fall_back(tmp_path):
    p = str(tmp_path / "s.json")
    s = SettingsStore(p)
    s.value.ping_interval_ms, s.value.ping_timeout_ms, s.value.graph_points = 250, 3500, 900
    s.save()
    s2 = SettingsStore(p)
    assert (s2.value.ping_interval_ms, s2.value.ping_timeout_ms, s2.value.graph_points) == (250, 3500, 900)
    open(p, "w").write(json.dumps({"ping_interval_ms": 5, "ping_timeout_ms": "x", "graph_points": 10 ** 9}))
    s3 = SettingsStore(p)
    assert (s3.value.ping_interval_ms, s3.value.ping_timeout_ms, s3.value.graph_points) == (1000, 2000, 300)
    open(p, "w").write(json.dumps({"ping_interval_ms": True}))
    assert SettingsStore(p).value.ping_interval_ms == 1000


def test_no_spinners_in_the_main_window_and_settings_button_present(app, tmp_path, monkeypatch):
    rt, win = make_window(tmp_path, monkeypatch)
    try:
        spin(300)
        for i in range(win._tabs.count()):
            win._tabs.setCurrentIndex(i)
            spin(50)
            assert not [w for w in win.findChildren(QSpinBox) if w.isVisible()], f"spinner visible on tab {i}"
        assert not hasattr(win, "_toolbar") and not hasattr(win, "_interval_spin")
        assert win._settings_btn.text() == "Settings" and win._settings_btn.isVisible()
        assert win._export_btn.isVisible()
        assert win._settings_btn.text().isascii() and win._settings_btn.toolTip().isascii()
    finally:
        close(rt, win)


def test_tab_row_is_top_content_and_never_moves(app, tmp_path, monkeypatch):
    rt, win = make_window(tmp_path, monkeypatch)
    try:
        spin(300)
        bar = win._tabs.tabBar()
        seen = set()
        for i in range(win._tabs.count()):
            win._tabs.setCurrentIndex(i)
            spin(50)
            seen.add((bar.mapTo(win, bar.rect().topLeft()).y(), bar.height(), win._tabs.currentWidget().mapTo(
                win, win._tabs.currentWidget().rect().topLeft()).y()))
        assert len(seen) == 1, f"tab row / content moved between tabs: {seen}"
        # nothing sits above the tab row inside the window's central area
        top = bar.mapTo(win.centralWidget(), bar.rect().topLeft()).y()
        assert top <= win.centralWidget().layout().contentsMargins().top()
        # opening Settings does not move the tabs or the content (it is a separate dialog window)
        before = (bar.mapTo(win, bar.rect().topLeft()), win._tabs.currentWidget().geometry())
        dlg = win._settings_dialog()
        dlg.show()
        spin(100)
        after = (bar.mapTo(win, bar.rect().topLeft()), win._tabs.currentWidget().geometry())
        assert before == after
        dlg.reject()
    finally:
        close(rt, win)


def test_settings_apply_and_persist_across_restart(app, tmp_path, monkeypatch):
    rt, win = make_window(tmp_path, monkeypatch)
    try:
        spin(200)
        dlg = win._settings_dialog()
        assert (dlg.ping_interval.value(), dlg.ping_timeout.value(), dlg.graph_points.value()) == (1000, 2000, 300)
        assert (win._monitor_tab._interval_ms, win._monitor_tab._timeout_ms, win._monitor_tab._window) == (1000, 2000, 300)
        dlg.ping_interval.setValue(400)
        dlg.ping_timeout.setValue(1500)
        dlg.graph_points.setValue(120)
        dlg._save()
        mt = win._monitor_tab
        assert (mt._interval_ms, mt._timeout_ms, mt._window) == (400, 1500, 120)      # applied at once
        saved = json.load(open(rt.settings.path))
        assert (saved["ping_interval_ms"], saved["ping_timeout_ms"], saved["graph_points"]) == (400, 1500, 120)
    finally:
        close(rt, win)
    rt2, win2 = make_window(tmp_path, monkeypatch)          # a full restart: new runtime, new window, same profile
    try:
        mt = win2._monitor_tab
        assert (mt._interval_ms, mt._timeout_ms, mt._window) == (400, 1500, 120)
        d2 = win2._settings_dialog()
        assert (d2.ping_interval.value(), d2.ping_timeout.value(), d2.graph_points.value()) == (400, 1500, 120)
        d2.reject()
    finally:
        close(rt2, win2)


def test_cancel_changes_nothing(app, tmp_path, monkeypatch):
    rt, win = make_window(tmp_path, monkeypatch)
    try:
        dlg = win._settings_dialog()
        dlg.ping_interval.setValue(777)
        dlg.reject()
        assert win._monitor_tab._interval_ms == 1000
        assert rt.settings.value.ping_interval_ms == 1000
    finally:
        close(rt, win)


def test_tray_settings_and_button_open_the_same_dialog(app, tmp_path, monkeypatch):
    rt, win = make_window(tmp_path, monkeypatch)
    try:
        opened = []

        class Stub:
            def exec(self):
                opened.append(1)

        monkeypatch.setattr(win, "_settings_dialog", lambda: Stub())
        win._settings_btn.click()
        tray = [a for a in win._tray_mgr.menu.actions() if a.text() == "Settings..."]
        assert len(tray) == 1
        tray[0].trigger()
        assert opened == [1, 1]
    finally:
        close(rt, win)
