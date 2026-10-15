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


def grab_ip_research(win, out):
    page = win._path_page
    page.ip.settings.value.lookups_allowed = True
    page.ip.settings.value.lookups_notice_seen = True
    page.ip._refresh_notice()
    page.path.select(len(page._snap.hops) - 1)
    page._on_hop_selected(len(page._snap.hops) - 1)          # the target, 1.1.1.1: a public address
    wait(6000)
    win.grab().save(os.path.join(out, "ip-research.png"))


def grab_tools(win, out):
    from PySide6.QtCore import Qt
    win._tabs.setCurrentIndex(2)
    win._monitor_tab.add_session("1.1.1.1")
    win._monitor_tab.add_session("8.8.8.8")
    wait(9000)
    win.grab().save(os.path.join(out, "tool-monitor.png"))
    win._monitor_tab.stop_all() if hasattr(win._monitor_tab, "stop_all") else None
    win._tabs.setCurrentIndex(4)
    win._dossier_tab._lookup_combo.lineEdit().setText("1.1.1.1")
    win._dossier_tab._lookup()
    wait(9000)
    win.grab().save(os.path.join(out, "tool-dossier.png"))
    win._tabs.setCurrentIndex(3)
    win._tracer_tab.set_target("1.1.1.1")
    win._tracer_tab._run()
    wait(40000)
    t = win._tracer_tab._table
    for r in range(t.rowCount()):                         # never render this network's real hops: mask before grabbing
        for c in (1, 2):
            it = t.item(r, c)
            if it is not None:
                it.setText("[masked]")
    wait(300)
    win.grab().save(os.path.join(out, "tool-traceroute.png"))
    win._tabs.setCurrentIndex(5)
    wait(500)
    win.grab().save(os.path.join(out, "tool-alerts.png"))


def main():
    out = sys.argv[1]
    names = sys.argv[2:] or ["healthy"]
    os.makedirs(out, exist_ok=True)
    app = QApplication(sys.argv[:1])
    app.setApplicationName("NetPulse")
    app.setApplicationVersion(app_main.APP_VERSION)
    app.setStyleSheet(theme.build_qss(resource_path(os.path.join("assets", "ui"))))
    for name in names:
        rt = RcRuntime(app_main.APP_VERSION, {"live": None, "ip-research": "healthy", "tools": "healthy"}.get(name, name))
        win = MainWindow(rt)
        win.resize(1280, 800)
        win.show()
        rt.start()
        wait(14000 if name == "live" else 2500)
        win.grab().save(os.path.join(out, f"{name}.png"))
        if name == "ip-research":
            grab_ip_research(win, out)
        if name == "tools":
            grab_tools(win, out)
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
