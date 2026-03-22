"""Main window with toolbar, tabs, and system tray integration."""

import csv
import datetime
from collections import deque

from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
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
from core.ping_engine import PingEngine, PingResult, PingStats
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

        self._engine: PingEngine | None = None
        self._current_stats: PingStats | None = None
        self._session_start: datetime.datetime | None = None
        self._history: deque[PingResult] = deque(maxlen=20000)

        self._alert_mgr = AlertManager()
        self._tracer = TracerouteEngine()
        self._dossier = DossierEngine()

        self._build_ui()
        self._build_tray()
        self._connect_signals()

        self._sb_timer = QTimer()
        self._sb_timer.timeout.connect(self._update_status_bar)
        self._sb_timer.start(1000)

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

        self._sb_label = QLabel("Ready - enter a host and press Start")
        self._sb_label.setStyleSheet("color: #8b949e; padding: 2px 6px;")
        self._status_bar.addWidget(self._sb_label)

        self._sb_right = QLabel("")
        self._sb_right.setStyleSheet("color: #8b949e; padding: 2px 6px;")
        self._status_bar.addPermanentWidget(self._sb_right)

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

        layout.addWidget(QLabel("Target:"))
        self._host_combo = QComboBox()
        self._host_combo.setEditable(True)
        self._host_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._host_combo.lineEdit().setPlaceholderText("hostname or IP (e.g. google.com)")
        self._host_combo.addItem("google.com")
        self._host_combo.setMinimumWidth(220)
        self._host_combo.lineEdit().returnPressed.connect(self._start)
        layout.addWidget(self._host_combo)

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

        self._start_btn = QPushButton("Start")
        self._start_btn.setObjectName("startBtn")
        self._start_btn.setFixedWidth(90)
        self._start_btn.clicked.connect(self._start)
        layout.addWidget(self._start_btn)

        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setObjectName("stopBtn")
        self._stop_btn.setFixedWidth(90)
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._stop)
        layout.addWidget(self._stop_btn)

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
        quit_action = menu.addAction("Exit NetPulse")
        quit_action.triggered.connect(QApplication.quit)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._tray_activated)
        self._tray.show()

    def _connect_signals(self):
        self._alert_mgr.alert_triggered.connect(self._on_alert)

    def _add_host_to_history(self, host: str):
        """Add host to ping combo history and push to tracert tab (non-destructively)."""
        combo = self._host_combo
        idx = combo.findText(host)
        if idx >= 0:
            combo.removeItem(idx)
        combo.insertItem(0, host)
        combo.setCurrentIndex(0)
        while combo.count() > 15:
            combo.removeItem(combo.count() - 1)
        self._tracer_tab.add_to_history(host)

    def _start(self):
        host = self._host_combo.currentText().strip()
        if not host:
            return

        if self._engine and self._engine.is_running:
            self._stop()

        self._start_btn.setText("Live")
        self._start_btn.setEnabled(False)
        self._stop_btn.setText("Stop")
        self._stop_btn.setEnabled(False)
        self._host_combo.setEnabled(False)
        self._add_host_to_history(host)
        self._sb_label.setText(f"  Starting {host}...")
        QApplication.processEvents()

        self._history.clear()
        self._session_start = datetime.datetime.now()

        self._engine = PingEngine(
            host=host,
            interval_ms=self._interval_spin.value(),
            timeout_ms=self._timeout_spin.value(),
            window=3600,
        )
        self._engine.result_ready.connect(self._on_result)
        self._engine.stats_updated.connect(self._on_stats)

        self._monitor_tab.set_engine(self._engine, self._window_spin.value())
        self._tracer_tab.notify_host(host)
        self._dossier_tab.notify_host(host)
        self._engine.start()

        self._stop_btn.setEnabled(True)
        self._tray.setIcon(_make_tray_icon("#3fb950"))
        self._tray.setToolTip(f"NetPulse - {host}")
        self._tray_status_action.setText(f"Monitoring: {host}")

    def _stop(self):
        self._stop_btn.setText("Stopping...")
        self._stop_btn.setEnabled(False)
        self._start_btn.setEnabled(False)
        QApplication.processEvents()

        if self._engine:
            self._engine.stop()
            self._engine = None

        self._start_btn.setText("Start")
        self._start_btn.setEnabled(True)
        self._stop_btn.setText("Stop")
        self._stop_btn.setEnabled(False)
        self._host_combo.setEnabled(True)
        self._tray.setIcon(_make_tray_icon("#8b949e"))
        self._tray.setToolTip("NetPulse - Stopped")
        self._tray_status_action.setText("Stopped")
        self._sb_label.setText("  Stopped - enter a host and press Start")

    @Slot(object)
    def _on_result(self, result: PingResult):
        self._history.append(result)

    @Slot(object)
    def _on_stats(self, stats: PingStats):
        self._current_stats = stats
        self._alert_mgr.check(stats)
        self._update_tray_icon(stats)

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

    @Slot(object)
    def _on_alert(self, event):
        self._tray.showMessage(
            "NetPulse Alert",
            event.message,
            QSystemTrayIcon.MessageIcon.Warning,
            5000,
        )

    def _update_status_bar(self):
        if not self._current_stats:
            return
        stats = self._current_stats
        rtt_str = f"{stats.last_rtt:.0f} ms" if stats.last_rtt is not None else "Timeout"
        self._sb_label.setText(
            f"  Host: {stats.host}    RTT: {rtt_str}    "
            f"Loss: {stats.loss_pct:.1f}%    Samples: {stats.samples}"
        )
        if self._session_start:
            elapsed = datetime.datetime.now() - self._session_start
            hours, remainder = divmod(int(elapsed.total_seconds()), 3600)
            minutes, seconds = divmod(remainder, 60)
            self._sb_right.setText(f"Session: {hours:02d}:{minutes:02d}:{seconds:02d}")

    def _export_csv(self):
        if not self._history:
            QMessageBox.information(self, "Export", "No data to export yet.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Ping History",
            "netpulse_export.csv",
            "CSV Files (*.csv)",
        )
        if not path:
            return

        with open(path, "w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["Timestamp", "Host", "Seq", "RTT_ms", "TTL", "IP", "Error"])
            for result in self._history:
                writer.writerow(
                    [
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

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self._tray.showMessage(
            "NetPulse",
            "Still running in background. Right-click the tray icon to exit.",
            QSystemTrayIcon.MessageIcon.Information,
            2500,
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
