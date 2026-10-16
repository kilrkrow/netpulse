"""Main window with toolbar, tabs, and system tray integration."""

import csv
import datetime
import json
import os

from PySide6.QtCore import QSize, Qt, QTimer, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QSystemTrayIcon,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.alerts import AlertManager
from core.dossier import DossierEngine
from core.ping_engine import PingStats
from core.traceroute import TracerouteEngine
from ui.alerts_tab import AlertsTab
from ui.dossier_tab import DossierTab
from ui.monitor_tab import MonitorTab
from ui.traceroute_tab import TracerouteTab
from ui.rc.page import OutagePanel, PathPage
from ui.rc.settings_dialog import SettingsDialog
from ui.rc.tray import TrayManager, app_icon
from ui.rc.widgets import harden_text


class _TabCorner(QWidget):
    """The widget at the right end of the tab row. QTabWidget sizes the tab bar from sizeHint(), which a style sheet
    can shrink below the real button sizes, so it is pinned to the exact size the buttons need."""

    def __init__(self, w: int, h: int):
        super().__init__()
        self._fixed = QSize(w, h)
        self.setFixedSize(self._fixed)

    def sizeHint(self) -> QSize:
        return self._fixed

    def minimumSizeHint(self) -> QSize:
        return self._fixed


class MainWindow(QMainWindow):
    def __init__(self, runtime=None):
        super().__init__()
        self.rt = runtime
        self._in_outage = False
        self._bad_streak = 0
        self._good_streak = 0
        self._last_headline = ""
        self._hint_shown = False
        self.setWindowIcon(app_icon())
        self.setWindowTitle("NetPulse - Network Diagnostic Tool")
        self.resize(1280, 860)
        self.setMinimumSize(900, 640)

        self._current_stats: PingStats | None = None
        self._session_start: datetime.datetime | None = None

        self._alert_mgr = AlertManager()
        self._tracer = TracerouteEngine()
        self._dossier = DossierEngine()

        self._quitting = False
        self._build_ui()
        self._build_tray()
        self._connect_signals()

        self._sb_timer = QTimer()
        self._sb_timer.timeout.connect(self._update_status_bar)
        self._sb_timer.start(1000)

        if self.rt and self.rt.is_sim:
            self._monitor_tab._proc_combo.clear()      # a simulated run never shows this PC's real processes or history
        else:
            self._load_history()
        self._wire_runtime()
        harden_text(self)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 4)
        root.setSpacing(6)

        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)

        self._monitor_tab = MonitorTab(self._alert_mgr)
        self._tracer_tab = TracerouteTab(self._tracer)
        self._dossier_tab = DossierTab(self._dossier)
        self._alerts_tab = AlertsTab(self._alert_mgr)

        self._path_page = PathPage(self.rt.ctl, self.rt.settings) if self.rt else QWidget()
        self._outage_page = OutagePanel(self.rt.ctl) if self.rt else QWidget()
        self._tabs.addTab(self._path_page, "Path")
        self._tabs.addTab(self._outage_page, "Outages")
        self._tabs.addTab(self._monitor_tab, "Monitor")
        self._tabs.addTab(self._tracer_tab, "Traceroute")
        self._tabs.addTab(self._dossier_tab, "Dossier")
        self._tabs.addTab(self._alerts_tab, "Alerts")
        self._tabs.setCornerWidget(self._build_corner(), Qt.Corner.TopRightCorner)
        root.addWidget(self._tabs)

        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)

        self._sb_label = QLabel("Starting...")
        self._sb_label.setStyleSheet("padding: 2px 6px;")
        self._status_bar.addWidget(self._sb_label)

        self._sb_right = QLabel("")
        self._sb_right.setStyleSheet("padding: 2px 6px;")
        self._status_bar.addPermanentWidget(self._sb_right)

        ver = QApplication.applicationVersion()
        self._sb_version = QLabel(f"v{ver}")
        self._sb_version.setStyleSheet("color: #52666f; padding: 2px 8px; font-size: 8pt;")
        if self.rt and self.rt.is_sim:
            sim = QLabel("SIMULATED DATA")
            sim.setStyleSheet("color: #ffb43f; padding: 2px 8px; font-size: 8pt; font-weight: bold;")
            self._status_bar.addPermanentWidget(sim)
        self._status_bar.addPermanentWidget(self._sb_version)

    def _build_corner(self) -> QWidget:
        """Settings and Export sit in the tab row itself (right end), so nothing is stacked above the tabs and no
        tab ever changes the height of the row. The Interval / Timeout / Graph controls live in the Settings dialog.

        Spacing: 24 px tall buttons centred in the 30 px tab row (3 px above and below, so they never touch the
        pane border), 6 px between buttons (same as the Monitor tab row), the same 8 px window margin on the right."""
        row_h, btn_h, gap = 30, 24, 6
        fm = self.fontMetrics()
        btn_w = max(82, max(fm.horizontalAdvance(s) for s in ("Settings", "Export")) + 24)    # 82 px with Segoe UI
        box = _TabCorner(btn_w * 2 + gap, row_h)
        lay = QHBoxLayout(box)
        lay.setContentsMargins(0, (row_h - btn_h) // 2, 0, (row_h - btn_h) // 2)
        lay.setSpacing(gap)

        self._settings_btn = QPushButton("Settings")
        self._settings_btn.setToolTip("Probe target, ping defaults (interval, timeout, graph), notifications and labels")
        self._settings_btn.setEnabled(bool(self.rt))
        self._settings_btn.clicked.connect(self._open_settings)
        lay.addWidget(self._settings_btn)

        self._export_btn = QPushButton("Export")
        self._export_btn.setToolTip("Save the Monitor tab ping results as CSV")
        self._export_btn.clicked.connect(self._export_csv)
        lay.addWidget(self._export_btn)

        for b in (self._settings_btn, self._export_btn):
            b.setFixedSize(btn_w, btn_h)
            b.setStyleSheet("padding: 0 8px; min-width: 0;")
        return box

    def _build_tray(self):
        self._tray_mgr = TrayManager(
            self, on_show=self._show_window, on_copy=self._copy_report, on_settings=self._open_settings,
            on_about=self._show_about, on_exit=self._exit_app, simulate=bool(self.rt and self.rt.is_sim))
        self._tray = self._tray_mgr.tray
        self._tray.activated.connect(self._tray_activated)
        self._tray.messageClicked.connect(self._on_notification_clicked)
        self._tray_mgr.show()
        self._last_alert_host: str = ""  # host from most recent alert notification

    def _wire_runtime(self):
        if not self.rt:
            return
        self._apply_monitor_settings()
        self.rt.bridge.updated.connect(self._on_rc_update)
        self.rt.bridge.outages_changed.connect(self._outage_page.refresh)
        self._path_page.copy_report.connect(self._copy_report)
        self._path_page.open_settings.connect(self._open_settings)
        self._outage_page.copy_report.connect(self._copy_report)
        if self.rt.error:
            self._sb_label.setText("  " + self.rt.error)

    @Slot(object, object)
    def _on_rc_update(self, snap, verdict):
        self._path_page.update_data(snap, verdict)
        self._tray_mgr.set_verdict(verdict.kind, verdict.headline)
        self._last_headline = verdict.headline
        if not self._current_stats:
            self._sb_label.setText("  " + verdict.headline)
        # notifications: require two bad (or good) evaluations in a row so one blip never pops a balloon
        if verdict.kind == "outage":
            self._bad_streak, self._good_streak = self._bad_streak + 1, 0
        elif verdict.kind == "healthy":
            self._good_streak, self._bad_streak = self._good_streak + 1, 0
        if self.rt.settings.value.notifications and not self.rt.is_sim:
            if verdict.kind == "outage" and not self._in_outage and self._bad_streak >= 2:
                self._in_outage = True
                self._tray_mgr.notify("NetPulse: connection problem", verdict.headline, warn=True)
            elif verdict.kind == "healthy" and self._in_outage and self._good_streak >= 3:
                self._in_outage = False
                self._tray_mgr.notify("NetPulse: back online", "The connection is answering again.")
        elif verdict.kind == "healthy":
            self._in_outage = False

    def _copy_report(self):
        if not self.rt:
            return
        QGuiApplication.clipboard().setText(self.rt.ctl.report_text())
        self._tray_mgr.notify("NetPulse", "Report copied to the clipboard.")
        self._sb_label.setText("  Report copied to the clipboard")

    def _open_settings(self):
        if not self.rt:
            return
        self.show()
        self._settings_dialog().exec()

    def _settings_dialog(self) -> SettingsDialog:
        return SettingsDialog(self.rt.settings, on_applied=self._apply_settings, parent=self)

    def _apply_settings(self):
        self.rt.apply_settings()
        self._apply_monitor_settings()

    def _apply_monitor_settings(self):
        """Interval / Timeout / Graph become the defaults of the Monitor tab's next ping sessions."""
        s = self.rt.settings.value
        self._monitor_tab.set_interval(s.ping_interval_ms)
        self._monitor_tab.set_timeout(s.ping_timeout_ms)
        self._monitor_tab.set_window(s.graph_points)

    def _show_window(self):
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        self.raise_()
        self.activateWindow()

    def _exit_app(self):
        self._quitting = True
        self._tray_mgr.hide()
        QApplication.quit()

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------
    def _connect_signals(self):
        # MonitorTab -> MainWindow
        self._monitor_tab.worst_stats_updated.connect(self._on_stats)
        self._monitor_tab.session_started.connect(self._on_session_started)
        self._monitor_tab.any_running_changed.connect(self._on_any_running_changed)

        # Alert manager
        self._alert_mgr.alert_triggered.connect(self._on_alert)

        # Traceroute -> Monitor hop
        self._tracer_tab.monitor_requested.connect(self._on_monitor_hop_requested)

        # Traceroute pause/resume
        self._tracer.started.connect(self._on_tracer_started)
        self._tracer.finished.connect(self._on_tracer_done)
        self._tracer.error_occurred.connect(self._on_tracer_error)

        # Dossier history save
        self._dossier.finished.connect(self._on_dossier_done)

    # ------------------------------------------------------------------
    # History persistence
    # ------------------------------------------------------------------
    def _history_file(self) -> str:
        base = os.environ.get('APPDATA') or os.path.expanduser('~')
        folder = os.path.join(base, 'NetPulse')
        os.makedirs(folder, exist_ok=True)
        return os.path.join(folder, 'history.json')

    def _load_history(self):
        try:
            with open(self._history_file(), encoding='utf-8') as f:
                data = json.load(f)
            self._monitor_tab.load_history(data.get('ping', ['google.com']))
            self._tracer_tab.load_history(data.get('tracert', []))
            self._dossier_tab.load_history(data.get('dossier', []))
        except Exception:
            pass

    def _save_history(self):
        if self.rt and self.rt.is_sim:
            return
        try:
            data = {
                'ping':    self._monitor_tab.get_history(),
                'tracert': self._tracer_tab.get_history(),
                'dossier': self._dossier_tab.get_history(),
            }
            with open(self._history_file(), 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # MonitorTab signal handlers
    # ------------------------------------------------------------------
    @Slot(str)
    def _on_session_started(self, host: str):
        """Push the new host into tracert/dossier history and save."""
        self._tracer_tab.add_to_history(host)
        self._dossier_tab.notify_host(host)
        self._session_start = self._session_start or datetime.datetime.now()
        self._save_history()

    @Slot(bool)
    def _on_any_running_changed(self, running: bool):
        if not running:
            self._session_start = None
            self._current_stats = None
            self._sb_label.setText("  " + (self._last_headline or "Ready"))
            self._sb_right.setText("")

    @Slot(object)
    def _on_stats(self, stats: PingStats):
        self._current_stats = stats

    # ------------------------------------------------------------------
    # Traceroute pause / resume
    # ------------------------------------------------------------------
    @Slot()
    def _on_tracer_started(self):
        if self._monitor_tab.any_paused is False and self._current_stats:
            self._monitor_tab.pause_all()
            self._sb_label.setText(
                f"  Ping paused: traceroute in progress  ({self._current_stats.host})"
            )

    @Slot(list)
    def _on_tracer_done(self, hops):
        self._monitor_tab.resume_all()
        self._save_history()

    @Slot(str)
    def _on_tracer_error(self, _msg: str):
        self._monitor_tab.resume_all()

    @Slot(str)
    def _on_monitor_hop_requested(self, ip: str):
        """Switch to Monitor tab and start pinging the requested hop IP."""
        monitor_idx = self._tabs.indexOf(self._monitor_tab)
        self._tabs.setCurrentIndex(monitor_idx)
        self._monitor_tab.add_session(ip)

    @Slot(int, object)
    def _on_dossier_done(self, request_id, result):
        self._save_history()

    # ------------------------------------------------------------------
    # Tray icon
    # ------------------------------------------------------------------
    @Slot(object)
    def _on_alert(self, event):
        self._last_alert_host = event.host
        msg = event.message
        if event.host:
            msg += "\n\nClick to run traceroute"
        self._tray.showMessage(
            "NetPulse Alert",
            msg,
            QSystemTrayIcon.MessageIcon.Warning,
            6000,
        )

    @Slot()
    def _on_notification_clicked(self):
        """User clicked a tray alert balloon - open app and launch traceroute."""
        self.show()
        self.raise_()
        self.activateWindow()
        if self._last_alert_host:
            tracer_idx = self._tabs.indexOf(self._tracer_tab)
            self._tabs.setCurrentIndex(tracer_idx)
            self._tracer_tab.set_target(self._last_alert_host)

    # ------------------------------------------------------------------
    # Status bar
    # ------------------------------------------------------------------
    def _update_status_bar(self):
        if self._monitor_tab.any_paused:
            return  # keep the "paused" message visible
        if not self._current_stats:
            return
        stats = self._current_stats
        rtt_str = f"{stats.last_rtt:.0f} ms" if stats.last_rtt is not None else "Timeout"
        self._sb_label.setText(
            f"  {stats.host}    RTT: {rtt_str}    "
            f"Loss: {stats.loss_pct:.1f}%    Samples: {stats.samples}"
        )
        if self._session_start:
            elapsed = datetime.datetime.now() - self._session_start
            hours, remainder = divmod(int(elapsed.total_seconds()), 3600)
            minutes, seconds = divmod(remainder, 60)
            self._sb_right.setText(f"Session: {hours:02d}:{minutes:02d}:{seconds:02d}")

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------
    def _export_csv(self):
        all_results = self._monitor_tab.get_all_results()
        if not all_results:
            QMessageBox.information(self, "Export", "No data to export yet.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Export Ping History", "netpulse_export.csv", "CSV Files (*.csv)"
        )
        if not path:
            return

        with open(path, "w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["Session", "Timestamp", "Host", "Seq", "RTT_ms", "TTL", "IP", "Error"])
            for label, result in all_results:
                writer.writerow([
                    label,
                    result.timestamp.isoformat(),
                    result.host,
                    result.seq,
                    result.rtt_ms if result.rtt_ms is not None else "",
                    result.ttl or "",
                    result.resolved_ip or "",
                    result.error or "",
                ])
        QMessageBox.information(self, "Export", f"Saved to:\n{path}")

    # ------------------------------------------------------------------
    # Window / tray helpers
    # ------------------------------------------------------------------
    def closeEvent(self, event):
        if self._quitting or not QSystemTrayIcon.isSystemTrayAvailable():
            event.accept()
            return
        event.ignore()
        self.hide()
        if not self._hint_shown:
            self._hint_shown = True
            self._tray_mgr.notify("NetPulse", "Still running in the tray. Right-click the tray icon to exit.")

    def _show_about(self):
        ver = QApplication.applicationVersion()
        QMessageBox.about(
            self,
            "About NetPulse",
            f"<h3>NetPulse v{ver}</h3>"
            "<p>Network diagnostics with a guided root-cause view: path map, per-hop probes, "
            "plain-English verdict, outage log, IP research, ping, traceroute and domain dossier.</p>"
            "<p style='color:#8aa2ad; font-size:9pt;'>"
            "(c) 2026 Guy Schamp (kilrkrow)<br>"
            "Free software under the GNU General Public License v3."
            "</p>",
        )

    def _toggle_window(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.activateWindow()
            self.raise_()

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._toggle_window()
