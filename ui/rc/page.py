"""The Path page (verdict, path, detail + IP research) and the Outages page."""

from __future__ import annotations

import time
from typing import Optional

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QMenu, QMessageBox, QPushButton,
                               QSizePolicy, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from core.rc.ipclass import classify_ip
from core.rc.model import (SEG_DISH, SEG_GATEWAY, SEG_INTERNET, SEG_PC, SEGMENT_NAMES, SEGMENTS, PathSnapshot, Verdict,
                           compute_stats)
from core.rc.outages import fmt_duration, fmt_time, segment_label
from ui.dock import add_slot
from ui.rc import theme
from ui.rc.ip_panel import IpResearchPanel
from ui.rc.path_view import PathView
from ui.rc.verdict_panel import VerdictPanel
from ui.rc.widgets import PhosphorGraph, ReadoutCell


class DetailPanel(QWidget):
    """Opens from the path: readouts and a five minute phosphor graph for the selected hop."""

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(6)
        self.title = QLabel("SELECT A HOP")
        self.title.setFont(theme.mono(9, True))
        self.title.setStyleSheet(f"color: {theme.CYAN};")
        root.addWidget(self.title)
        row = QHBoxLayout()
        row.setSpacing(6)
        self.cells = {}
        for k in ("LAST", "AVERAGE", "BEST", "WORST", "JITTER", "LOSS"):
            c = ReadoutCell(k)
            self.cells[k] = c
            row.addWidget(c)
        root.addLayout(row)
        self.graph = PhosphorGraph(window_s=300.0)
        root.addWidget(self.graph, 1)
        self.note = QLabel("")
        self.note.setWordWrap(True)
        self.note.setStyleSheet(f"color: {theme.DIM}; font-size: 8.5pt;")
        root.addWidget(self.note)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(theme.PANEL))
        p.setPen(QPen(QColor(theme.BORDER), 1))
        p.drawRect(0, 0, self.width() - 1, self.height() - 1)

    def show_hop(self, snap: PathSnapshot, ttl: Optional[int], interval_s: float = 1.0) -> None:
        hop = snap.hop_by_ttl(ttl) if ttl is not None else None
        if hop is None or hop.ttl == 0:
            self.title.setText("THIS PC" if hop else "SELECT A HOP")
            for c in self.cells.values():
                c.set_value("--", theme.DIMMER)
            self.graph.set_series([], snap.ts, interval_s=interval_s)
            self.note.setText("Click a hop in the path to see its history.")
            return
        recent = [s for s in hop.samples if s.ts >= snap.ts - 300]
        st = compute_stats(recent)
        seg = SEGMENT_NAMES.get(hop.segment, hop.segment)
        self.title.setText(f"HOP {hop.ttl}   {hop.ip or 'NO ADDRESS'}   {seg}   LAST 5 MIN")
        col = theme.SEG_COLORS.get(hop.segment, theme.OK)

        def ms(v):
            return "--" if v is None else (f"{v:.0f} ms" if v >= 10 else f"{v:.1f} ms")

        if st.consec_fail >= 2:
            self.cells["LAST"].set_value("NO REPLY", theme.FAIL)
        else:
            self.cells["LAST"].set_value(ms(st.last_rtt), col)
        self.cells["AVERAGE"].set_value(ms(st.avg_rtt), theme.TEXT)
        self.cells["BEST"].set_value(ms(st.min_rtt), theme.TEXT)
        self.cells["WORST"].set_value(ms(st.max_rtt), theme.TEXT)
        self.cells["JITTER"].set_value(ms(st.jitter), theme.TEXT)
        lc = theme.FAIL if st.loss_pct >= 50 else (theme.WARN if st.loss_pct >= 10 else theme.OK)
        self.cells["LOSS"].set_value(f"{st.loss_pct:.0f}%" if st.sent else "--", lc if st.sent else theme.DIMMER)
        series = []
        tgt = snap.hops[-1] if snap.hops else None
        if tgt is not None and tgt.ttl != hop.ttl and tgt.ttl >= 1:
            series.append((theme.SEG_COLORS[SEG_INTERNET], [(s.ts, s.rtt_ms if s.ok else None) for s in tgt.samples
                                                            if s.ts >= snap.ts - 300], True))
        series.append((col, [(s.ts, s.rtt_ms if s.ok else None) for s in recent], False))
        self.graph.set_series(series, snap.ts, interval_s=interval_s)
        notes = []
        if hop.hostname:
            notes.append(f"Reverse DNS: {hop.hostname}")
        if tgt is not None and tgt.ttl != hop.ttl and tgt.ttl >= 1:
            notes.append("The dimmer line is the final target, for comparison.")
        notes.append("Red ticks along the bottom edge are lost probes.")
        self.note.setText("  ".join(notes))


