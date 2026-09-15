"""Glass hop story card matching Command Center mockup density."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from core.traceroute import TracerouteHop
from ui.sparkline import Sparkline
from ui.theme import AMBER, CORAL, EMERALD, MUTED, TEXT


def hop_quality(hop: TracerouteHop) -> tuple[str, str]:
    if hop.state == "probing":
        return "Probing", AMBER
    if hop.timed_out or hop.state == "timeout":
        return "Timeout", CORAL
    rtt = hop.avg_rtt
    if rtt is None:
        return "Unknown", MUTED
    if hop.hop_num == 0 or rtt < 10:
        return "Excellent", EMERALD
    if rtt < 40:
        return "Good", EMERALD
    return "Warning", AMBER


def story_title(hop: TracerouteHop, is_dest: bool = False) -> str:
    if hop.hop_num == 0:
        return "PC"
    if is_dest:
        return "destination"
    role = (hop.role or "").strip()
    if role in ("gateway", "LAN", "CGNAT", "public", "This PC"):
        if role == "This PC":
            return "PC"
        return role
    return f"Hop {hop.hop_num}"


class StoryCard(QFrame):
    selected = Signal(object)
    context_requested = Signal(object, object)
    power_context_requested = Signal(object, object)

    def __init__(self, hop: TracerouteHop, is_dest: bool = False, parent=None):
        super().__init__(parent)
        self.hop = hop
        self.setObjectName("HopCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(148, 148)
        self.setMaximumWidth(220)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_ctx)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(4)

        top = QHBoxLayout()
        title = QLabel(story_title(hop, is_dest))
        title.setObjectName("HopTitle")
        top.addWidget(title)
        top.addStretch()
        q, color = hop_quality(hop)
        self._dot = QLabel("*")
        self._dot.setStyleSheet(f"color: {color}; font-size: 11pt;")
        top.addWidget(self._dot)
        lay.addLayout(top)

        status = QLabel(q)
        status.setStyleSheet(f"color: {color}; font-size: 9pt;")
        lay.addWidget(status)

        spark = Sparkline()
        samples = [hop.rtt1, hop.rtt2, hop.rtt3]
        # repeat so the spark has shape even with 3 probes
        vals = [s for s in samples if s is not None]
        if vals:
            spark.set_samples(vals * 3, fail=hop.timed_out)
        else:
            spark.set_samples([], fail=hop.timed_out)
        lay.addWidget(spark)

        lay.addStretch()
        if hop.timed_out:
            rtt = QLabel("timeout")
            rtt.setObjectName("HopLatencyFail")
        elif hop.state == "probing":
            rtt = QLabel("probing...")
            rtt.setObjectName("HopMeta")
        elif hop.avg_rtt is not None:
            rtt = QLabel(f"{hop.avg_rtt:.1f} ms")
            rtt.setObjectName("HopLatency")
        else:
            rtt = QLabel("-")
            rtt.setObjectName("HopMeta")
        lay.addWidget(rtt)

        sub = hop.ip or hop.hostname or ("waiting" if hop.state == "probing" else "no address")
        meta = QLabel(sub)
        meta.setObjectName("HopMeta")
        meta.setWordWrap(True)
        lay.addWidget(meta)

    def set_selected(self, on: bool):
        # Keep border WIDTH constant so selection never shifts/overlaps neighbors.
        color = EMERALD if on else "#2a3340"
        self.setStyleSheet(
            f"QFrame#HopCard {{ border: 2px solid {color}; background-color: #1c2330; }}"
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(self.hop)
        super().mousePressEvent(event)

    def _on_ctx(self, pos):
        from PySide6.QtWidgets import QApplication
        gp = self.mapToGlobal(pos)
        if QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.power_context_requested.emit(self.hop, gp)
        else:
            self.context_requested.emit(self.hop, gp)
