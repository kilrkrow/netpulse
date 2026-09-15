"""Selected-hop detail card under the path overview."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from core.traceroute import TracerouteHop
from ui.theme import CORAL, EMERALD, MUTED


class HopDetailPanel(QFrame):
    context_requested = Signal(object, object)
    power_context_requested = Signal(object, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("HopCard")
        self._hop: Optional[TracerouteHop] = None
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_ctx)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(6)

        top = QHBoxLayout()
        self._title = QLabel("Select a hop on the overview")
        self._title.setObjectName("HopTitle")
        top.addWidget(self._title)
        top.addStretch()
        self._badge = QLabel("")
        self._badge.setStyleSheet(
            f"color: {EMERALD}; border: 1px solid {EMERALD}; border-radius: 6px; padding: 2px 8px; font-size: 9pt;"
        )
        top.addWidget(self._badge)
        self._state = QLabel("")
        top.addWidget(self._state)
        lay.addLayout(top)

        self._host = QLabel("")
        self._host.setObjectName("HopMeta")
        self._host.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self._host)

        row = QHBoxLayout()
        self._ip = QLabel("")
        self._ip.setObjectName("HopMeta")
        self._ip.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._rtt = QLabel("")
        self._rtt.setObjectName("HopLatency")
        row.addWidget(self._ip)
        row.addStretch()
        row.addWidget(self._rtt)
        lay.addLayout(row)

        self._hint = QLabel("Right-click for verbs. Shift+right-click for CLI.")
        self._hint.setObjectName("HopMeta")
        lay.addWidget(self._hint)

    def clear(self):
        self._hop = None
        self._title.setText("Select a hop on the overview")
        self._badge.hide()
        self._state.setText("")
        self._host.setText("")
        self._ip.setText("")
        self._rtt.setText("")

    def set_hop(self, hop: Optional[TracerouteHop]):
        self._hop = hop
        if not hop:
            self.clear()
            return
        if hop.hop_num == 0:
            self._title.setText("This PC (source)")
        else:
            self._title.setText(f"Hop {hop.hop_num}")
        role = hop.role or ""
        if role:
            self._badge.setText(role)
            self._badge.show()
        else:
            self._badge.hide()
        if hop.state == "probing":
            self._state.setText("probing")
            self._state.setStyleSheet(f"color: #fbbf24;")
        elif hop.timed_out:
            self._state.setText("timeout")
            self._state.setStyleSheet(f"color: {CORAL};")
        else:
            self._state.setText("ok")
            self._state.setStyleSheet(f"color: {EMERALD};")
        self._host.setText(hop.hostname or "(no hostname)")
        self._ip.setText(hop.ip or "(no address yet)")
        if hop.state == "probing":
            self._rtt.setText("probing...")
            self._rtt.setObjectName("HopMeta")
        elif hop.timed_out or hop.avg_rtt is None:
            self._rtt.setText("timeout / no RTT")
            self._rtt.setObjectName("HopLatencyFail")
            self._rtt.setStyleSheet(f"color: {CORAL}; font-weight: 600;")
        else:
            parts = []
            for r in (hop.rtt1, hop.rtt2, hop.rtt3):
                parts.append(f"{r:.0f}" if r is not None else "*")
            self._rtt.setText(f"{hop.avg_rtt:.0f} ms avg  ({'/'.join(parts)})")
            self._rtt.setStyleSheet(f"color: {EMERALD}; font-weight: 600;")

    def hop(self) -> Optional[TracerouteHop]:
        return self._hop

    def _on_ctx(self, pos):
        if not self._hop or self._hop.state == "probing":
            return
        from PySide6.QtWidgets import QApplication
        global_pos = self.mapToGlobal(pos)
        if QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.power_context_requested.emit(self._hop, global_pos)
        else:
            self.context_requested.emit(self._hop, global_pos)
