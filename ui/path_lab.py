"""Path lab: dense hop table + intel (same density as Command Center lower pane)."""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSplitter, QVBoxLayout, QWidget

from core.traceroute import TracerouteHop
from ui.context_verbs import VerbCallbacks, build_hop_menu, build_hop_power_menu
from ui.hop_detail import HopDetailPanel
from ui.hop_table import HopTable


class PathLabView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._hops: List[TracerouteHop] = []
        self._cb: Optional[VerbCallbacks] = None
        self._filtered: set = set()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        head = QHBoxLayout()
        title = QLabel("Path lab")
        title.setStyleSheet("font-size: 14pt; font-weight: 600;")
        head.addWidget(title)
        head.addStretch()
        hint = QLabel("Dense hop table + intel. Right-click / Shift+right-click for verbs.")
        hint.setObjectName("HopMeta")
        head.addWidget(hint)
        lay.addLayout(head)

        split = QSplitter(Qt.Orientation.Horizontal)
        self._table = HopTable()
        self._table.hop_selected.connect(self._on_select)
        self._table.hop_context.connect(self._on_ctx)
        self._table.hop_power_context.connect(self._on_power)
        split.addWidget(self._table)
        self._detail = HopDetailPanel()
        self._detail.context_requested.connect(self._on_ctx)
        self._detail.power_context_requested.connect(self._on_power)
        split.addWidget(self._detail)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        lay.addWidget(split, 1)

    def set_callbacks(self, cb: VerbCallbacks):
        self._cb = cb

    def set_hops(self, hops: List[TracerouteHop]):
        self._hops = list(hops)
        # annotate filtered in notes via role/status already; keep set for mark
        self._table.set_hops(hops)
        if hops:
            from ui.hop_table import worst_hop
            w = worst_hop(hops)
            if w:
                self._table.select_hop_num(w.hop_num)
                self._detail.set_hop(w, is_dest=(w is hops[-1]))

    def mark_filtered(self, hop: TracerouteHop):
        self._filtered.add(hop.hop_num)
        hop.state = hop.state  # no-op; notes path uses timed_out
        # force note by setting hostname suffix? keep simple: refresh
        self.set_hops(self._hops)

    def _on_select(self, hop: TracerouteHop):
        is_dest = bool(self._hops) and hop is self._hops[-1]
        self._detail.set_hop(hop, is_dest=is_dest)

    def _on_ctx(self, hop, gp):
        if not self._cb:
            return
        build_hop_menu(self, hop, self._cb, table=True).exec(gp)

    def _on_power(self, hop, gp):
        if not self._cb:
            return
        build_hop_power_menu(self, hop, self._cb).exec(gp)
