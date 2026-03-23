"""Main window with toolbar, tabs, and system tray integration."""

import csv
import datetime
import json
import os

from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSpinBox,
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


def _make_tray_icon(color: str = "#3fb950") -> QIcon:
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QBrush(QColor(color)))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(4, 4, 24, 24)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QColor("#ffffff"))
    painter.drawEllipse(10, 10, 12, 12)
    painter.end()
    return QIcon(pixmap)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NetPulse - Network Diagnostic Tool")
        self.resize(1200, 750)
        self.setMinimumSize(900, 600)

        self._current_stats: PingStats | None = None
        self._session_start: datetime.datetime | None = None

        self._alert_mgr = AlertManager()
        self._tracer = TracerouteEngine()
        self._dossier = DossierEngine()

        self._build_ui()
        self._build_tray()
        self._connect_signals()

        self._sb_timer = QTimer()
        self._sb_timer.timeout.connect(self._update_status_bar)
        self._sb_timer.start(1000)

        self._load_history()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 4)
        root.setSpacing(6)

        root.addWidget(self._build_toolbar())

        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)

        self._monitor_tab = MonitorTab(self._alert_mgr)
        self._tracer_tab = TracerouteTab(self._tracer)
        self._dossier_tab = DossierTab(self._dossier)
        self._alerts_tab = AlertsTab(self._alert_mgr)

        self._tabs.addTab(self._monitor_tab, "Monitor")
        self._tabs.addTab(self._tracer_tab, "Traceroute")
        self._tabs.addTab(self._dossier_tab, "Dossier")
        self._tabs.addTab(self._alerts_tab, "Alerts")
        root.addWidget(self._tabs)

        self._status_bar = QStatusBar()
        self._status_bar.setStyleSheet("QStatusBar { border-top: 1px solid #30363d; }")
        self.setStatusBar(self._status_bar)

        self._sb_label = QLabel("Ready - add a target on the Monitor tab to start")
        self._sb_label.setStyleSheet("color: #8b949e; padding: 2px 6px;")
        self._status_bar.addWidget(self._sb_label)

        self._sb_right = QLabel("")
        self._sb_right.setStyleSheet("color: #8b949e; padding: 2px 6px;")
        self._status_bar.addPermanentWidget(self._sb_right)

        ver = QApplication.applicationVersion()
        self._sb_version = QLabel(f"v{ver}")
        self._sb_version.setStyleSheet("color: #484f58; padding: 2px 8px; font-size: 8pt;")
        self._status_bar.addPermanentWidget(self._sb_version)

    def _build_toolbar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("toolbar")
        bar.setStyleSheet(
            "#toolbar { background: #161b22; border: 1px solid #30363d; "
            "border-radius: 6px; padding: 4px; }"
        )

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        layout.addWidget(QLabel("Interval:"))
        self._interval_spin = QSpinBox()
        self._interval_spin.setRange(100, 60000)
        self._interval_spin.setValue(1000)
        self._interval_spin.setSuffix(" ms")
        self._interval_spin.setFixedWidth(100)
        layout.addWidget(self._interval_spin)

        layout.addWidget(QLabel("Timeout:"))
        self._timeout_spin = QSpinBox()
        self._timeout_spin.setRange(200, 10000)
        self._timeout_spin.setValue(2000)
        self._timeout_spin.setSuffix(" ms")
        self._timeout_spin.setFixedWidth(100)
        layout.addWidget(self._timeout_spin)

        layout.addWidget(QLabel("Graph:"))
        self._window_spin = QSpinBox()
        self._window_spin.setRange(30, 3600)
        self._window_spin.setValue(300)
        self._window_spin.setSuffix(" pts")
        self._window_spin.setFixedWidth(90)
        layout.addWidget(self._window_spin)

        layout.addStretch()

        self._export_btn = QPushButton("Export")
        self._export_btn.setFixedWidth(90)
        self._export_btn.clicked.connect(self._export_csv)
        layout.addWidget(self._export_btn)

        return bar

    def _build_tray(self):
        self._tray = QSystemTrayIcon(self)
        self._tray.setIcon(_make_tray_icon("#8b949e"))
        self._tray.setToolTip("NetPulse - Not running")

        menu = QMenu()
        self._tray_status_action = menu.addAction("Not running")
        self._tray_status_action.setEnabled(False)
        menu.addSeparator()

        show_action = menu.addAction("Show / Hide")
        show_action.triggered.connect(self._toggle_window)

        menu.addSeparator()
        about_action = menu.addAction("About NetPulse...")
        about_action.triggered.connect(self._show_about)

        menu.addSeparator()
        quit_action = menu.addAction("Exit NetPulse")
        quit_action.triggered.connect(QApplication.quit)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._tray_activated)
        self._tray.messageClicked.connect(self._on_notification_clicked)
        self._tray.show()

        self._last_alert_host: str = ""  # host from most recent alert notification

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------
    def _connect_signals(self):
        # Toolbar spins -> MonitorTab defaults
        self._interval_spin.valueChanged.connect(self._monitor_tab.set_interval)
        self._timeout_spin.valueChanged.connect(self._monitor_tab.set_timeout)
        self._window_spin.valueChanged.connect(self._monitor_tab.set_window)

        # MonitorTab -> MainWindow
        self._monitor_tab.worst_stats_updated.connect(self._on_stats)
        self._monitor_tab.session_started.connect(self._on_session_started)
        self._monitor_tab.any_running_changed.connect(self._on_any_running_changed)

        # Alert manager
        self._alert_mgr.alert_triggered.connect(self._on_alert)

        # Traceroute → Monitor hop
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
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        folder = os.path.join(base, "NetPulse")
        os.makedirs(folder, exist_ok=True)
        return os.path.join(folder, "history.json")

    def _load_history(self):
        try:
            with open(self._history_file(), encoding="utf-8") as f:
                data = json.load(f)
            self._monitor_tab.load_history(data.get("ping", ["google.com"]))
            self._tracer_tab.load_history(data.get("tracert", []))
            self._dossier_tab.load_history(data.get("dossier", []))
        except Exception:
            pass

    def _save_history(self):
        try:
            data = {
                "ping": self._monitor_tab.get_history(),
                "tracert": self._tracer_tab.get_history(),
                "dossier": self._dossier_tab.get_history(),
            }
            with open(self._history_file(), "w", encoding="utf-8") as f:
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
            self._tray.setIcon(_make_tray_icon("#8b949e"))
            self._tray.setToolTip("NetPulse - Stopped")
            self._tray_status_action.setText("Stopped")
            self._sb_label.setText("  Ready - add a target on the Monitor tab to start")
            self._sb_right.setText("")

    @Slot(object)
    def _on_stats(self, stats: PingStats):
        self._current_stats = stats
        self._update_tray_icon(stats)

    # ------------------------------------------------------------------
    # Traceroute pause / resume
    # ------------------------------------------------------------------
    @Slot()
    def _on_tracer_started(self):
        if self._monitor_tab.any_paused is False and self._current_stats:
            self._monitor_tab.pause_all()
            self._sb_label.setText(
                f"  Ping paused - traceroute in progress ({self._current_stats.host})"
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
    def _update_tray_icon(self, stats: PingStats):
        rtt = stats.last_rtt
        loss = stats.loss_pct
        rtt_thresh = next(
            (
                rule.threshold
                for rule in self._alert_mgr.rules
                if rule.metric == "last_rtt" and rule.operator in (">", ">=")
            ),
            100,
        )
        if rtt is None or loss > 10:
            color = "#f85149"
        elif rtt > rtt_thresh or loss > 2:
            color = "#d29922"
        else:
            color = "#3fb950"

        self._tray.setIcon(_make_tray_icon(color))
        if rtt is not None:
            self._tray.setToolTip(
                f"NetPulse - {stats.host}\nRTT: {rtt:.0f}ms  Loss: {loss:.1f}%"
            )
        self._tray_status_action.setText(f"Monitoring: {stats.host}")

    @Slot(object)
    def _on_alert(self, event):
        self._last_alert_host = event.host
        msg = event.message
        if event.host:
            msg += "\n\nClick to run traceroute →"
        self._tray.showMessage(
            "NetPulse Alert",
            msg,
            QSystemTrayIcon.MessageIcon.Warning,
            6000,
        )

    @Slot()
    def _on_notification_clicked(self):
        """User clicked a tray alert balloon — open app and launch traceroute."""
        self.show()
        self.raise_()
        self.activateWindow()
        if self._last_alert_host:
            tracer_idx = self._tabs.indexOf(self._tracer_tab)
            self._tabs.setCurrentIndex(tracer_idx)
            # Alert clicks should land on the alerted host and immediately trace it.
            self._tracer_tab.set_target(self._last_alert_host, autorun=True)

    # ------------------------------------------------------------------
    # Status bar
    # ------------------------------------------------------------------
    def _update_status_bar(self):
        if self._monitor_tab.any_paused:
            return
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
            writer.writerow(
                ["Session", "Timestamp", "Host", "Seq", "RTT_ms", "TTL", "IP", "Error"]
            )
            for label, result in all_results:
                writer.writerow(
                    [
                        label,
                        result.timestamp.isoformat(),
                        result.host,
                        result.seq,
                        result.rtt_ms if result.rtt_ms is not None else "",
                        result.ttl or "",
                        result.resolved_ip or "",
                        result.error or "",
                    ]
                )
        QMessageBox.information(self, "Export", f"Saved to:\n{path}")

    # ------------------------------------------------------------------
    # Window / tray helpers
    # ------------------------------------------------------------------
    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self._tray.showMessage(
            "NetPulse",
            "Still running in background. Right-click the tray icon to exit.",
            QSystemTrayIcon.MessageIcon.Information,
            2500,
        )

    def _show_about(self):
        ver = QApplication.applicationVersion()
        QMessageBox.about(
            self,
            "About NetPulse",
            f"<h3>NetPulse v{ver}</h3>"
            "<p>Real-time network diagnostic tool.<br>"
            "Ping monitoring, traceroute, DNS/GeoIP/WHOIS dossier, and configurable alerts.</p>"
            "<p style='color:#8b949e; font-size:9pt;'>"
            "(c) 2025 Guy Schamp (kilrkrow)<br>"
            "Released under the MIT License."
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
