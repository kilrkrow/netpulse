"""Traceroute tab: hop-by-hop table with RTT and hop data."""

from typing import List, Optional

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.traceroute import TracerouteEngine, TracerouteHop

C_GREEN = "#3fb950"
C_YELLOW = "#d29922"
C_RED = "#f85149"
C_MUTED = "#8b949e"


def _rtt_color(avg: Optional[float]) -> QColor:
    if avg is None:
        return QColor(C_MUTED)
    if avg < 50:
        return QColor(C_GREEN)
    if avg < 150:
        return QColor(C_YELLOW)
    return QColor(C_RED)


def _fmt_rtt(value: Optional[float]) -> str:
    if value is None:
        return "*"
    if value < 1:
        return "<1 ms"
    return f"{value:.0f} ms"


class TracerouteTab(QWidget):
    COLUMNS = ["Hop", "IP Address", "Hostname", "RTT 1", "RTT 2", "RTT 3", "Avg RTT", "Status"]

    def __init__(self, engine: TracerouteEngine, parent=None):
        super().__init__(parent)
        self._engine = engine
        self._hops: List[TracerouteHop] = []
        self._running = False
        self._build_ui()
        self._connect_signals()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Target:"))
        self._host_combo = QComboBox()
        self._host_combo.setEditable(True)
        self._host_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._host_combo.lineEdit().setPlaceholderText("hostname or IP")
        self._host_combo.setMinimumWidth(220)
        toolbar.addWidget(self._host_combo)
        toolbar.addStretch()

        self._run_btn = QPushButton("Run Traceroute")
        self._run_btn.setObjectName("startBtn")
        self._run_btn.setFixedWidth(150)
        self._run_btn.clicked.connect(self._run)
        toolbar.addWidget(self._run_btn)

        self._abort_btn = QPushButton("Abort")
        self._abort_btn.setObjectName("stopBtn")
        self._abort_btn.setFixedWidth(100)
        self._abort_btn.setEnabled(False)
        self._abort_btn.clicked.connect(self._abort)
        toolbar.addWidget(self._abort_btn)

        root.addLayout(toolbar)

        self._progress = QLabel('Click "Run Traceroute" to begin.')
        self._progress.setStyleSheet(f"color: {C_MUTED}; font-size: 9pt;")
        root.addWidget(self._progress)

        self._table = QTableWidget(0, len(self.COLUMNS))
        self._table.setHorizontalHeaderLabels(self.COLUMNS)
        # All columns fixed width except Hostname (col 2) which stretches
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.setColumnWidth(0, 45)   # Hop
        self._table.setColumnWidth(1, 120)  # IP Address
        # col 2 (Hostname) stretches to fill remaining space
        self._table.setColumnWidth(3, 68)   # RTT 1
        self._table.setColumnWidth(4, 68)   # RTT 2
        self._table.setColumnWidth(5, 68)   # RTT 3
        self._table.setColumnWidth(6, 78)   # Avg RTT
        self._table.setColumnWidth(7, 78)   # Status
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(False)
        root.addWidget(self._table)

        self._summary = QLabel("")
        self._summary.setStyleSheet(f"color: {C_MUTED}; font-size: 9pt;")
        root.addWidget(self._summary)

    def _connect_signals(self):
        self._engine.hop_found.connect(self._on_hop)
        self._engine.finished.connect(self._on_finished)
        self._engine.error_occurred.connect(self._on_error)
        self._engine.started.connect(self._on_started)

    def add_to_history(self, host: str):
        """Add host to the dropdown without changing the current selection."""
        idx = self._host_combo.findText(host)
        if idx >= 0:
            self._host_combo.removeItem(idx)
        self._host_combo.insertItem(0, host)
        while self._host_combo.count() > 15:
            self._host_combo.removeItem(self._host_combo.count() - 1)

    def set_target(self, host: str):
        self.add_to_history(host)

    def _run(self):
        target = self._host_combo.currentText().strip()
        if not target:
            self._progress.setText("Enter a hostname or IP above.")
            return
        self._target = target

        self._hops.clear()
        self._table.setRowCount(0)
        self._running = True
        self._run_btn.setEnabled(False)
        self._abort_btn.setEnabled(True)
        self._engine.run(target)

    def _abort(self):
        self._engine.abort()
        self._abort_btn.setEnabled(False)
        self._run_btn.setEnabled(True)
        self._progress.setText("Aborted.")

    @Slot()
    def _on_started(self):
        self._progress.setText("Tracing route...")

    @Slot(object)
    def _on_hop(self, hop: TracerouteHop):
        self._hops.append(hop)
        row = self._table.rowCount()
        self._table.insertRow(row)

        value_color = _rtt_color(hop.avg_rtt)
        status = "Timeout" if hop.timed_out else "OK"
        status_color = QColor(C_RED) if hop.timed_out else QColor(C_GREEN)

        def item(text: str, align=Qt.AlignmentFlag.AlignCenter) -> QTableWidgetItem:
            table_item = QTableWidgetItem(text)
            table_item.setTextAlignment(align)
            return table_item

        ip_item = item(hop.ip or "*", Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        ip_item.setToolTip(hop.ip or "")
        hostname_item = item(hop.hostname or "", Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        hostname_item.setToolTip(hop.hostname or "")
        columns = [
            item(str(hop.hop_num)),
            ip_item,
            hostname_item,
            item(_fmt_rtt(hop.rtt1)),
            item(_fmt_rtt(hop.rtt2)),
            item(_fmt_rtt(hop.rtt3)),
            item(_fmt_rtt(hop.avg_rtt)),
            item(status),
        ]
        for index, table_item in enumerate(columns):
            if index in (3, 4, 5, 6):
                table_item.setForeground(value_color)
            if index == 7:
                table_item.setForeground(status_color)
            self._table.setItem(row, index, table_item)

        self._progress.setText(
            f'Hop {hop.hop_num}: {hop.ip or "timeout"}'
            + (f" ({hop.avg_rtt:.0f} ms avg)" if hop.avg_rtt is not None else "")
        )

    @Slot(list)
    def _on_finished(self, hops):
        self._running = False
        self._run_btn.setEnabled(True)
        self._abort_btn.setEnabled(False)
        responding = [hop for hop in hops if not hop.timed_out]
        avg_total = (
            sum(hop.avg_rtt for hop in responding if hop.avg_rtt is not None) / len(responding)
            if responding
            else None
        )
        self._progress.setText(
            f"Complete - {len(hops)} hops, {len(responding)} responding"
            + (f", total avg {avg_total:.0f} ms" if avg_total is not None else "")
        )

    @Slot(str)
    def _on_error(self, message: str):
        self._progress.setText(f"Error: {message}")
        self._running = False
        self._run_btn.setEnabled(True)
        self._abort_btn.setEnabled(False)

    def notify_host(self, host: str):
        self.add_to_history(host)
