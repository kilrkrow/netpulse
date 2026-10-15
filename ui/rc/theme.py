"""Instrument look: near-black panels, 1px lines, square corners, source-colored traces.

An aesthetic direction (dense VFD meters, CRT-phosphor history, glanceable summary that opens into
detail), reimplemented here from scratch with QPainter; no code is shared with any other project.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QFontDatabase

from core.rc.model import SEG_DISH, SEG_GATEWAY, SEG_INTERNET, SEG_PC

BG = "#06080b"
PANEL = "#0a0e12"
PANEL_HI = "#0e141a"
GRID = "#14202a"
GRID_MAJOR = "#1b2c38"
BORDER = "#1c2a34"
TEXT = "#d5ecf2"
DIM = "#8aa2ad"
DIMMER = "#52666f"
CYAN = "#19e6ff"

OK = "#4be07c"
WARN = "#ffb43f"
FAIL = "#ff4d5a"
INFO = "#5aa9ff"
UNKNOWN = "#8aa2ad"

SEG_COLORS = {
    SEG_PC: "#b4c6d0",
    SEG_GATEWAY: "#19e6ff",
    SEG_DISH: "#ffb43f",
    SEG_INTERNET: "#4be07c",
}

STATUS_COLORS = {"ok": OK, "info": INFO, "warn": WARN, "fail": FAIL}
KIND_COLORS = {"healthy": OK, "degraded": WARN, "outage": FAIL, "unknown": UNKNOWN, "measuring": INFO}
KIND_GLYPH = {"healthy": "OK", "degraded": "!!", "outage": "XX", "unknown": "??", "measuring": ".."}

MONO_FAMILIES = ["Cascadia Mono", "Consolas", "Lucida Console", "Courier New"]
UI_FAMILIES = ["Segoe UI", "Arial"]


def qcolor(hex_: str, alpha: float = 1.0) -> QColor:
    c = QColor(hex_)
    c.setAlphaF(max(0.0, min(1.0, alpha)))
    return c


_mono_family = None


def mono_family() -> str:
    global _mono_family
    if _mono_family is None:
        have = set(QFontDatabase.families())
        _mono_family = next((f for f in MONO_FAMILIES if f in have), "Courier New")
    return _mono_family


def mono(pt: float, bold: bool = False) -> QFont:
    f = QFont(mono_family())
    f.setPointSizeF(pt)
    f.setBold(bold)
    f.setStyleHint(QFont.StyleHint.Monospace)
    return f


def ui_font(pt: float, bold: bool = False) -> QFont:
    f = QFont("Segoe UI")
    f.setPointSizeF(pt)
    f.setBold(bold)
    return f


APP_QSS = f"""
* {{ outline: 0; }}
QMainWindow, QDialog, QWidget {{
    background-color: {BG}; color: {TEXT};
    font-family: "Segoe UI", Arial, sans-serif; font-size: 10pt;
}}
QToolTip {{ background: {PANEL_HI}; color: {TEXT}; border: 1px solid {BORDER}; padding: 3px 5px; }}
QTabWidget::pane {{ border: 1px solid {BORDER}; background-color: {PANEL}; top: -1px; }}
QTabBar::tab {{
    background: {BG}; color: {DIM}; border: 1px solid transparent; border-bottom: none;
    padding: 6px 16px; min-width: 70px; font-size: 9.5pt; letter-spacing: 1px;
}}
QTabBar::tab:selected {{ background: {PANEL}; color: {CYAN}; border: 1px solid {BORDER}; border-bottom: none; }}
QTabBar::tab:hover:!selected {{ color: {TEXT}; }}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit {{
    background-color: {PANEL}; border: 1px solid {BORDER}; color: {TEXT}; padding: 4px 6px;
    border-radius: 0; selection-background-color: #0f4a57;
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border-color: {CYAN}; }}
QComboBox::drop-down {{ border: none; border-left: 1px solid {BORDER}; width: 20px; background: {PANEL_HI}; }}
QComboBox::down-arrow {{ image: url(@ASSETS@/arrow_down.png); width: 9px; height: 5px; }}
QSpinBox, QDoubleSpinBox {{ padding-right: 18px; }}
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-origin: border; subcontrol-position: top right; width: 16px; border-left: 1px solid {BORDER};
    background: {PANEL_HI};
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border; subcontrol-position: bottom right; width: 16px; border-left: 1px solid {BORDER};
    background: {PANEL_HI};
}}
QSpinBox::up-button:hover, QSpinBox::down-button:hover, QDoubleSpinBox::up-button:hover,
QDoubleSpinBox::down-button:hover {{ background: #0f3a44; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url(@ASSETS@/arrow_up.png); width: 9px; height: 5px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url(@ASSETS@/arrow_down.png); width: 9px; height: 5px; }}
QLabel, QCheckBox {{ background: transparent; }}
QComboBox QAbstractItemView {{
    background: {PANEL}; border: 1px solid {BORDER}; selection-background-color: #0f4a57; outline: 0;
}}
QPushButton {{
    background-color: {PANEL_HI}; color: {TEXT}; border: 1px solid {BORDER}; padding: 5px 12px;
    border-radius: 0; min-width: 56px;
}}
QPushButton:hover {{ border-color: {CYAN}; color: #ffffff; }}
QPushButton:pressed {{ background: #0b2a31; }}
QPushButton:disabled {{ color: {DIMMER}; border-color: {GRID}; }}
QPushButton#startBtn {{ background: #0c2a1a; border-color: #1f8f4a; color: {OK}; font-weight: bold; }}
QPushButton#startBtn:hover {{ background: #13663a; color: #ffffff; }}
QPushButton#stopBtn {{ background: #2e1214; border-color: #b83a43; color: {FAIL}; font-weight: bold; }}
QPushButton#stopBtn:hover {{ background: #8d2a31; color: #ffffff; }}
QPushButton#primary {{ background: #0a3038; border-color: {CYAN}; color: {CYAN}; font-weight: bold; }}
QPushButton#primary:hover {{ background: #0f5766; color: #ffffff; }}
QTableWidget, QTableView, QListWidget, QTreeWidget {{
    background-color: {PANEL}; border: 1px solid {BORDER}; gridline-color: {GRID};
    selection-background-color: #0f3a44; selection-color: #ffffff; outline: 0; alternate-background-color: {PANEL_HI};
}}
QTableWidget::item {{ padding: 3px 6px; border: none; }}
QHeaderView::section {{
    background-color: {PANEL_HI}; color: {DIM}; border: none; border-right: 1px solid {BORDER};
    border-bottom: 1px solid {BORDER}; padding: 5px 8px; font-size: 8pt; letter-spacing: 1px;
}}
QScrollBar:vertical {{ background: {BG}; width: 8px; border: none; }}
QScrollBar::handle:vertical {{ background: #22343f; min-height: 20px; border-radius: 0; }}
QScrollBar::handle:vertical:hover {{ background: #33505e; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ background: {BG}; height: 8px; border: none; }}
QScrollBar::handle:horizontal {{ background: #22343f; min-width: 20px; border-radius: 0; }}
QScrollBar::handle:horizontal:hover {{ background: #33505e; }}
QSplitter::handle {{ background-color: {BORDER}; }}
QStatusBar {{ background-color: {PANEL}; color: {DIM}; border-top: 1px solid {BORDER}; }}
QStatusBar::item {{ border: none; }}
QMessageBox, QDialog {{ background-color: {PANEL}; }}
QMessageBox QPushButton {{ min-width: 80px; }}
QFormLayout QLabel {{ color: {DIM}; }}
QCheckBox {{ color: {TEXT}; spacing: 6px; }}
QCheckBox::indicator {{ width: 13px; height: 13px; border: 1px solid #2c4150; border-radius: 0; background: {BG}; }}
QCheckBox::indicator:checked {{ background: {CYAN}; border-color: {CYAN}; }}
QScrollArea {{ border: none; background: transparent; }}
QMenu {{ background-color: {PANEL}; color: {TEXT}; border: 1px solid #2c4150; padding: 2px; }}
QMenu::item {{ padding: 5px 26px 5px 22px; border: 1px solid transparent; }}
QMenu::item:selected {{ background-color: #0f3a44; border-color: #1b6677; color: #ffffff; }}
QMenu::item:disabled {{ color: {DIM}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 3px 4px; }}
QMenu::indicator {{ width: 12px; height: 12px; margin-left: 5px; border: 1px solid #2c4150; background: {BG}; border-radius: 0; }}
QMenu::indicator:checked {{ background: {CYAN}; border-color: {CYAN}; }}
QGroupBox {{ border: 1px solid {BORDER}; margin-top: 10px; padding-top: 8px; border-radius: 0; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 8px; color: {DIM}; padding: 0 4px; }}
"""


def build_qss(assets_dir: str) -> str:
    """The application stylesheet with the arrow image paths filled in."""
    return APP_QSS.replace("@ASSETS@", assets_dir.replace("\\", "/"))
