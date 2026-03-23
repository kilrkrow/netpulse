"""Monitor tab: multi-session ping with live table and overlay-graph views."""

import itertools
import time
from collections import deque
from typing import List, Optional

import pyqtgraph as pg

from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.alerts import AlertManager
from core.ping_engine import PingEngine, PingResult, PingStats
from core.process_monitor import ProcessWatcher, get_running_processes

pg.setConfigOptions(antialias=True)

# Colour palette for dark theme — cycles as more sessions are added
SESSION_COLORS = [
    "#58a6ff",  # blue
    "#3fb950",  # green
    "#d29922",  # amber
    "#d2a8ff",  # purple
    "#ff7b72",  # salmon
    "#ffa657",  # orange
    "#79c0ff",  # sky
    "#56d364",  # lime
]

_id_gen = itertools.count(1)


class _PingSession:
    def __init__(self, host: str, label: str, color: str,
                 interval_ms: int, timeout_ms: int, window: int):
        self.id = next(_id_gen)
        self.host = host
        self.label = label
        self.color = color
        self.engine = PingEngine(host, interval_ms, timeout_ms, window)
        self.window = window
        self.results: deque = deque(maxlen=window)
        self.stats: Optional[PingStats] = None
        self.plot_curve: Optional[pg.PlotDataItem] = None
        self.running: bool = True   # False once stopped (data preserved)


