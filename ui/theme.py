"""NetPulse Pro theme tokens and stylesheet."""

EMERALD = "#2dd4a8"
CORAL = "#f87171"
CHARCOAL = "#0f1419"
PANEL = "#161b22"
PANEL_GLASS = "#1c2330"
BORDER = "#2a3340"
TEXT = "#e6edf3"
MUTED = "#8b949e"
AMBER = "#fbbf24"

PRO_STYLE = f"""
QMainWindow, QDialog {{
    background-color: {CHARCOAL};
}}
QWidget {{
    background-color: {CHARCOAL};
    color: {TEXT};
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 10pt;
}}
QFrame#Rail {{
    background-color: #0b0f14;
    border-right: 1px solid {BORDER};
}}
QToolButton#RailBtn {{
    background: transparent;
    color: {MUTED};
    border: none;
    border-radius: 8px;
    padding: 10px 6px;
    font-size: 9pt;
}}
QToolButton#RailBtn:hover {{
    background-color: {PANEL_GLASS};
    color: {TEXT};
}}
QToolButton#RailBtn:checked {{
    background-color: {PANEL};
    color: {EMERALD};
    border: 1px solid {BORDER};
}}
QFrame#TopBar, QFrame#FooterStrip {{
    background-color: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
QLineEdit#TargetEdit, QComboBox#TargetCombo {{
    background-color: #0b0f14;
    border: 1px solid {BORDER};
    color: {TEXT};
    padding: 8px 12px;
    border-radius: 8px;
    selection-background-color: {EMERALD};
    min-height: 20px;
}}
QLineEdit#TargetEdit:focus, QComboBox#TargetCombo:focus {{
    border-color: {EMERALD};
}}
QPushButton#PrimaryRun {{
    background-color: {EMERALD};
    color: #04140f;
    border: none;
    border-radius: 8px;
    padding: 8px 22px;
    font-weight: 600;
}}
QPushButton#PrimaryRun:hover {{
    background-color: #5eead4;
}}
QPushButton#PrimaryRun:disabled {{
    background-color: #1f6b55;
    color: #0a2018;
}}
QPushButton#ModeToggle {{
    background-color: #0b0f14;
    color: {MUTED};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 12px;
}}
QPushButton#ModeToggle:checked {{
    color: {EMERALD};
    border-color: {EMERALD};
}}
QFrame#HopCard {{
    background-color: {PANEL_GLASS};
    border: 1px solid {BORDER};
    border-radius: 12px;
}}
QFrame#HopCard:hover {{
    border-color: {EMERALD};
}}
QLabel#HopTitle {{
    color: {TEXT};
    font-weight: 600;
    font-size: 10pt;
}}
QLabel#HopMeta {{
    color: {MUTED};
    font-size: 9pt;
}}
QLabel#HopLatency {{
    color: {EMERALD};
    font-weight: 600;
    font-size: 11pt;
}}
QLabel#HopLatencyFail {{
    color: {CORAL};
    font-weight: 600;
    font-size: 11pt;
}}
QLabel#FooterLabel {{
    color: {MUTED};
    font-size: 9pt;
}}
QLabel#FooterValue {{
    color: {TEXT};
    font-size: 9pt;
}}
QLabel#EmptyHint {{
    color: {MUTED};
    font-size: 12pt;
}}
QScrollArea {{
    border: none;
    background: transparent;
}}
QTableWidget {{
    background-color: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 8px;
    gridline-color: {BORDER};
}}
QHeaderView::section {{
    background-color: #0b0f14;
    color: {MUTED};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 6px;
}}
QMenu {{
    background-color: {PANEL};
    border: 1px solid {BORDER};
    color: {TEXT};
}}
QMenu::item:selected {{
    background-color: #243044;
}}
QMenu::separator {{
    height: 1px;
    background: {BORDER};
    margin: 4px 8px;
}}
QStatusBar {{
    background: #0b0f14;
    color: {MUTED};
}}
QMessageBox {{
    background-color: {PANEL};
}}
"""
