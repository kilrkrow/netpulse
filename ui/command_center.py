"""Command Center Path view: empty canvas + hop cards."""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.traceroute import TracerouteHop
from ui.context_verbs import VerbCallbacks, build_empty_canvas_menu, build_hop_menu, build_hop_power_menu
from ui.hop_card import HopCard


class CommandCenterView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._cb: Optional[VerbCallbacks] = None
        self._hops: List[TracerouteHop] = []
        self._cards: List[HopCard] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        self._status = QLabel("Enter a target and Run to map the path.")
        self._status.setObjectName("EmptyHint")
        root.addWidget(self._status)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._canvas = QFrame()
        self._canvas.setObjectName("PathCanvas")
        self._canvas.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._canvas.customContextMenuRequested.connect(self._on_empty_ctx)
        self._row = QHBoxLayout(self._canvas)
        self._row.setContentsMargins(16, 24, 16, 24)
        self._row.setSpacing(12)

        self._empty = QLabel("Right-click for Paste target & Run, Recent, or a playbook.")
        self._empty.setObjectName("EmptyHint")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._row.addWidget(self._empty)
        self._row.addStretch(1)

        self._scroll.setWidget(self._canvas)
        root.addWidget(self._scroll, 1)

    def set_callbacks(self, cb: VerbCallbacks):
        self._cb = cb

    def set_status(self, text: str):
        self._status.setText(text)

    def _clear_cards(self):
        self._cards.clear()
        while self._row.count():
            item = self._row.takeAt(0)
            w = item.widget()
            if w is not None and w is not self._empty:
                w.deleteLater()
        self._empty.setParent(self._canvas)
        self._row.addWidget(self._empty)
        self._row.addStretch(1)
        self._empty.show()

    def clear_path(self):
        self._hops = []
        self._clear_cards()

    def begin_run(self, target: str):
        self._hops = []
        self._clear_cards()
        self._empty.hide()
        pc = TracerouteHop(
            hop_num=0,
            ip="127.0.0.1",
            hostname="This PC",
            rtt1=0,
            rtt2=0,
            rtt3=0,
            avg_rtt=0,
            timed_out=False,
        )
        self._add_card(pc, label="PC")
        self.set_status(f"Tracing path to {target}...")

    def add_hop(self, hop: TracerouteHop):
        self._hops.append(hop)
        self._add_card(hop)

    def finish_run(self, hops: List[TracerouteHop], error: Optional[str] = None):
        self._hops = list(hops)
        if error:
            self.set_status(f"Path failed: {error}")
        elif not hops:
            self.set_status("No hops returned. Check the target and try again.")
        else:
            last = hops[-1]
            dest = last.hostname or last.ip or "destination"
            self.set_status(f"Path complete - {len(hops)} hop(s) to {dest}.")

    def hops(self) -> List[TracerouteHop]:
        return list(self._hops)

    def _add_card(self, hop: TracerouteHop, label: Optional[str] = None):
        # Remove trailing stretch, add card, restore stretch
        stretch_item = None
        if self._row.count():
            stretch_item = self._row.takeAt(self._row.count() - 1)
        card = HopCard(hop, label=label)
        if self._cb:
            card.context_requested.connect(self._show_hop_menu)
            card.power_context_requested.connect(self._show_hop_power)
        self._cards.append(card)
        self._row.addWidget(card)
        self._row.addStretch(1)
        if stretch_item is not None:
            del stretch_item

    def _show_hop_menu(self, hop, global_pos):
        if not self._cb:
            return
        build_hop_menu(self, hop, self._cb).exec(global_pos)

    def _show_hop_power(self, hop, global_pos):
        if not self._cb:
            return
        build_hop_power_menu(self, hop, self._cb).exec(global_pos)

    def _on_empty_ctx(self, pos):
        if not self._cb:
            return
        build_empty_canvas_menu(self, self._cb).exec(self._canvas.mapToGlobal(pos))
