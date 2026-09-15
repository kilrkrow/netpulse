"""Full-width path overview timeline + hop detail panel."""

from __future__ import annotations

from typing import Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.traceroute import TracerouteHop, classify_role
from ui.theme import BORDER, CHARCOAL, CORAL, EMERALD, MUTED, PANEL_GLASS, TEXT


def _state_color(hop: TracerouteHop) -> QColor:
    if hop.state == "probing":
        return QColor(AMBER := "#fbbf24")
    if hop.timed_out or hop.state == "timeout":
        return QColor(CORAL)
    if hop.avg_rtt is not None and hop.avg_rtt >= 150:
        return QColor("#fbbf24")
    return QColor(EMERALD)


class PathOverview(QWidget):
    """Compact full-width hop timeline - no horizontal scroll required."""

    hop_selected = Signal(object)  # TracerouteHop | None
    hop_context = Signal(object, object)  # hop, global QPoint
    hop_power_context = Signal(object, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hops: List[TracerouteHop] = []
        self._selected: Optional[int] = None  # hop_num
        self._probing_num: Optional[int] = None
        self.setMinimumHeight(72)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_ctx)
        self._hit: List[tuple] = []  # (hop_num, x0, x1)

    def set_hops(self, hops: List[TracerouteHop], probing: Optional[int] = None):
        self._hops = list(hops)
        self._probing_num = probing
        if self._selected is not None and not any(h.hop_num == self._selected for h in hops):
            # keep selection if still present
            pass
        self.update()

    def set_probing(self, hop_num: Optional[int]):
        self._probing_num = hop_num
        self.update()

    def select_hop_num(self, hop_num: Optional[int]):
        self._selected = hop_num
        self.update()
        hop = next((h for h in self._hops if h.hop_num == hop_num), None)
        self.hop_selected.emit(hop)

    def selected_hop(self) -> Optional[TracerouteHop]:
        if self._selected is None:
            return None
        return next((h for h in self._hops if h.hop_num == self._selected), None)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor(PANEL_GLASS))
        p.setPen(QPen(QColor(BORDER)))
        p.drawRoundedRect(0, 0, w - 1, h - 1, 10, 10)

        hops = self._hops
        self._hit = []
        if not hops and self._probing_num is None:
            p.setPen(QColor(MUTED))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Path overview - run a target")
            p.end()
            return

        # Include probing placeholder if ahead of known hops
        display: List[TracerouteHop] = list(hops)
        if self._probing_num is not None and not any(h.hop_num == self._probing_num for h in hops):
            display.append(
                TracerouteHop(
                    hop_num=self._probing_num,
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
            display.sort(key=lambda x: x.hop_num)

        n = max(len(display), 1)
        margin = 28
        usable = max(w - 2 * margin, 1)
        step = usable / max(n - 1, 1) if n > 1 else 0
        cy = h // 2 + 4

        # spine
        if n > 1:
            p.setPen(QPen(QColor(BORDER), 2))
            p.drawLine(margin, cy, w - margin, cy)

        for i, hop in enumerate(display):
            x = int(margin + i * step) if n > 1 else w // 2
            r = 9 if hop.hop_num in (0, display[-1].hop_num) else 7
            if hop.hop_num == self._selected:
                r += 2
            color = _state_color(hop)
            # glow for selected / ends
            if hop.hop_num == 0 or hop is display[-1] or hop.hop_num == self._selected:
                p.setBrush(QBrush(QColor(color.red(), color.green(), color.blue(), 60)))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(x - r - 4, cy - r - 4, 2 * r + 8, 2 * r + 8)
            p.setBrush(QBrush(color))
            p.setPen(QPen(QColor(CHARCOAL), 1))
            p.drawEllipse(x - r, cy - r, 2 * r, 2 * r)

            # label above
            p.setPen(QColor(TEXT if hop.hop_num == self._selected else MUTED))
            font = QFont("Segoe UI", 8)
            font.setBold(hop.hop_num in (0, display[-1].hop_num))
            p.setFont(font)
            label = "PC" if hop.hop_num == 0 else str(hop.hop_num)
            if hop is display[-1] and hop.hop_num != 0:
                label = f"{hop.hop_num}"
            p.drawText(x - 14, cy - r - 14, 28, 12, Qt.AlignmentFlag.AlignHCenter, label)

            # mini RTT under
            p.setFont(QFont("Segoe UI", 7))
            p.setPen(QColor(MUTED))
            if hop.state == "probing":
                sub = "..."
            elif hop.timed_out:
                sub = "to"
            elif hop.avg_rtt is not None:
                sub = f"{hop.avg_rtt:.0f}"
            else:
                sub = ""
            p.drawText(x - 16, cy + r + 2, 32, 12, Qt.AlignmentFlag.AlignHCenter, sub)

            self._hit.append((hop.hop_num, x - 14, x + 14))

        # end captions
        if display:
            p.setFont(QFont("Segoe UI", 8, QFont.Weight.DemiBold))
            p.setPen(QColor(EMERALD))
            p.drawText(8, 14, 40, 14, Qt.AlignmentFlag.AlignLeft, "PC")
            last = display[-1]
            dest = "DST"
            if last.role == "public" or (last.ip and last.state != "probing"):
                dest = "DST"
            p.setPen(QColor(CORAL if last.timed_out else EMERALD))
            p.drawText(w - 48, 14, 40, 14, Qt.AlignmentFlag.AlignRight, dest)

        p.end()

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        hop_num = self._hop_at(event.position().x())
        if hop_num is not None:
            self.select_hop_num(hop_num)

    def _hop_at(self, x: float) -> Optional[int]:
        for hop_num, x0, x1 in self._hit:
            if x0 <= x <= x1:
                return hop_num
        # nearest
        if not self._hit:
            return None
        best = min(self._hit, key=lambda t: abs((t[1] + t[2]) / 2 - x))
        mid = (best[1] + best[2]) / 2
        if abs(mid - x) < 24:
            return best[0]
        return None

    def _on_ctx(self, pos):
        from PySide6.QtWidgets import QApplication
        hop_num = self._hop_at(pos.x())
        if hop_num is None:
            return
        self.select_hop_num(hop_num)
        hop = self.selected_hop()
        if not hop or hop.state == "probing":
            return
        global_pos = self.mapToGlobal(pos)
        mods = QApplication.keyboardModifiers()
        if mods & Qt.KeyboardModifier.ShiftModifier:
            self.hop_power_context.emit(hop, global_pos)
        else:
            self.hop_context.emit(hop, global_pos)
