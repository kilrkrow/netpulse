"""Command Center Path: story cards + dense table + intel. Filled canvas."""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from core.traceroute import TracerouteHop
from ui.context_verbs import (
    VerbCallbacks,
    build_empty_canvas_menu,
    build_hop_menu,
    build_hop_power_menu,
)
from ui.hop_detail import HopDetailPanel
from ui.hop_table import HopTable, worst_hop
from ui.path_overview import PathOverview
from ui.story_card import StoryCard



class StoryStrip(QWidget):
    """Wrapping glass cards - no horizontal slider required to see the story."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(10)
        self._cards: List[StoryCard] = []
        self._hops: List[TracerouteHop] = []
        self._handlers = None  # (select, ctx, power)

    def set_handlers(self, select, ctx, power):
        self._handlers = (select, ctx, power)

    def set_hops(self, hops: List[TracerouteHop], selected_num: Optional[int] = None):
        self._hops = list(hops)
        self._rebuild(selected_num)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rebuild(self._selected_num() if self._cards else None)

    def _selected_num(self) -> Optional[int]:
        for c in self._cards:
            # crude: last selected style not stored; parent tracks
            return None
        return None

    def _rebuild(self, selected_num: Optional[int]):
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._cards = []
        hops = self._hops
        if not hops:
            return
        cols = max(1, self.width() // 170)
        last = hops[-1].hop_num if hops else -1
        for i, hop in enumerate(hops):
            is_dest = hop.hop_num == last and hop.hop_num != 0
            card = StoryCard(hop, is_dest=is_dest)
            if self._handlers:
                sel, ctx, power = self._handlers
                card.selected.connect(sel)
                card.context_requested.connect(ctx)
                card.power_context_requested.connect(power)
            card.set_selected(selected_num is not None and hop.hop_num == selected_num)
            self._grid.addWidget(card, i // cols, i % cols)
            self._cards.append(card)


class CommandCenterView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._cb: Optional[VerbCallbacks] = None
        self._hops: List[TracerouteHop] = []
        self._pc: Optional[TracerouteHop] = None
        self._probing: Optional[int] = None
        self._selected: Optional[int] = None
        self._target: str = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 4, 8, 4)
        root.setSpacing(8)

        self._status = QLabel("Enter a target and Run to map the path.")
        self._status.setObjectName("EmptyHint")
        self._status.setWordWrap(True)
        self._status.setStyleSheet("font-size: 12pt;")
        root.addWidget(self._status)

        self._overview = PathOverview()
        self._overview.hop_selected.connect(self._on_select)
        self._overview.hop_context.connect(self._show_hop_menu)
        self._overview.hop_power_context.connect(self._show_hop_power)
        root.addWidget(self._overview)

        self._cards = StoryStrip()
        self._cards.set_handlers(self._on_select, self._show_hop_menu, self._show_hop_power)
        self._cards_scroll = QScrollArea()
        self._cards_scroll.setWidgetResizable(True)
        self._cards_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._cards_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._cards_scroll.setWidget(self._cards)
        self._cards_scroll.setMinimumHeight(160)
        self._cards_scroll.setMaximumHeight(280)
        self._cards_scroll.hide()
        root.addWidget(self._cards_scroll)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)

        self._table = HopTable()
        self._table.hop_selected.connect(self._on_select)
        self._table.hop_context.connect(self._show_hop_menu)
        self._table.hop_power_context.connect(self._show_hop_power)
        split.addWidget(self._table)

        self._detail = HopDetailPanel()
        self._detail.context_requested.connect(self._show_hop_menu)
        self._detail.power_context_requested.connect(self._show_hop_power)
        split.addWidget(self._detail)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        split.setSizes([900, 300])
        root.addWidget(split, 1)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_empty_ctx)

    def set_callbacks(self, cb: VerbCallbacks):
        self._cb = cb

    def set_status(self, text: str):
        self._status.setText(text)

    def clear_path(self):
        self._hops = []
        self._pc = None
        self._probing = None
        self._selected = None
        self._overview.set_hops([])
        self._cards.set_hops([])
        self._cards_scroll.hide()
        self._table.set_hops([])
        self._detail.clear()

    def begin_run(self, target: str, gateway: Optional[str] = None):
        self._target = target
        self._hops = []
        self._probing = 1
        self._selected = 0
        self._pc = TracerouteHop(
            hop_num=0,
            ip="127.0.0.1",
            hostname="This PC",
            rtt1=0,
            rtt2=0,
            rtt3=0,
            avg_rtt=0,
            timed_out=False,
            role="This PC",
            state="ok",
        )
        self._refresh()
        self.select_hop_num(0)
        self.set_status(f"Probing hop 1...  (0s)  target {target}")

    def set_probing(self, hop_num: int, elapsed: float, hint: str = ""):
        self._probing = hop_num
        self._refresh()
        base = f"Probing hop {hop_num}...  ({elapsed:.0f}s)"
        if hint:
            base = f"{base}  -  {hint}"
        self.set_status(base)

    def add_hop(self, hop: TracerouteHop):
        self._hops = [h for h in self._hops if h.hop_num != hop.hop_num]
        self._hops.append(hop)
        self._hops.sort(key=lambda h: h.hop_num)
        self._probing = hop.hop_num + 1
        self._refresh()
        if hop.timed_out:
            self.select_hop_num(hop.hop_num)
        elif self._selected in (None, 0):
            self.select_hop_num(hop.hop_num)

    def finish_run(
        self,
        hops: List[TracerouteHop],
        error: Optional[str] = None,
        cancelled: bool = False,
    ):
        self._hops = list(hops)
        self._probing = None
        self._refresh()
        n = len(hops)
        timeouts = [h for h in hops if h.timed_out]
        dest = ""
        if hops:
            last = hops[-1]
            dest = last.hostname or last.ip or "destination"
        if cancelled:
            self.set_status(f"Cancelled after {n} hop(s).")
        elif error:
            self.set_status(f"Path failed: {error}")
        elif not hops:
            self.set_status("No hops returned. Check the target and try again.")
        else:
            if timeouts:
                t = timeouts[0]
                extra = f"{len(timeouts)} timeout at hop {t.hop_num}"
                self.set_status(f"Path complete - {n} hops to {dest}. {extra}.")
            else:
                self.set_status(f"Path complete - {n} hops to {dest}.")
            w = worst_hop(self.all_hops_with_pc())
            if w:
                self.select_hop_num(w.hop_num)

    def hops(self) -> List[TracerouteHop]:
        return list(self._hops)

    def all_hops_with_pc(self) -> List[TracerouteHop]:
        out = []
        if self._pc:
            out.append(self._pc)
        out.extend(self._hops)
        if self._probing is not None and not any(h.hop_num == self._probing for h in out):
            out.append(
                TracerouteHop(
                    hop_num=self._probing,
                    ip=None,
                    hostname=None,
                    rtt1=None,
                    rtt2=None,
                    rtt3=None,
                    avg_rtt=None,
                    timed_out=False,
                    role="",
                    state="probing",
                )
            )
        return out

    def select_hop_num(self, hop_num: Optional[int]):
        self._selected = hop_num
        display = self.all_hops_with_pc()
        hop = next((h for h in display if h.hop_num == hop_num), None)
        last = display[-1].hop_num if display else -1
        is_dest = hop is not None and hop.hop_num == last and hop.hop_num != 0
        self._overview.select_hop_num(hop_num, emit=False)
        self._table.select_hop_num(hop_num if hop_num is not None else -1)
        self._cards.set_hops(display, selected_num=hop_num)
        self._detail.set_hop(hop, is_dest=is_dest)

    def _refresh(self):
        display = self.all_hops_with_pc()
        self._overview.set_hops(display, probing=self._probing)
        self._table.set_hops(display, selected_num=self._selected)
        self._cards.set_hops(display, selected_num=self._selected)
        if display:
            self._cards_scroll.show()
        else:
            self._cards_scroll.hide()

    def _on_select(self, hop: Optional[TracerouteHop]):
        if hop is None:
            return
        self.select_hop_num(hop.hop_num)

    def _show_hop_menu(self, hop, global_pos):
        if not self._cb or not hop or hop.state == "probing":
            return
        build_hop_menu(self, hop, self._cb).exec(global_pos)

    def _show_hop_power(self, hop, global_pos):
        if not self._cb or not hop or hop.state == "probing":
            return
        build_hop_power_menu(self, hop, self._cb).exec(global_pos)

    def _on_empty_ctx(self, pos):
        if not self._cb:
            return
        build_empty_canvas_menu(self, self._cb).exec(self.mapToGlobal(pos))
