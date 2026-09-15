"""Command Center Path view: live overview + hop detail."""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from core.traceroute import TracerouteHop
from ui.context_verbs import (
    VerbCallbacks,
    build_empty_canvas_menu,
    build_hop_menu,
    build_hop_power_menu,
)
from ui.hop_detail import HopDetailPanel
from ui.path_overview import PathOverview


class CommandCenterView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._cb: Optional[VerbCallbacks] = None
        self._hops: List[TracerouteHop] = []
        self._pc: Optional[TracerouteHop] = None
        self._probing: Optional[int] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        self._status = QLabel("Enter a target and Run to map the path.")
        self._status.setObjectName("EmptyHint")
        self._status.setWordWrap(True)
        root.addWidget(self._status)

        self._overview = PathOverview()
        self._overview.hop_selected.connect(self._on_select)
        self._overview.hop_context.connect(self._show_hop_menu)
        self._overview.hop_power_context.connect(self._show_hop_power)
        root.addWidget(self._overview)

        self._detail = HopDetailPanel()
        self._detail.context_requested.connect(self._show_hop_menu)
        self._detail.power_context_requested.connect(self._show_hop_power)
        root.addWidget(self._detail)

        self._empty = QLabel(
            "Right-click empty area for Paste target & Run, Recent, or a playbook."
        )
        self._empty.setObjectName("EmptyHint")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._empty.customContextMenuRequested.connect(self._on_empty_ctx)
        root.addWidget(self._empty)
        root.addStretch(1)

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
        self._overview.set_hops([])
        self._overview.select_hop_num(None)
        self._detail.clear()
        self._empty.show()

    def begin_run(self, target: str, gateway: Optional[str] = None):
        self._hops = []
        self._probing = 1
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
        self._empty.hide()
        self._refresh_overview()
        self._overview.select_hop_num(0)
        self.set_status(f"Probing hop 1...  (0s)  target {target}")

    def set_probing(self, hop_num: int, elapsed: float, hint: str = ""):
        self._probing = hop_num
        self._refresh_overview()
        base = f"Probing hop {hop_num}...  ({elapsed:.0f}s)"
        if hint:
            base = f"{base}  -  {hint}" if False else f"{base}  -  {hint}"
        self.set_status(base)

    def add_hop(self, hop: TracerouteHop):
        # replace if same hop_num
        self._hops = [h for h in self._hops if h.hop_num != hop.hop_num]
        self._hops.append(hop)
        self._hops.sort(key=lambda h: h.hop_num)
        self._probing = hop.hop_num + 1
        self._refresh_overview()
        # auto-focus latest completed hop (or keep selection)
        if self._overview.selected_hop() is None or (
            self._overview.selected_hop()
            and self._overview.selected_hop().state == "probing"
        ):
            self._overview.select_hop_num(hop.hop_num)
        else:
            # update detail if same hop refreshed
            sel = self._overview.selected_hop()
            if sel and sel.hop_num == hop.hop_num:
                self._detail.set_hop(hop)

    def finish_run(
        self,
        hops: List[TracerouteHop],
        error: Optional[str] = None,
        cancelled: bool = False,
    ):
        self._hops = list(hops)
        self._probing = None
        self._refresh_overview()
        if cancelled:
            self.set_status(f"Cancelled after {len(hops)} hop(s).")
        elif error:
            self.set_status(f"Path failed: {error}")
        elif not hops:
            self.set_status("No hops returned. Check the target and try again.")
            self._empty.show()
        else:
            last = hops[-1]
            dest = last.hostname or last.ip or "destination"
            timeouts = sum(1 for h in hops if h.timed_out)
            extra = f"  ({timeouts} timeout)" if timeouts else ""
            self.set_status(f"Path complete - {len(hops)} hop(s) to {dest}.{extra}")
            # select destination
            self._overview.select_hop_num(last.hop_num)

    def hops(self) -> List[TracerouteHop]:
        return list(self._hops)

    def all_hops_with_pc(self) -> List[TracerouteHop]:
        out = []
        if self._pc:
            out.append(self._pc)
        out.extend(self._hops)
        return out

    def _refresh_overview(self):
        display = self.all_hops_with_pc()
        self._overview.set_hops(display, probing=self._probing)

    def _on_select(self, hop: Optional[TracerouteHop]):
        self._detail.set_hop(hop)

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
