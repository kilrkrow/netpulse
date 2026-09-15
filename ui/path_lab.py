"""Thin Path lab hop table for NetPulse Pro."""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.traceroute import TracerouteHop
from ui.context_verbs import VerbCallbacks, build_hop_menu, build_hop_power_menu


class PathLabView(QWidget):
    """Simple hop table with context-menu parity to cards."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hops: List[TracerouteHop] = []
        self._cb: Optional[VerbCallbacks] = None
        self._filtered: set = set()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        head = QHBoxLayout()
        title = QLabel("Path lab")
        title.setStyleSheet("font-size: 14pt; font-weight: 600;")
        head.addWidget(title)
        head.addStretch()
        self._hint = QLabel("Right-click a row for verbs. Shift+right-click for CLI.")
        self._hint.setObjectName("HopMeta")
        head.addWidget(self._hint)
        lay.addLayout(head)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["Hop", "Hostname", "Address", "Avg ms", "Status"])
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_ctx)
        self._table.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(self._table)

    def set_callbacks(self, cb: VerbCallbacks):
        self._cb = cb

    def set_hops(self, hops: List[TracerouteHop]):
        self._hops = list(hops)
        self._table.setRowCount(0)
        for hop in hops:
            row = self._table.rowCount()
            self._table.insertRow(row)
            vals = [
                str(hop.hop_num),
                hop.hostname or "",
                hop.ip or "",
                f"{hop.avg_rtt:.0f}" if hop.avg_rtt is not None else "",
                "timeout" if hop.timed_out else ("filtered" if hop.hop_num in self._filtered else "ok"),
            ]
            for col, v in enumerate(vals):
                self._table.setItem(row, col, QTableWidgetItem(v))

    def mark_filtered(self, hop: TracerouteHop):
        self._filtered.add(hop.hop_num)
        self.set_hops(self._hops)

    def _hop_at_row(self, row: int) -> Optional[TracerouteHop]:
        if 0 <= row < len(self._hops):
            return self._hops[row]
        return None

    def _on_ctx(self, pos):
        if not self._cb:
            return
        from PySide6.QtWidgets import QApplication
        idx = self._table.indexAt(pos)
        if not idx.isValid():
            return
        hop = self._hop_at_row(idx.row())
        if not hop:
            return
        global_pos = self._table.viewport().mapToGlobal(pos)
        mods = QApplication.keyboardModifiers()
        if mods & Qt.KeyboardModifier.ShiftModifier:
            menu = build_hop_power_menu(self, hop, self._cb)
        else:
            menu = build_hop_menu(self, hop, self._cb, table=True)
        menu.exec(global_pos)
