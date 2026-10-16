"""The Share, Export and Settings buttons: one floating dock at the top right of the content area.

The dock is a child of the tab widget, placed over the content (never in the tab row and never in a layout), so it is
in the same screen position on every tab and cannot shift anything. Every tab keeps a same-sized invisible slot at the
right end of its top row so its own controls never run under the dock; a test pins the dock to every slot.

All three buttons are icon-only squares as tall as every other button (29 px), 6 px apart:
[share] [download = export CSV] [gear = settings]."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QSizePolicy, QWidget

from ui.rc.icons import download_icon, gear_icon, share_icon

GAP = 6                 # between buttons in every row of the app
EDGE = 8                # from the content edge (top and right) to the dock
BTN_H = 29              # the natural QPushButton height in the instrument theme (every other button row)
ICON_PX = 17


def _icon_button(icon, tip: str, desc: str, name: str) -> QPushButton:
    b = QPushButton()
    b.setObjectName("iconBtn")
    b.setIcon(icon)
    b.setIconSize(QSize(ICON_PX, ICON_PX))
    b.setToolTip(tip)
    b.setAccessibleName(tip)
    b.setAccessibleDescription(desc)
    b.setProperty("dockName", name)
    b.setFixedSize(BTN_H, BTN_H)                # square; QPushButton#iconBtn in theme.py pins the same 29 px: 27 + 1 px border (a style
                                                # sheet min-width would otherwise override this)
    return b


class ActionDock(QWidget):
    def __init__(self, parent=None, placeholder: bool = False):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(GAP)
        self.share_btn = _icon_button(share_icon(), "Share screenshot",
                                      "Copy a picture of the NetPulse window to the clipboard or save it as a PNG", "share")
        self.export_btn = _icon_button(download_icon(), "Export CSV",
                                       "Save the Monitor tab ping results as a CSV file", "export")
        self.settings_btn = _icon_button(gear_icon(), "Settings",
                                         "Open the NetPulse settings: probe target, ping interval, timeout and graph "
                                         "length, notifications and labels", "settings")
        for b in (self.share_btn, self.export_btn, self.settings_btn):
            lay.addWidget(b)
        if placeholder:
            for b in (self.share_btn, self.export_btn, self.settings_btn):
                b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                b.setEnabled(False)
            sp = self.sizePolicy()
            sp.setRetainSizeWhenHidden(True)
            sp.setHorizontalPolicy(QSizePolicy.Policy.Fixed)
            sp.setVerticalPolicy(QSizePolicy.Policy.Fixed)
            self.setSizePolicy(sp)
            self.setVisible(False)                      # keeps its size in the layout, draws nothing


def slot() -> ActionDock:
    """An invisible same-sized hole for a tab's top row."""
    return ActionDock(placeholder=True)


def add_slot(row) -> ActionDock:
    """Reserve the dock's place at the right end of a tab's top row (gap of GAP to the control before it)."""
    row.setSpacing(GAP)
    s = slot()
    row.addWidget(s, 0, Qt.AlignmentFlag.AlignRight)
    return s