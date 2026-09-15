"""NetPulse Pro - Command Center entry point.

Classic tabs remain available via the rail "Classic" button (ui.main_window).
"""

APP_VERSION = "2.0.0-pro"

import os
import sys

os.environ.setdefault("PYQTGRAPH_QT_LIB", "PySide6")

from PySide6.QtWidgets import QApplication

from ui.pro_shell import ProShell, make_pulse_icon
from ui.theme import PRO_STYLE


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("NetPulse Pro")
    app.setOrganizationName("NetPulse")
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(make_pulse_icon())
    app.setStyleSheet(PRO_STYLE)
    win = ProShell()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
