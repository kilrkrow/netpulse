"""Developer helper: render the real main window in simulation mode and save widget grabs as PNG files.

    python tools/shots.py OUTDIR [scenario ...]

Uses Qt's own widget grab, so it needs no screen capture permission. Not used by the shipped app.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("PYQTGRAPH_QT_LIB", "PySide6")

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication     # noqa: E402

import main as app_main                         # noqa: E402
from ui.main_window import MainWindow           # noqa: E402
from ui.rc import theme                         # noqa: E402
from ui.rc.runtime import RcRuntime, resource_path             # noqa: E402


def wait(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def main():
    out = sys.argv[1]
    names = sys.argv[2:] or ["healthy"]
    os.makedirs(out, exist_ok=True)
    app = QApplication(sys.argv[:1])
    app.setApplicationName("NetPulse")
    app.setApplicationVersion(app_main.APP_VERSION)
    app.setStyleSheet(theme.build_qss(resource_path(os.path.join("assets", "ui"))))
    for name in names:
        rt = RcRuntime(app_main.APP_VERSION, None if name == "live" else name)
        win = MainWindow(rt)
        win.resize(1280, 800)
        win.show()
        rt.start()
        wait(14000 if name == "live" else 2500)
        win.grab().save(os.path.join(out, f"{name}.png"))
        if name == "history":
            for idx, tab in ((1, "outage-log"), (2, "tool-monitor"), (3, "tool-traceroute"), (4, "tool-dossier"),
                             (5, "tool-alerts")):
                win._tabs.setCurrentIndex(idx)
                wait(600)
                win.grab().save(os.path.join(out, tab + ".png"))
        rt.stop()
        win._tray_mgr.hide()
        win.deleteLater()
    print("done")


if __name__ == "__main__":
    main()
