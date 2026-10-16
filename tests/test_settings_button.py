"""Interval / Timeout / Graph live behind a Settings button (issue #7): never above the tabs, persisted, applied."""

import json
import os
import sys

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEventLoop, QRect, QTimer  # noqa: E402
from PySide6.QtGui import QGuiApplication, QImage  # noqa: E402
from PySide6.QtWidgets import (QAbstractButton, QApplication, QComboBox, QLineEdit, QSpinBox,  # noqa: E402
                               QTableWidget)

from core.rc.settings import RcSettings, SettingsStore  # noqa: E402


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication(sys.argv[:1])
    a.setApplicationName("NetPulse")
    a.setApplicationVersion("test")
    from ui.rc import theme
    a.setStyleSheet(theme.build_qss(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "ui")))
    yield a
    a.setStyleSheet("")


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


TAB_NAMES = ["Path", "Outages", "Monitor", "Traceroute", "Dossier", "Alerts"]


def rect_of(win, w) -> QRect:
    return QRect(w.mapTo(win, w.rect().topLeft()), w.size())


def test_no_spinners_and_three_icon_buttons_present(app, tmp_path, monkeypatch):
    rt, win = make_window(tmp_path, monkeypatch)
    try:
        spin(300)
        for i in range(win._tabs.count()):
            win._tabs.setCurrentIndex(i)
            spin(50)
            assert not [w for w in win.findChildren(QSpinBox) if w.isVisible() and w.window() is win], f"spinner on tab {i}"
        assert not hasattr(win, "_toolbar") and not hasattr(win, "_interval_spin")
        assert win._tabs.cornerWidget() is None, "nothing may sit in the tab row"
        want = {"share": "Share screenshot", "export": "Export CSV", "settings": "Settings"}
        for key, b in (("share", win._share_btn), ("export", win._export_btn), ("settings", win._settings_btn)):
            assert b.isVisible() and b.text() == "" and not b.icon().isNull(), key
            assert b.toolTip() == want[key] and b.accessibleName() == want[key]
            assert b.toolTip().isascii() and b.accessibleName().isascii() and b.accessibleDescription().isascii()
        # left to right: Share, Export, Settings
        xs = [rect_of(win, b).x() for b in (win._share_btn, win._export_btn, win._settings_btn)]
        assert xs == sorted(xs)
    finally:
        close(rt, win)


def test_tab_row_is_clean_and_nothing_moves_between_tabs(app, tmp_path, monkeypatch):
    rt, win = make_window(tmp_path, monkeypatch)
    try:
        spin(300)
        bar = win._tabs.tabBar()
        seen, docks = set(), set()
        for i in range(win._tabs.count()):
            win._tabs.setCurrentIndex(i)
            spin(80)
            seen.add((tuple(rect_of(win, bar).getRect()), tuple(rect_of(win, win._tabs.currentWidget()).getRect())))
            docks.add(tuple(rect_of(win, win._dock).getRect()))
        assert len(seen) == 1, f"tab row / content moved between tabs: {seen}"
        assert len(docks) == 1, f"the Share/Export/Settings dock moved between tabs: {docks}"
        dock = rect_of(win, win._dock)
        assert not dock.intersects(rect_of(win, bar)), "the dock must stay out of the tab row"
        top = bar.mapTo(win.centralWidget(), bar.rect().topLeft()).y()
        assert top <= win.centralWidget().layout().contentsMargins().top()
        # opening Settings (a separate dialog window) does not move the tabs, the content or the dock
        before = (rect_of(win, bar), rect_of(win, win._tabs.currentWidget()), rect_of(win, win._dock))
        dlg = win._settings_dialog()
        dlg.show()
        spin(100)
        after = (rect_of(win, bar), rect_of(win, win._tabs.currentWidget()), rect_of(win, win._dock))
        assert before == after
        dlg.reject()
    finally:
        close(rt, win)


def test_every_tab_reserves_exactly_the_dock_position(app, tmp_path, monkeypatch):
    """Each tab keeps an invisible same-sized slot at the right end of its top row; the dock sits right on it."""
    from ui.dock import ActionDock
    rt, win = make_window(tmp_path, monkeypatch)
    try:
        spin(300)
        dock = rect_of(win, win._dock)
        for i, name in enumerate(TAB_NAMES):
            win._tabs.setCurrentIndex(i)
            spin(80)
            slots = [s for s in win._tabs.currentWidget().findChildren(ActionDock)]
            assert len(slots) == 1, name
            assert rect_of(win, slots[0]) == dock, (name, rect_of(win, slots[0]), dock)
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


