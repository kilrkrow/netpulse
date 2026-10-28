"""NetPulse - Network Diagnostic Tool.

Entry point: applies the instrument theme, starts the root-cause runtime and launches MainWindow.

Command line:
  --background         start hidden in the system tray (used by Start with Windows)
  --simulate NAME      feed a scripted network (healthy, gateway-outage, dish-outage, internet-outage,
                       cant-tell, loss, latency, ratelimit, measuring, history) into the real UI.
                       The environment variable NETPULSE_SIMULATE does the same. Not shown anywhere in the UI.
"""

APP_VERSION = "1.4.5"

import argparse
import os
import sys

os.environ.setdefault("PYQTGRAPH_QT_LIB", "PySide6")

import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow
from ui.rc import theme
from ui.rc.runtime import RcRuntime, resource_path
from ui.rc.tray import app_icon

pg.setConfigOptions(antialias=True, background=theme.BG, foreground=theme.TEXT)

APP_ID = "kilrkrow.NetPulse"


def _parse_args(argv):
    ap = argparse.ArgumentParser(prog="NetPulse", add_help=False)
    ap.add_argument("--background", action="store_true")
    ap.add_argument("--simulate", nargs="?", const="healthy", default=None)
    args, _unknown = ap.parse_known_args(argv)
    if args.simulate is None:
        args.simulate = os.environ.get("NETPULSE_SIMULATE") or None
    return args


def _set_app_id():
    """Give the process its own taskbar identity so Windows shows the NetPulse icon, not Python's."""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except Exception:
            pass


def _single_instance(name: str):
    """Return (server, None) for the first instance, or (None, True) after asking a running one to show itself."""
    sock = QLocalSocket()
    sock.connectToServer(name)
    if sock.waitForConnected(300):
        sock.write(b"show")
        sock.flush()
        sock.waitForBytesWritten(300)
        sock.disconnectFromServer()
        return None, True
    QLocalServer.removeServer(name)
    server = QLocalServer()
    server.listen(name)
    return server, False


def main():
    args = _parse_args(sys.argv[1:])
    _set_app_id()
    app = QApplication(sys.argv)
    app.setApplicationName("NetPulse")
    app.setApplicationVersion(APP_VERSION)
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(theme.build_qss(resource_path(os.path.join("assets", "ui"))))
    app.setWindowIcon(app_icon())

    name = "NetPulse-single-instance" + ("-sim" if args.simulate else "")
    server, already = _single_instance(name)
    if already:
        return 0

    try:
        rt = RcRuntime(APP_VERSION, args.simulate)
    except ValueError as exc:
        sys.stderr.write(f"{exc}\n")
        return 2

    window = MainWindow(rt)
    server.newConnection.connect(lambda: (server.nextPendingConnection(), window._show_window()))
    rt.start()
    if not args.background:
        window.show()
    code = app.exec()
    rt.stop()
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass
    os._exit(code)          # leave no helper thread behind: Exit must end the process


if __name__ == "__main__":
    sys.exit(main())
