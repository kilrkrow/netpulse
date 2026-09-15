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
    color: {TEXT};
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 10pt;
}}
/* Do NOT set opaque background on all QWidgets — that paints black plates under labels. */
QLabel {{
    background-color: transparent;
    color: {TEXT};
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
QFrame#Rail {{
    background-color: #0b0f14;
    border-right: 1px solid {BORDER};
}}
QFrame#TopBar, QFrame#FooterStrip {{
    background-color: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
QFrame#HopCard {{
    background-color: {PANEL_GLASS};
    border: 2px solid {BORDER};
    border-radius: 12px;
}}
QFrame#HopCard:hover {{
    border-color: {EMERALD};
}}
QFrame#HopCard QLabel {{
    background-color: transparent;
}}
QLineEdit#TargetEdit, QComboBox#TargetCombo, QComboBox {{
    background-color: #0b0f14;
    border: 1px solid {BORDER};
    color: {TEXT};
    padding: 8px 12px;
    border-radius: 8px;
    selection-background-color: {EMERALD};
    min-height: 20px;
}}
QComboBox QAbstractItemView {{
    background-color: {PANEL};
    color: {TEXT};
    selection-background-color: #243044;
}}
QLineEdit#TargetEdit:focus, QComboBox#TargetCombo:focus, QComboBox:focus {{
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
QPushButton#ModeToggle:disabled {{
    color: #4b5563;
    border-color: {BORDER};
}}
QLabel#HopTitle {{
    color: {TEXT};
    font-weight: 600;
    font-size: 10pt;
    background: transparent;
}}
QLabel#HopMeta {{
    color: {MUTED};
    font-size: 9pt;
    background: transparent;
}}
QLabel#HopLatency {{
    color: {EMERALD};
    font-weight: 600;
    font-size: 11pt;
    background: transparent;
}}
QLabel#HopLatencyFail {{
    color: {CORAL};
    font-weight: 600;
    font-size: 11pt;
    background: transparent;
}}
QLabel#FooterLabel {{
    color: {MUTED};
    font-size: 9pt;
    background: transparent;
}}
QLabel#FooterValue {{
    color: {TEXT};
    font-size: 9pt;
    background: transparent;
}}
QLabel#EmptyHint {{
    color: {MUTED};
    font-size: 12pt;
    background: transparent;
}}
QScrollArea {{
    border: none;
    background: transparent;
}}
QScrollArea > QWidget > QWidget {{
    background: transparent;
}}
QAbstractScrollArea {{
    background-color: transparent;
}}
QTableWidget {{
    background-color: {PANEL};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 8px;
    gridline-color: {BORDER};
    alternate-background-color: #141a22;
}}
QTableWidget::item {{
    background-color: transparent;
    color: {TEXT};
    padding: 4px;
}}
QTableWidget::item:selected {{
    background-color: #3a2e14;
    color: {TEXT};
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
QStatusBar QLabel {{
    background: transparent;
}}
QMessageBox {{
    background-color: {PANEL};
}}
QMessageBox QLabel {{
    background: transparent;
    color: {TEXT};
}}
QSplitter::handle {{
    background-color: {BORDER};
    width: 2px;
}}
QToolTip {{
    background-color: {PANEL};
    color: {TEXT};
    border: 1px solid {BORDER};
}}
"""
