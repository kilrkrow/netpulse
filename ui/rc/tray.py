"""System tray: the real app icon with a status square, and the menu."""

from __future__ import annotations

import os
from typing import Callable

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from core.rc import autostart
from ui.rc import theme
from ui.rc.runtime import resource_path

_SIZES = (16, 20, 24, 32, 48, 64)


def app_icon() -> QIcon:
    """The NetPulse icon from the repo assets (never a drawn placeholder)."""
    ico = QIcon(resource_path(os.path.join("assets", "appicon.ico")))
    if ico.isNull():
        ico = QIcon(resource_path(os.path.join("assets", "icon.png")))
    return ico


def status_icon(kind: str) -> QIcon:
    """App icon with a square status indicator in the lower right corner."""
    base = app_icon()
    out = QIcon()
    col = QColor(theme.KIND_COLORS.get(kind, theme.UNKNOWN))
    for s in _SIZES:
        pm = QPixmap(base.pixmap(s, s))
        if pm.isNull():
            pm = QPixmap(s, s)
            pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        d = max(6, int(s * 0.42))
        r = QRectF(s - d, s - d, d, d)
        p.fillRect(r, QColor("#06080b"))
        p.fillRect(r.adjusted(1, 1, -1, -1), col)
        p.end()
        out.addPixmap(pm)
    return out


class TrayManager:
    """Owns the QSystemTrayIcon. The menu items are plain callbacks into the main window."""

    def __init__(self, window, on_show: Callable, on_copy: Callable, on_settings: Callable, on_about: Callable,
                 on_exit: Callable, simulate: bool = False):
        self.window = window
        self.simulate = simulate
        self.tray = QSystemTrayIcon(window)
        self.tray.setIcon(status_icon("measuring"))
        self.tray.setToolTip("NetPulse")
        m = QMenu()
        self.status = m.addAction("NetPulse: starting")
        self.status.setEnabled(False)
        m.addSeparator()
        self.show_act = m.addAction("Show NetPulse")
        f = self.show_act.font()
        f.setBold(True)
        self.show_act.setFont(f)
        self.show_act.triggered.connect(on_show)
        m.addAction("Copy report").triggered.connect(on_copy)
        m.addSeparator()
        self.run_act = QAction("Start with Windows", m, checkable=True)
        self.run_act.triggered.connect(self._toggle_run)
        m.addAction(self.run_act)
        self.menu_act = QAction("Add to Start menu", m, checkable=True)
        self.menu_act.triggered.connect(self._toggle_menu)
        m.addAction(self.menu_act)
        m.addSeparator()
        m.addAction("Settings...").triggered.connect(on_settings)
        m.addAction("About NetPulse").triggered.connect(on_about)
        m.addSeparator()
        m.addAction("Exit NetPulse").triggered.connect(on_exit)
        m.aboutToShow.connect(self.refresh_toggles)
        self.menu = m
        self.tray.setContextMenu(m)
        self.refresh_toggles()
        self._kind = ""

    def show(self) -> None:
        self.tray.show()

    def hide(self) -> None:
        self.tray.hide()

    def refresh_toggles(self) -> None:
        try:
            self.run_act.setChecked(autostart.run_key_enabled())
            self.menu_act.setChecked(autostart.shortcut_enabled())
        except Exception:
            pass

    def _toggle_run(self, on: bool) -> None:
        if self.simulate:                    # a simulated run never touches the real Windows registry
            return
        try:
            autostart.set_run_key(on)
        except Exception as exc:
            self.tray.showMessage("NetPulse", f"Could not change the startup entry ({exc.__class__.__name__}).",
                                  QSystemTrayIcon.MessageIcon.Warning, 4000)
        self.refresh_toggles()

    def _toggle_menu(self, on: bool) -> None:
        if self.simulate:
            return
        try:
            autostart.set_shortcut(on)
        except Exception as exc:
            self.tray.showMessage("NetPulse", f"Could not change the Start menu entry ({exc.__class__.__name__}).",
                                  QSystemTrayIcon.MessageIcon.Warning, 4000)
        self.refresh_toggles()

    def set_verdict(self, kind: str, headline: str) -> None:
        if kind != self._kind:
            self.tray.setIcon(status_icon(kind))
            self._kind = kind
        self.status.setText(headline if len(headline) < 60 else headline[:57] + "...")
        self.tray.setToolTip(f"NetPulse: {headline}"[:120])

    def notify(self, title: str, text: str, warn: bool = False) -> None:
        self.tray.showMessage(title, text, QSystemTrayIcon.MessageIcon.Warning if warn else
                              QSystemTrayIcon.MessageIcon.Information, 6000)
