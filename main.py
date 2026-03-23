"""NetPulse - Network Diagnostic Tool.

Entry point: configures pyqtgraph, applies dark theme, launches MainWindow.
"""

APP_VERSION = "1.2.0"

import os
import sys

os.environ.setdefault("PYQTGRAPH_QT_LIB", "PySide6")

import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow

pg.setConfigOptions(antialias=True, background="#0d1117", foreground="#c9d1d9")


DARK_STYLE = """
QMainWindow, QDialog {
    background-color: #0d1117;
}
QWidget {
    background-color: #0d1117;
    color: #c9d1d9;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 10pt;
}
QTabWidget::pane {
    border: 1px solid #30363d;
    background-color: #161b22;
}
QTabBar::tab {
    background-color: #0d1117;
    color: #8b949e;
    border: 1px solid transparent;
    border-bottom: none;
    padding: 7px 18px;
    min-width: 100px;
    font-size: 10pt;
}
QTabBar::tab:selected {
    background-color: #161b22;
    color: #c9d1d9;
    border: 1px solid #30363d;
    border-bottom: none;
}
QTabBar::tab:hover:!selected {
    color: #c9d1d9;
}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #161b22;
    border: 1px solid #30363d;
    color: #c9d1d9;
    padding: 5px 8px;
    border-radius: 4px;
    selection-background-color: #1f6feb;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border-color: #58a6ff;
}
QComboBox::drop-down {
    border: none;
    border-left: 1px solid #30363d;
    width: 22px;
    background-color: #21262d;
    border-radius: 0 3px 3px 0;
}
QComboBox::down-arrow {
    border-left:  5px solid transparent;
    border-right: 5px solid transparent;
    border-top:   6px solid #8b949e;
    width: 0;
    height: 0;
}
QComboBox::down-arrow:hover {
    border-top-color: #c9d1d9;
}
QComboBox QAbstractItemView {
    background-color: #161b22;
    border: 1px solid #30363d;
    selection-background-color: #1f6feb;
}
QPushButton {
    background-color: #21262d;
    color: #c9d1d9;
    border: 1px solid #30363d;
    padding: 6px 14px;
    border-radius: 4px;
    min-width: 60px;
}
QPushButton:hover {
    background-color: #30363d;
    border-color: #58a6ff;
}
QPushButton:pressed {
    background-color: #0d1117;
}
QPushButton:disabled {
    color: #484f58;
    border-color: #21262d;
}
QPushButton#startBtn {
    background-color: #1a4731;
    border-color: #2ea043;
    color: #3fb950;
    font-weight: bold;
}
QPushButton#startBtn:hover {
    background-color: #238636;
    color: #ffffff;
}
QPushButton#stopBtn {
    background-color: #3d1c1c;
    border-color: #f85149;
    color: #f85149;
    font-weight: bold;
}
QPushButton#stopBtn:hover {
    background-color: #b91c1c;
    color: #ffffff;
}
QTableWidget {
    background-color: #161b22;
    border: 1px solid #30363d;
    gridline-color: #21262d;
    selection-background-color: #1f6feb;
    selection-color: #ffffff;
    outline: none;
}
QTableWidget::item {
    padding: 4px 6px;
    border: none;
}
QTableWidget::item:selected {
    background-color: #1f6feb;
}
QHeaderView::section {
    background-color: #21262d;
    color: #8b949e;
    border: none;
    border-right: 1px solid #30363d;
    border-bottom: 1px solid #30363d;
    padding: 6px 8px;
    font-weight: bold;
    font-size: 8.5pt;
    text-transform: uppercase;
}
QScrollBar:vertical {
    background: #0d1117;
    width: 8px;
    border: none;
}
QScrollBar::handle:vertical {
    background: #30363d;
    border-radius: 4px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover {
    background: #484f58;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar:horizontal {
    background: #0d1117;
    height: 8px;
    border: none;
}
QScrollBar::handle:horizontal {
    background: #30363d;
    border-radius: 4px;
}
QSplitter::handle {
    background-color: #30363d;
}
QStatusBar {
    background-color: #161b22;
    color: #8b949e;
}
QMessageBox {
    background-color: #161b22;
}
QMessageBox QPushButton {
    min-width: 80px;
}
QDialog {
    background-color: #161b22;
}
QFormLayout QLabel {
    color: #8b949e;
}
QCheckBox {
    color: #c9d1d9;
    spacing: 6px;
}
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #30363d;
    border-radius: 3px;
    background: #0d1117;
}
QCheckBox::indicator:checked {
    background: #238636;
    border-color: #2ea043;
}
QScrollArea {
    border: none;
}
QScrollArea > QWidget > QWidget {
    background: #0d1117;
}
"""


def _app_icon() -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QBrush(QColor("#3fb950")))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(4, 4, 56, 56)
    painter.setBrush(QBrush(QColor("#0d1117")))
    painter.drawEllipse(14, 14, 36, 36)
    painter.setBrush(QBrush(QColor("#3fb950")))
    painter.drawEllipse(26, 26, 12, 12)
    painter.end()
    return QIcon(pixmap)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("NetPulse")
    app.setApplicationDisplayName("NetPulse")
    app.setApplicationVersion(APP_VERSION)
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(DARK_STYLE)
    app.setWindowIcon(_app_icon())
    app.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
