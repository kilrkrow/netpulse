"""Dense hop table filling Command Center / Path lab."""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from core.traceroute import TracerouteHop
from ui.theme import AMBER, CHARCOAL, CORAL, EMERALD, PANEL, TEXT


def worst_hop(hops: List[TracerouteHop]) -> Optional[TracerouteHop]:
    real = [h for h in hops if h.hop_num > 0 and h.state != "probing"]
    if not real:
        return hops[-1] if hops else None
    timeouts = [h for h in real if h.timed_out]
    if timeouts:
        return timeouts[0]
    with_rtt = [h for h in real if h.avg_rtt is not None]
    if with_rtt:
        return max(with_rtt, key=lambda h: h.avg_rtt or 0)
    return real[-1]



def _note(hop: TracerouteHop, is_dest: bool) -> str:
    if hop.state == "probing":
        return "probing..."
    if hop.timed_out:
        return "timeout - ICMP filtered or no reply"
    if hop.hop_num == 0:
        return "This PC"
    if hop.role == "gateway":
        return "Local gateway"
    if hop.role == "LAN":
        return "LAN"
    if hop.role == "CGNAT":
        return "CGNAT 100.64"
    if is_dest:
        return "destination"
    if hop.role == "public":
        return "public"
    return ""


class HopTable(QTableWidget):
    hop_selected = Signal(object)
    hop_context = Signal(object, object)
    hop_power_context = Signal(object, object)

    COLS = ["Hop", "Role", "Address", "Hostname", "RTT ms", "Status", "Notes"]

    def __init__(self, parent=None):
        super().__init__(0, len(self.COLS), parent)
        self._hops: List[TracerouteHop] = []
        self.setHorizontalHeaderLabels(self.COLS)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.setColumnWidth(0, 48)
        self.setColumnWidth(1, 80)
        self.setColumnWidth(2, 140)
        self.setColumnWidth(3, 180)
        self.setColumnWidth(4, 80)
        self.setColumnWidth(5, 80)
        self.setShowGrid(False)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_ctx)
        self.itemSelectionChanged.connect(self._on_sel)
        self.setStyleSheet(
            f"""
            QTableWidget {{
                background-color: {PANEL};
                alternate-background-color: #141a22;
                color: {TEXT};
            }}
            QTableWidget::item:selected {{
                background-color: #3a2e14;
                color: {TEXT};
            }}
            """
        )

    def hops(self) -> List[TracerouteHop]:
        return list(self._hops)

    def set_hops(self, hops: List[TracerouteHop], selected_num: Optional[int] = None):
        self.blockSignals(True)
        self._hops = list(hops)
        self.setRowCount(0)
        last = hops[-1].hop_num if hops else -1
        for hop in hops:
            row = self.rowCount()
            self.insertRow(row)
            is_dest = hop.hop_num == last and hop.hop_num != 0
            rtt = ""
            if hop.state == "probing":
                rtt = "..."
            elif hop.avg_rtt is not None:
                rtt = f"{hop.avg_rtt:.1f}"
            status = hop.state if hop.state == "probing" else ("timeout" if hop.timed_out else "ok")
            vals = [
                "PC" if hop.hop_num == 0 else str(hop.hop_num),
                hop.role or "",
                hop.ip or "",
                hop.hostname or "(no hostname)",
                rtt,
                status,
                _note(hop, is_dest),
            ]
            for col, v in enumerate(vals):
                item = QTableWidgetItem(v)
                if hop.timed_out:
                    item.setForeground(QBrush(QColor(CORAL)))
                elif hop.state == "probing":
                    item.setForeground(QBrush(QColor(AMBER)))
                elif col == 5:
                    item.setForeground(QBrush(QColor(EMERALD)))
                self.setItem(row, col, item)
            self.setRowHeight(row, 28)
        self.blockSignals(False)
        if selected_num is not None:
            self.select_hop_num(selected_num)

    def select_hop_num(self, hop_num: int):
        for i, hop in enumerate(self._hops):
            if hop.hop_num == hop_num:
                self.blockSignals(True)
                self.selectRow(i)
                self.blockSignals(False)
                self.scrollToItem(self.item(i, 0))
                return

    def _on_sel(self):
        rows = self.selectionModel().selectedRows()
        if not rows:
            return
        idx = rows[0].row()
        if 0 <= idx < len(self._hops):
            self.hop_selected.emit(self._hops[idx])

    def _on_ctx(self, pos):
        from PySide6.QtWidgets import QApplication
        idx = self.indexAt(pos)
        if not idx.isValid() or idx.row() >= len(self._hops):
            return
        hop = self._hops[idx.row()]
        if hop.state == "probing":
            return
        self.selectRow(idx.row())
        gp = self.viewport().mapToGlobal(pos)
        if QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.hop_power_context.emit(hop, gp)
        else:
            self.hop_context.emit(hop, gp)