class MonitorTab(QWidget):
    """Multi-session ping monitor with toggleable table and overlay-graph views."""

    # For MainWindow: tray icon / alert manager
    worst_stats_updated = Signal(object)   # PingStats — worst across all active sessions
    # For MainWindow: push host into tracert/dossier history
    session_started = Signal(str)
    # For MainWindow: enable/disable export button etc.
    any_running_changed = Signal(bool)

    VIEW_TABLE = 0
    VIEW_GRAPH = 1

    def __init__(self, alert_mgr: AlertManager, parent=None):
        super().__init__(parent)
        self._alert_mgr = alert_mgr
        self._sessions: List[_PingSession] = []
        self._archived_sessions: list = []   # [(label, [PingResult, ...])] for closed sessions
        self._color_idx = 0
        self._view_mode = self.VIEW_TABLE
        self._user_zoomed = False
        self._t0: Optional[float] = None   # Unix epoch of first session; graph x origin

        # Defaults — kept in sync with MainWindow toolbar spins
        self._interval_ms = 1000
        self._timeout_ms = 2000
        self._window = 300

        self._build_ui()
        self._connect_watcher()

        # Refresh table cells at 2 Hz
        self._table_timer = QTimer(self)
        self._table_timer.timeout.connect(self._refresh_table)
        self._table_timer.start(500)

    # ------------------------------------------------------------------
    # Settings setters — called by MainWindow when toolbar spins change
    # ------------------------------------------------------------------
    def set_interval(self, ms: int):
        self._interval_ms = ms

    def set_timeout(self, ms: int):
        self._timeout_ms = ms

    def set_window(self, pts: int):
        self._window = pts

    # ------------------------------------------------------------------
    # Build UI
    # ------------------------------------------------------------------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 4)
        root.setSpacing(6)

        root.addLayout(self._build_controls())

        self._status_lbl = QLabel("Add a target above to start monitoring.")
        self._status_lbl.setStyleSheet("color: #8b949e; font-size: 9pt;")
        root.addWidget(self._status_lbl)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_table_view())
        self._stack.addWidget(self._build_graph_view())
        root.addWidget(self._stack)

    def _build_controls(self) -> QHBoxLayout:
        ctrl = QHBoxLayout()
        ctrl.setSpacing(6)

        # ── Manual target ──────────────────────────────────────────────
        ctrl.addWidget(QLabel("Target:"))
        self._host_combo = QComboBox()
        self._host_combo.setEditable(True)
        self._host_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._host_combo.lineEdit().setPlaceholderText("hostname or IP")
        self._host_combo.setMinimumWidth(180)
        self._host_combo.lineEdit().returnPressed.connect(self._on_start_clicked)
        ctrl.addWidget(self._host_combo)

        self._start_btn = QPushButton("▶ Start")
        self._start_btn.setObjectName("startBtn")
        self._start_btn.setFixedWidth(80)
        self._start_btn.clicked.connect(self._on_start_clicked)
        ctrl.addWidget(self._start_btn)

        self._stop_all_btn = QPushButton("■ Stop All")
        self._stop_all_btn.setObjectName("stopBtn")
        self._stop_all_btn.setFixedWidth(90)
        self._stop_all_btn.setEnabled(False)
        self._stop_all_btn.clicked.connect(self.stop_all)
        ctrl.addWidget(self._stop_all_btn)

        # ── Separator ──────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color: #30363d;")
        ctrl.addWidget(sep)

        # ── Process picker ─────────────────────────────────────────────
        ctrl.addWidget(QLabel("Process:"))
        self._proc_combo = QComboBox()
        self._proc_combo.setEditable(True)
        self._proc_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._proc_combo.lineEdit().setPlaceholderText("search running processes…")
        self._proc_combo.setMinimumWidth(180)
        ctrl.addWidget(self._proc_combo)

        self._proc_refresh_btn = QPushButton("↻")
        self._proc_refresh_btn.setFixedWidth(26)
        self._proc_refresh_btn.setToolTip("Refresh process list")
        self._proc_refresh_btn.clicked.connect(self._refresh_processes)
        ctrl.addWidget(self._proc_refresh_btn)

        self._watch_btn = QPushButton("Watch")
        self._watch_btn.setObjectName("startBtn")
        self._watch_btn.setFixedWidth(65)
        self._watch_btn.setCheckable(True)
        self._watch_btn.setToolTip(
            "Monitor this process for TCP connections.\n"
            "Works even before the process has launched."
        )
        self._watch_btn.clicked.connect(self._toggle_watch)
        ctrl.addWidget(self._watch_btn)

        ctrl.addStretch()

        # ── View toggle ────────────────────────────────────────────────
        self._table_btn = QPushButton("⊞")
        self._table_btn.setToolTip("Table view")
        self._table_btn.setCheckable(True)
        self._table_btn.setChecked(True)
        self._table_btn.setFixedWidth(32)
        self._table_btn.clicked.connect(lambda: self._set_view(self.VIEW_TABLE))
        ctrl.addWidget(self._table_btn)

        self._graph_btn = QPushButton("〜")
        self._graph_btn.setToolTip("Overlay graph view")
        self._graph_btn.setCheckable(True)
        self._graph_btn.setFixedWidth(32)
        self._graph_btn.clicked.connect(lambda: self._set_view(self.VIEW_GRAPH))
        ctrl.addWidget(self._graph_btn)

        return ctrl

    def _build_table_view(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)

        cols = ["", "Host / Label", "RTT", "Loss %", "Min", "Max", "Avg", "Samples", ""]
        self._table = QTableWidget(0, len(cols))
        self._table.setHorizontalHeaderLabels(cols)
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        fixed_widths = {0: 18, 2: 72, 3: 60, 4: 55, 5: 55, 6: 55, 7: 72, 8: 28}
        for col, width in fixed_widths.items():
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            self._table.setColumnWidth(col, width)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(False)
        self._table.setStyleSheet("QTableWidget { gridline-color: #21262d; }")
        layout.addWidget(self._table)
        return w

    def _build_graph_view(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._plot = pg.PlotWidget(
            background="#0d1117",
            axisItems={'bottom': pg.DateAxisItem(orientation='bottom')},
        )
        self._plot.showGrid(x=True, y=True, alpha=0.15)
        self._plot.setLabel("left", "RTT (ms)")
        self._plot.setLabel("bottom", "")
        self._plot.setMouseEnabled(x=True, y=True)
        for axis in ('left', 'bottom'):
            self._plot.getAxis(axis).setPen(pg.mkPen("#8b949e"))
            self._plot.getAxis(axis).setTextPen(pg.mkPen("#8b949e"))
        self._plot.getViewBox().sigRangeChangedManually.connect(self._on_user_zoom)
        self._legend = self._plot.addLegend(
            offset=(10, 10),
            labelTextColor="#c9d1d9",
            brush=pg.mkBrush(color=(22, 27, 34, 210)),
            pen=pg.mkPen(color="#30363d"),
        )
        layout.addWidget(self._plot)

        zoom_row = QHBoxLayout()
        zoom_row.addStretch()
        self._zoom_btn = QPushButton("● Live")
        self._zoom_btn.setFixedWidth(110)
        self._zoom_btn.clicked.connect(self._reset_zoom)
        zoom_row.addWidget(self._zoom_btn)
        layout.addLayout(zoom_row)

        return w

    # ------------------------------------------------------------------
    # Process watcher
    # ------------------------------------------------------------------
    def _connect_watcher(self):
        self._watcher = ProcessWatcher(self)
        self._watcher.process_found.connect(self._on_process_found)
        self._watcher.connections_found.connect(self._on_connections_found)
        self._refresh_processes()

    def _refresh_processes(self):
        procs = get_running_processes()
        current = self._proc_combo.currentText()
        self._proc_combo.clear()
        for p in procs:
            self._proc_combo.addItem(p.name)
        idx = self._proc_combo.findText(current)
        if idx >= 0:
            self._proc_combo.setCurrentIndex(idx)
        elif current:
            self._proc_combo.lineEdit().setText(current)

    def _toggle_watch(self, checked: bool):
        if checked:
            name = self._proc_combo.currentText().strip()
            if not name:
                self._watch_btn.setChecked(False)
                return
            self._watcher.watch(name)
            self._status_lbl.setText(
                f"Watching for '{name}'…  (will auto-add connections when found)"
            )
            self._watch_btn.setText("Stop")
            self._watch_btn.setObjectName("stopBtn")
            self._watch_btn.setStyle(self._watch_btn.style())
        else:
            self._watcher.stop()
            self._watch_btn.setText("Watch")
            self._watch_btn.setObjectName("startBtn")
            self._watch_btn.setStyle(self._watch_btn.style())
            self._status_lbl.setText("Watch stopped.")

    @Slot(str, int)
    def _on_process_found(self, name: str, pid: int):
        self._status_lbl.setText(f"Found '{name}' (PID {pid}) — scanning connections…")

    @Slot(list)
    def _on_connections_found(self, ips: list):
        added = 0
        for ip in ips:
            if self.add_session(ip):
                added += 1
        if added:
            self._status_lbl.setText(
                f"Auto-added {added} connection{'s' if added != 1 else ''} from process."
            )

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------
    def _next_color(self) -> str:
        color = SESSION_COLORS[self._color_idx % len(SESSION_COLORS)]
        self._color_idx += 1
        return color

    def add_session(self, host: str, label: Optional[str] = None) -> Optional[_PingSession]:
        """Start monitoring host.  Returns the session, or None if already monitored."""
        host = host.strip()
        if not host:
            return None
        for s in self._sessions:
            if s.host == host:
                self._status_lbl.setText(f"Already monitoring {host}.")
                return None

        label = label or host
        color = self._next_color()
        session = _PingSession(
            host=host, label=label, color=color,
            interval_ms=self._interval_ms,
            timeout_ms=self._timeout_ms,
            window=self._window,
        )

        sid = session.id
        session.engine.result_ready.connect(lambda r, _sid=sid: self._on_result(_sid, r))
        session.engine.stats_updated.connect(lambda st, _sid=sid: self._on_stats(_sid, st))
        session.engine.start()

        if self._t0 is None:
            self._t0 = time.time()

        self._sessions.append(session)
        self._add_table_row(session)
        self._add_graph_curve(session)
        self._add_to_history(host)

        self.session_started.emit(host)
        self._stop_all_btn.setText("■ Stop All")
        self._stop_all_btn.setEnabled(True)
        self.any_running_changed.emit(True)
        self._status_lbl.setText(f"Monitoring {len(self._sessions)} session(s).")
        return session

    def stop_session(self, session_id: int):
        idx = next((i for i, s in enumerate(self._sessions) if s.id == session_id), None)
        if idx is None:
            return
        session = self._sessions[idx]
        session.engine.stop()
        self._archive_session(session)

        if session.plot_curve is not None:
            try:
                self._legend.removeItem(session.plot_curve)
            except Exception:
                pass
            self._plot.removeItem(session.plot_curve)

        for row in range(self._table.rowCount()):
            btn = self._table.cellWidget(row, 8)
            if btn and getattr(btn, '_session_id', None) == session_id:
                self._table.removeRow(row)
                break

        self._sessions.pop(idx)
        self._stop_all_btn.setEnabled(bool(self._sessions))
        if not self._sessions:
            self.any_running_changed.emit(False)
            self._status_lbl.setText("All sessions stopped.")
        else:
            self._status_lbl.setText(f"Monitoring {len(self._sessions)} session(s).")

    def stop_all(self):
        """First click: stop engines, preserve data in table/graph.
           Second click (when already all stopped): clear everything."""
        any_running = any(s.running for s in self._sessions)
        if any_running:
            for s in self._sessions:
                if s.running:
                    s.engine.stop()
                    s.running = False
            self._stop_all_btn.setText("✕ Clear All")
            self.any_running_changed.emit(False)
            n = len(self._sessions)
            self._status_lbl.setText(
                f"{n} session{'s' if n != 1 else ''} stopped — data preserved.  "
                f"Click 'Clear All' to remove."
            )
        else:
            self._clear_all()

    def _clear_all(self):
        """Remove all sessions, rows, and graph curves completely."""
        for s in self._sessions:
            if s.plot_curve is not None:
                try:
                    self._legend.removeItem(s.plot_curve)
                except Exception:
                    pass
                self._plot.removeItem(s.plot_curve)
        self._sessions.clear()
        self._table.setRowCount(0)
        try:
            self._legend.clear()
        except Exception:
            pass
        self._t0 = None
        self._stop_all_btn.setText("■ Stop All")
        self._stop_all_btn.setEnabled(False)
        self.any_running_changed.emit(False)
        self._status_lbl.setText("All sessions cleared.")

    def pause_all(self):
        for s in self._sessions:
            s.engine.pause()

    def resume_all(self):
        for s in self._sessions:
            s.engine.resume()

    @property
    def any_paused(self) -> bool:
        return any(s.engine.is_paused for s in self._sessions)

    # ------------------------------------------------------------------
    # Table
    # ------------------------------------------------------------------
    def _add_table_row(self, session: _PingSession):
        row = self._table.rowCount()
        self._table.insertRow(row)

        dot = QLabel("●")
        dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dot.setStyleSheet(f"color: {session.color}; font-size: 12pt;")
        self._table.setCellWidget(row, 0, dot)

        self._table.setItem(
            row, 1,
            self._mk_cell(session.label,
                          Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        )
        for col in range(2, 8):
            self._table.setItem(row, col, self._mk_cell("…"))

        btn = QPushButton("×")
        btn.setFixedSize(22, 22)
        btn.setStyleSheet(
            "QPushButton { color: #f85149; background: transparent; border: none; "
            "font-size: 14pt; font-weight: bold; }"
            "QPushButton:hover { color: #ff7b72; }"
        )
        btn._session_id = session.id
        btn.clicked.connect(lambda _checked, sid=session.id: self.stop_session(sid))
        self._table.setCellWidget(row, 8, btn)

    def _mk_cell(self, text: str,
                 align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignCenter) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setTextAlignment(align)
        return item

    def _refresh_table(self):
        for row in range(self._table.rowCount()):
            btn = self._table.cellWidget(row, 8)
            if not btn:
                continue
            sid = getattr(btn, '_session_id', None)
            if sid is None:
                continue
            session = next((s for s in self._sessions if s.id == sid), None)
            if not session or not session.stats:
                continue

            # Stopped session — dim dot, freeze stats cells, skip live update
            if not session.running:
                dot = self._table.cellWidget(row, 0)
                if dot:
                    dot.setStyleSheet("color: #484f58; font-size: 12pt;")
                continue

            stats = session.stats
            rtt = stats.last_rtt

            dot = self._table.cellWidget(row, 0)
            if dot:
                if rtt is None or stats.loss_pct > 10:
                    health = "#f85149"
                elif stats.loss_pct > 2 or (rtt is not None and rtt > 150):
                    health = "#d29922"
                else:
                    health = "#3fb950"
                dot.setStyleSheet(f"color: {health}; font-size: 12pt;")

            rtt_str  = f"{rtt:.0f} ms" if rtt is not None else "Timeout"
            loss_str = f"{stats.loss_pct:.1f}%"
            min_str  = f"{stats.rtt_min:.0f}" if stats.rtt_min is not None else "-"
            max_str  = f"{stats.rtt_max:.0f}" if stats.rtt_max is not None else "-"
            avg_str  = f"{stats.rtt_avg:.0f}" if stats.rtt_avg is not None else "-"

            for col, text in enumerate(
                [rtt_str, loss_str, min_str, max_str, avg_str, str(stats.samples)], start=2
            ):
                item = self._table.item(row, col)
                if item:
                    item.setText(text)
                    if col == 2:
                        if rtt is None:
                            item.setForeground(QColor("#f85149"))
                        elif rtt > 150:
                            item.setForeground(QColor("#d29922"))
                        else:
                            item.setForeground(QColor("#c9d1d9"))

    # ------------------------------------------------------------------
    # Graph
    # ------------------------------------------------------------------
    def _add_graph_curve(self, session: _PingSession):
        curve = pg.PlotDataItem(
            pen=pg.mkPen(color=session.color, width=2),
            name=session.label,
            connect='finite',
        )
        self._plot.addItem(curve)
        session.plot_curve = curve

    def _update_graph_curve(self, session: _PingSession):
        if session.plot_curve is None:
            return
        results = list(session.results)
        if not results:
            return
        y = [r.rtt_ms if r.rtt_ms is not None else float('nan') for r in results]
        x = [r.timestamp.timestamp() for r in results]
        session.plot_curve.setData(x=x, y=y)
        if not self._user_zoomed:
            now = time.time()
            window_secs = self._window * (self._interval_ms / 1000.0)
            self._plot.setXRange(now - window_secs, now, padding=0.02)

    def _on_user_zoom(self):
        self._user_zoomed = True
        self._zoom_btn.setText("↺ Live View")
        self._zoom_btn.setStyleSheet("QPushButton { color: #3fb950; font-weight: bold; }")

    def _reset_zoom(self):
        self._user_zoomed = False
        now = time.time()
        window_secs = self._window * (self._interval_ms / 1000.0)
        self._plot.setXRange(now - window_secs, now, padding=0.02)
        self._zoom_btn.setText("● Live")
        self._zoom_btn.setStyleSheet("")

    # ------------------------------------------------------------------
    # View toggle
    # ------------------------------------------------------------------
    def _set_view(self, mode: int):
        self._view_mode = mode
        self._stack.setCurrentIndex(mode)
        self._table_btn.setChecked(mode == self.VIEW_TABLE)
        self._graph_btn.setChecked(mode == self.VIEW_GRAPH)
        if mode == self.VIEW_GRAPH:
            for s in self._sessions:
                self._update_graph_curve(s)

    # ------------------------------------------------------------------
    # Engine signal handlers
    # ------------------------------------------------------------------
    def _on_result(self, session_id: int, result: PingResult):
        session = next((s for s in self._sessions if s.id == session_id), None)
        if not session or not session.running:
            return
        session.results.append(result)
        if self._view_mode == self.VIEW_GRAPH:
            self._update_graph_curve(session)

    def _on_stats(self, session_id: int, stats: PingStats):
        session = next((s for s in self._sessions if s.id == session_id), None)
        if not session:
            return
        session.stats = stats
        self._emit_worst_stats()

    def _emit_worst_stats(self):
        active = [s for s in self._sessions if s.stats is not None and s.running]
        if not active:
            return
        worst = max(active, key=lambda s: (s.stats.loss_pct, s.stats.last_rtt or 0))
        self.worst_stats_updated.emit(worst.stats)
        self._alert_mgr.check(worst.stats, host=worst.host)

    # ------------------------------------------------------------------
    # Manual start
    # ------------------------------------------------------------------
    def _on_start_clicked(self):
        host = self._host_combo.currentText().strip()
        if host:
            self.add_session(host)

    def _archive_session(self, session: _PingSession):
        """Save a closing session's results so they survive in the export."""
        if session.results:
            self._archived_sessions.append((session.label, list(session.results)))

    # ------------------------------------------------------------------
    # History combo (persisted by MainWindow via get_history/load_history)
    # ------------------------------------------------------------------
    def _add_to_history(self, host: str):
        idx = self._host_combo.findText(host)
        if idx >= 0:
            self._host_combo.removeItem(idx)
        self._host_combo.insertItem(0, host)
        self._host_combo.setCurrentIndex(0)
        while self._host_combo.count() > 15:
            self._host_combo.removeItem(self._host_combo.count() - 1)

    def get_history(self) -> list:
        return [self._host_combo.itemText(i) for i in range(self._host_combo.count())]

    def load_history(self, items: list):
        self._host_combo.clear()
        for host in items:
            self._host_combo.addItem(host)
        if not self._host_combo.count():
            self._host_combo.addItem("google.com")

    # ------------------------------------------------------------------
    # Export support
    # ------------------------------------------------------------------
    def get_all_results(self) -> list:
        """Return list of (session_label, PingResult) tuples for CSV export.
        Includes results from sessions that have already been closed."""
        rows = []
        for label, results in self._archived_sessions:
            for r in results:
                rows.append((label, r))
        for s in self._sessions:
            for r in s.results:
                rows.append((s.label, r))
        return rows