class PathPage(QWidget):
    copy_report = Signal()
    open_settings = Signal()

    def __init__(self, controller, settings_store, parent=None):
        super().__init__(parent)
        self.ctl = controller
        self.settings = settings_store
        self._snap: Optional[PathSnapshot] = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)
        self.verdict = VerdictPanel()
        self.path = PathView()
        self.detail = DetailPanel()
        self.ip = IpResearchPanel(controller, settings_store)
        root.addWidget(self.verdict)
        root.addWidget(self.path)
        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        bottom.addWidget(self.detail, 3)
        bottom.addWidget(self.ip, 2)
        root.addLayout(bottom, 1)

        self.verdict.copy_report.connect(self.copy_report)
        self.verdict.open_settings.connect(self.open_settings)
        self.path.hop_selected.connect(self._on_hop_selected)
        self.path.hop_context.connect(self._hop_menu)

    def update_data(self, snap: PathSnapshot, verdict: Verdict) -> None:
        self._snap = snap
        interval = self.ctl.engine.cfg.interval_s
        self.verdict.show_verdict(verdict, snap.ts)
        self.path.update_data(snap, verdict, interval)
        self.detail.show_hop(snap, self.path.selected_ttl(), interval)

    def redraw(self) -> None:
        """Paint the last snapshot again. Used when the probe interval changes, so the traces join at the new spacing without waiting for the next probe."""
        if self._snap is not None and self.ctl.verdict is not None:
            self.update_data(self._snap, self.ctl.verdict)

    def _on_hop_selected(self, ttl: int) -> None:
        if self._snap is not None:
            self.detail.show_hop(self._snap, ttl)
            hop = self._snap.hop_by_ttl(ttl)
            if hop is not None and hop.ip:
                self.ip.lookup(hop.ip)

    def _hop_menu(self, ttl: int, pos) -> None:
        if self._snap is None:
            return
        hop = self._snap.hop_by_ttl(ttl)
        if hop is None:
            return
        m = QMenu(self)
        if hop.ip:
            a = m.addAction(f"Research {hop.ip}")
            a.triggered.connect(lambda: self.ip.lookup(hop.ip))
            c = m.addAction("Copy address")
            c.triggered.connect(lambda: QGuiApplication.clipboard().setText(hop.ip))
            m.addSeparator()
        if hop.ttl >= 1:
            sub = m.addMenu("Label this hop as")
            for seg in (SEG_GATEWAY, SEG_DISH, SEG_INTERNET):
                act = sub.addAction(SEGMENT_NAMES[seg].title())
                act.setCheckable(True)
                act.setChecked(hop.segment == seg)
                act.triggered.connect(lambda _=False, s=seg: self._set_label(hop, s))
            if hop.label_source == "override":
                m.addAction("Clear my label").triggered.connect(lambda: self._set_label(hop, None))
        m.exec(pos)

    def _set_label(self, hop, seg) -> None:
        key = f"ip:{hop.ip}" if hop.ip else f"ttl:{hop.ttl}"
        self.settings.set_override(key, seg or "")