def test_screenshot_action_writes_a_valid_png_and_copies_to_clipboard(app, tmp_path, monkeypatch):
    rt, win = make_window(tmp_path, monkeypatch)
    try:
        spin(300)
        out = str(tmp_path / "shot.png")
        assert win._save_screenshot_to(out)
        raw = open(out, "rb").read()
        assert raw[:8] == b"\x89PNG\r\n\x1a\n" and len(raw) > 2000
        img = QImage(out)
        assert not img.isNull() and img.width() >= win.width() and img.height() >= win.height()
        assert win._save_screenshot_to(str(tmp_path / "noext"))                 # ".png" is added
        assert os.path.exists(str(tmp_path / "noext.png"))
        assert win._copy_screenshot()
        clip = QGuiApplication.clipboard().image()
        assert not clip.isNull() and clip.width() >= win.width()
        import re
        assert re.fullmatch(r"netpulse_\d{8}_\d{6}\.png", win._screenshot_name())
        assert not win._save_screenshot_to("")                                  # nothing to write to
        menu = win._build_share_menu()
        items = [x.text() for x in menu.actions()]
        assert items == ["Copy screenshot to clipboard", "Save screenshot as PNG..."]
        assert all(s.isascii() for s in items)
        QGuiApplication.clipboard().clear()
        menu.actions()[0].trigger()                                             # the menu's copy action works
        assert not QGuiApplication.clipboard().image().isNull()
    finally:
        close(rt, win)


def test_tray_settings_and_gear_open_the_same_dialog(app, tmp_path, monkeypatch):
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


def _row(win, widgets):
    return sorted((rect_of(win, w) for w in widgets), key=lambda r: r.x())


def test_dock_and_monitor_rows_share_one_set_of_tolerances(app, tmp_path, monkeypatch):
    """Heights equal across rows, the same 6 px gaps, the same distance to the border above, the same edge margin."""
    rt, win = make_window(tmp_path, monkeypatch)
    try:
        win._tabs.setCurrentIndex(2)
        spin(400)
        mt = win._monitor_tab
        pane = rect_of(win, mt)
        controls = _row(win, [mt._start_btn, mt._stop_all_btn, mt._proc_refresh_btn, mt._watch_btn])
        dock = _row(win, [win._share_btn, win._export_btn, win._settings_btn])
        status = _row(win, [mt._table_btn, mt._graph_btn])
        text_rows = controls + status
        assert len({r.height() for r in text_rows}) == 1, [r.height() for r in text_rows]      # every text button row
        assert len({r.height() for r in dock}) == 1, [r.height() for r in dock]
        assert dock[0].height() == 29 and text_rows[0].height() >= 24
        if text_rows[0].height() == 29:          # Segoe UI, the shipped font: the dock is exactly as tall as the lower rows
            assert dock[0].height() == text_rows[0].height()
        else:                                    # offscreen fallback font: natural buttons are shorter, the dock keeps 29
            assert text_rows[0].height() < 29
        for r in dock:
            assert r.width() == r.height(), "icon buttons are square"
        for row in (controls[:2], controls[2:], dock, status):
            for a, b in zip(row, row[1:]):
                assert b.left() - a.right() - 1 == 6, (a, b)
        # the dock sits in the Monitor controls row: same top as Start, same distance to the border above
        assert abs(dock[0].center().y() - controls[0].center().y()) <= 2          # same row
        assert dock[0].top() <= controls[0].top()
        assert dock[0].top() - pane.top() == 8
        if controls[0].height() == dock[0].height():
            assert controls[0].top() - pane.top() == 8
        # right edge margin: dock (controls row) and Graph (status row) end on the same x, 8 px inside the pane
        assert dock[-1].right() == status[-1].right() == pane.right() - 8
        # the status row sits 6 px under the controls row (the dock is as tall as the row)
        assert status[0].top() - max(r.bottom() for r in controls + dock) - 1 == 6
        # ... and 8 px (the pane-edge distance) between the status row and the table / graph frame below it
        assert rect_of(win, mt._stack).top() - max(r.bottom() for r in status) - 1 == 8
        # the same top gap on the other tabs' first row (dock slot): 8 px under the border above
        for i in (1, 3, 4, 5):
            win._tabs.setCurrentIndex(i)
            spin(80)
            assert rect_of(win, win._dock).top() - rect_of(win, win._tabs.currentWidget()).top() == 8
    finally:
        close(rt, win)


def _interactive(win):
    out = []
    for w in win.findChildren(QAbstractButton) + win.findChildren(QComboBox) + win.findChildren(QLineEdit):
        if not w.isVisibleTo(win) or w.window() is not win:
            continue
        p = w.parentWidget()
        inside_composite = False
        while p is not None and p is not win:
            if isinstance(p, (QTableWidget, QComboBox, QSpinBox)) or p.metaObject().className() in ("QTabBar",):
                inside_composite = True
                break
            p = p.parentWidget()
        if not inside_composite and w.width() > 0 and w.height() > 0:
            out.append(w)
    return out


def test_no_control_overlaps_or_touches_another_on_any_tab(app, tmp_path, monkeypatch):
    rt, win = make_window(tmp_path, monkeypatch)
    try:
        spin(300)
        for i, name in enumerate(TAB_NAMES):
            win._tabs.setCurrentIndex(i)
            spin(120)
            ws = _interactive(win)
            assert win._share_btn in ws
            for a_i, a in enumerate(ws):
                ra = rect_of(win, a)
                for b in ws[a_i + 1:]:
                    if a.isAncestorOf(b) or b.isAncestorOf(a):
                        continue
                    rb = rect_of(win, b)
                    grown = ra.adjusted(-3, -3, 3, 3)                          # closer than 4 px counts as touching
                    assert not grown.intersects(rb), (name, a.accessibleName() or a.text(), ra, b.accessibleName() or b.text(), rb)
    finally:
        close(rt, win)
