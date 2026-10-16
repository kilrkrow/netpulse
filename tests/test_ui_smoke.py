"""Runs the real main window against simulated networks (offscreen Qt) and reads every visible label.

Skipped automatically where PySide6 is not installed.
"""

import os
import sys
import time

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEventLoop, Qt, QTimer  # noqa: E402
from PySide6.QtWidgets import (QAbstractButton, QAbstractItemView, QApplication, QLabel, QLineEdit,  # noqa: E402
                               QTabBar)

EXPECTED = {
    "healthy": "Network is healthy",
    "gateway-outage": "Gateway is down",
    "dish-outage": "Dish is down",
    "internet-outage": "Internet side is down",
    "cant-tell": "Can't tell which segment is down",
}

TRAY_LABELS = ["Show NetPulse", "Copy report", "Start with Windows", "Add to Start menu", "Settings...",
               "About NetPulse", "Exit NetPulse"]


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


def visible_strings(win):
    out = []
    for w in win.findChildren(QLabel):
        out.append(w.text())
        out.append(w.toolTip())
    for w in win.findChildren(QAbstractButton):
        out += [w.text(), w.toolTip()]
    for w in win.findChildren(QLineEdit):
        out.append(w.placeholderText())
    for tb in win.findChildren(QTabBar):
        out += [tb.tabText(i) for i in range(tb.count())]
    out += [a.text() for a in win._tray_mgr.menu.actions()]
    out.append(win._tray.toolTip())
    for tv in win.findChildren(QAbstractItemView):
        m = tv.model()
        if m is None:
            continue
        for c in range(m.columnCount()):
            out.append(str(m.headerData(c, Qt.Orientation.Horizontal) or ""))
    return [s for s in out if s]


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_scenario_renders_expected_verdict_and_clean_text(app, name, tmp_path, monkeypatch):
    monkeypatch.setenv("NETPULSE_DATA_DIR", str(tmp_path))
    from ui.main_window import MainWindow
    from ui.rc.runtime import RcRuntime

    rt = RcRuntime("test", name)
    win = MainWindow(rt)
    win.show()
    rt.start()
    try:
        spin(1800)
        headline = win._path_page.verdict.headline.text()
        assert headline.startswith(EXPECTED[name]), headline
        assert not win.windowIcon().isNull(), "window must carry the NetPulse icon"
        assert not win._tray.icon().isNull(), "tray must carry the NetPulse icon"
        labels = [a.text() for a in win._tray_mgr.menu.actions() if a.text() and not a.isSeparator()]
        assert labels[1:] == TRAY_LABELS, labels
        bad = [s for s in visible_strings(win) if any(ord(c) > 127 for c in s)]
        assert not bad, f"non-ASCII visible text: {bad}"
        for tv in win.findChildren(QAbstractItemView):
            assert tv.textElideMode().name == "ElideNone"        # Qt would otherwise draw a Unicode ellipsis
        for tb in win.findChildren(QTabBar):
            assert tb.elideMode().name == "ElideNone"
        assert not any("debug" in s.lower() for s in visible_strings(win))
    finally:
        rt.stop()
        win._quitting = True
        win._tray_mgr.hide()
        win.close()


def test_status_icons_differ_per_state(app):
    from ui.rc.tray import status_icon
    a = status_icon("healthy").pixmap(32, 32).toImage()
    b = status_icon("outage").pixmap(32, 32).toImage()
    assert a != b
