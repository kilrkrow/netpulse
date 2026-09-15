"""Path hop card widget for Command Center."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from core.traceroute import TracerouteHop
from ui.theme import CORAL, EMERALD, MUTED


class StatusDot(QWidget):
    def __init__(self, ok: bool, parent=None):
        super().__init__(parent)
        self._ok = ok
        self.setFixedSize(12, 12)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QBrush(QColor(EMERALD if self._ok else CORAL)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(1, 1, 10, 10)
        p.end()


class HopCard(QFrame):
    """Clickable/right-clickable hop card."""

    context_requested = Signal(object, object)  # hop, QPoint global
    power_context_requested = Signal(object, object)

    def __init__(self, hop: TracerouteHop, label: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.hop = hop
        self.setObjectName("HopCard")
        self.setFixedWidth(168)
        self.setMinimumHeight(96)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_ctx)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(4)

        top = QHBoxLayout()
        title = label or (f"Hop {hop.hop_num}" if hop.hop_num else "PC")
        t = QLabel(title)
        t.setObjectName("HopTitle")
        top.addWidget(t)
        top.addStretch()
        ok = not hop.timed_out and hop.avg_rtt is not None
        if hop.hop_num == 0:
            ok = True
        top.addWidget(StatusDot(ok))
        lay.addLayout(top)

        host = hop.hostname or hop.ip or ("timeout" if hop.timed_out else "-")
        if hop.hostname and hop.ip:
            host = hop.hostname
        hl = QLabel(host)
        hl.setObjectName("HopMeta")
        hl.setWordWrap(True)
        lay.addWidget(hl)

        if hop.ip and hop.hostname:
            ip_l = QLabel(hop.ip)
            ip_l.setObjectName("HopMeta")
            lay.addWidget(ip_l)

        asn = getattr(hop, "asn", None) or "ASN N/A"
        al = QLabel(str(asn))
        al.setObjectName("HopMeta")
        al.setStyleSheet(f"color: {MUTED};")
        lay.addWidget(al)

        lay.addStretch()
        if hop.timed_out or hop.avg_rtt is None:
            lat = QLabel("--- ms" if hop.hop_num else "local")
            lat.setObjectName("HopLatencyFail" if hop.hop_num else "HopLatency")
        else:
            lat = QLabel(f"{hop.avg_rtt:.0f} ms")
            lat.setObjectName("HopLatency")
        lay.addWidget(lat)

    def _on_ctx(self, pos):
        from PySide6.QtWidgets import QApplication
        mods = QApplication.keyboardModifiers()
        global_pos = self.mapToGlobal(pos)
        if mods & Qt.KeyboardModifier.ShiftModifier:
            self.power_context_requested.emit(self.hop, global_pos)
        else:
            self.context_requested.emit(self.hop, global_pos)
