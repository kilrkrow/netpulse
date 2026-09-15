"""Selected-hop intel panel (Path lab side-card energy)."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from core.traceroute import TracerouteHop
from ui.sparkline import Sparkline
from ui.story_card import hop_quality
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
        self.setMinimumWidth(260)
        self.setMaximumWidth(340)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(8)

        head = QLabel("HOP INTEL")
        head.setObjectName("HopMeta")
        lay.addWidget(head)

        top = QHBoxLayout()
        self._title = QLabel("Select a hop")
        self._title.setObjectName("HopTitle")
        self._title.setStyleSheet("font-size: 14pt;")
        top.addWidget(self._title)
        top.addStretch()
        self._badge = QLabel("")
        self._badge.setStyleSheet(
            f"color: {EMERALD}; border: 1px solid {EMERALD}; border-radius: 6px; padding: 2px 8px; font-size: 9pt;"
        )
        top.addWidget(self._badge)
        lay.addLayout(top)

        self._quality = QLabel("")
        lay.addWidget(self._quality)

        self._spark = Sparkline()
        self._spark.setMinimumHeight(56)
        self._spark.setMaximumHeight(72)
        lay.addWidget(self._spark)

        self._host = QLabel("")
        self._host.setObjectName("HopMeta")
        self._host.setWordWrap(True)
        self._host.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self._host)

        self._ip = QLabel("")
        self._ip.setObjectName("HopMeta")
        self._ip.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self._ip)

        self._rtt = QLabel("")
        self._rtt.setObjectName("HopLatency")
        lay.addWidget(self._rtt)

        self._explain = QLabel("")
        self._explain.setObjectName("HopMeta")
        self._explain.setWordWrap(True)
        lay.addWidget(self._explain)

        lay.addStretch(1)
        hint = QLabel("Right-click for verbs. Shift+right-click for CLI.")
        hint.setObjectName("HopMeta")
        lay.addWidget(hint)

    def clear(self):
        self._hop = None
        self._title.setText("Select a hop")
        self._badge.hide()
        self._quality.setText("")
        self._spark.set_samples([])
        self._host.setText("")
        self._ip.setText("")
        self._rtt.setText("")
        self._explain.setText("")

    def set_hop(self, hop: Optional[TracerouteHop], is_dest: bool = False):
        self._hop = hop
        if not hop:
            self.clear()
            return
        if hop.hop_num == 0:
            self._title.setText("This PC")
        else:
            self._title.setText(f"Hop {hop.hop_num}")
        role = hop.role or ("destination" if is_dest else "")
        if role:
            self._badge.setText(role)
            self._badge.show()
        else:
            self._badge.hide()
        q, color = hop_quality(hop)
        self._quality.setText(q)
        self._quality.setStyleSheet(f"color: {color}; font-weight: 600;")
        samples = [hop.rtt1, hop.rtt2, hop.rtt3]
        vals = [s for s in samples if s is not None]
        self._spark.set_samples(vals * 3 if vals else [], fail=hop.timed_out)
        self._host.setText(hop.hostname or "(no hostname)")
        self._ip.setText(hop.ip or "(no address yet)")
        if hop.state == "probing":
            self._rtt.setText("probing...")
            self._rtt.setStyleSheet("")
            self._explain.setText("Waiting on this hop's ICMP probes.")
        elif hop.timed_out:
            self._rtt.setText("timeout / no RTT")
            self._rtt.setStyleSheet(f"color: {CORAL}; font-weight: 600;")
            self._explain.setText(
                "No ICMP reply at this hop. Common on filtered core routers. "
                "Later hops may still answer; the path is not necessarily dead."
            )
        elif hop.avg_rtt is not None:
            parts = []
            for r in (hop.rtt1, hop.rtt2, hop.rtt3):
                parts.append(f"{r:.0f}" if r is not None else "*")
            self._rtt.setText(f"{hop.avg_rtt:.1f} ms avg  ({'/'.join(parts)})")
            self._rtt.setStyleSheet(f"color: {EMERALD}; font-weight: 600;")
            self._explain.setText("")
        else:
            self._rtt.setText("-")
            self._explain.setText("")

    def hop(self) -> Optional[TracerouteHop]:
        return self._hop

    def _on_ctx(self, pos):
        if not self._hop or self._hop.state == "probing":
            return
        from PySide6.QtWidgets import QApplication
        gp = self.mapToGlobal(pos)
        if QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.power_context_requested.emit(self._hop, gp)
        else:
            self.context_requested.emit(self._hop, gp)