class OutagePanel(QWidget):
    copy_report = Signal()

    COLS = ["START", "DURATION", "FAILING SEGMENT", "WHAT HAPPENED", "STATE"]

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.ctl = controller
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)          # the same 8 px as the Monitor / Traceroute / Dossier / Alerts pages
        root.setSpacing(8)
        head = QHBoxLayout()
        t = QLabel("DISCONNECT LOG")
        t.setFont(theme.mono(10, True))
        t.setStyleSheet(f"color: {theme.CYAN};")
        head.addWidget(t)
        self.count = QLabel("")
        self.count.setStyleSheet(f"color: {theme.DIM};")
        head.addWidget(self.count)
        head.addStretch()
        self.copy_btn = QPushButton("Copy report")
        self.copy_btn.setObjectName("primary")
        self.copy_btn.clicked.connect(self.copy_report)
        self.clear_btn = QPushButton("Clear log")
        self.clear_btn.clicked.connect(self._clear)
        head.addWidget(self.copy_btn)
        head.addWidget(self.clear_btn)
        add_slot(head)
        root.addLayout(head)
        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        self.table.setShowGrid(False)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hh.setStretchLastSection(True)
        self.table.setColumnWidth(0, 170)
        self.table.setColumnWidth(1, 120)
        self.table.setColumnWidth(2, 160)
        self.table.setColumnWidth(3, 480)
        root.addWidget(self.table, 1)
        self.detail = QLabel("")
        self.detail.setWordWrap(True)
        self.detail.setMinimumHeight(40)
        self.detail.setStyleSheet(f"color: {theme.TEXT}; background: {theme.PANEL}; border: 1px solid {theme.BORDER}; "
                                  "padding: 6px 8px;")
        self.table.itemSelectionChanged.connect(self._show_detail)
        root.addWidget(self.detail)
        self.empty = QLabel("No outages recorded yet. Outages appear here while NetPulse is running and survive restarts.")
        self.empty.setStyleSheet(f"color: {theme.DIM};")
        root.addWidget(self.empty)
        self._tick = QTimer(self)
        self._tick.timeout.connect(self._refresh_open)
        self._tick.start(1000)
        self.refresh()

    def _clear(self) -> None:
        r = QMessageBox.question(self, "Clear log", "Delete every recorded outage from this PC?",
                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                 QMessageBox.StandardButton.No)
        if r == QMessageBox.StandardButton.Yes:
            self.ctl.store.clear()
            self.refresh()

    def refresh(self) -> None:
        rows = self.ctl.store.list(200)
        now = self.ctl.clock()
        cur = self.table.currentRow()
        keep_id = self.table.item(cur, 0).data(Qt.ItemDataRole.UserRole) if cur >= 0 and self.table.item(cur, 0) else None
        self.table.blockSignals(True)
        self.table.setRowCount(len(rows))
        for i, o in enumerate(rows):
            seg_col = theme.SEG_COLORS.get(o.segment, theme.DIM)
            state = "ONGOING" if o.open else ("INTERRUPTED" if o.interrupted else "ENDED")
            vals = [fmt_time(o.start_ts), fmt_duration(o.duration(now)), segment_label(o.segment), o.headline, state]
            for j, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if j == 2:
                    it.setForeground(QColor(seg_col))
                if j == 4:
                    it.setForeground(QColor(theme.FAIL if o.open else theme.DIM))
                if j in (0, 1):
                    it.setFont(theme.mono(9.5))
                it.setToolTip(o.explanation)
                it.setData(Qt.ItemDataRole.UserRole, o.id)
                self.table.setItem(i, j, it)
        if keep_id is not None:
            for i, o in enumerate(rows):
                if o.id == keep_id:
                    self.table.setCurrentCell(i, 0)
        self.table.blockSignals(False)
        self._show_detail()
        self.count.setText(f"{len(rows)} recorded")
        self.empty.setVisible(not rows)

    def _show_detail(self) -> None:
        it = self.table.currentItem()
        self.detail.setText(it.toolTip() if it is not None else "Select an outage to see what NetPulse concluded.")

    def _refresh_open(self) -> None:
        if not self.isVisible():
            return
        now = self.ctl.clock()
        for i in range(self.table.rowCount()):
            it = self.table.item(i, 4)
            if it is not None and it.text() == "ONGOING":
                self.refresh()
                return
