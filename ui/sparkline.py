"""Mini RTT sparkline for hop cards and intel."""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from ui.theme import CORAL, EMERALD


class Sparkline(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._values: List[float] = []
        self._fail = False
        self.setMinimumHeight(36)
        self.setMaximumHeight(48)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_samples(self, values: List[Optional[float]], fail: bool = False):
        self._values = [float(v) for v in values if v is not None]
        self._fail = fail
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = max(self.width(), 1), max(self.height(), 1)
        color = QColor(CORAL if self._fail else EMERALD)
        if not self._values:
            p.setPen(QPen(QColor(color.red(), color.green(), color.blue(), 80), 1.5))
            p.drawLine(4, h // 2, w - 4, h // 2)
            p.end()
            return
        vals = self._values
        mn, mx = min(vals), max(vals)
        span = max(mx - mn, 1.0)
        pad_x, pad_y = 4, 6
        n = len(vals)
        pts = []
        for i, v in enumerate(vals):
            x = pad_x + (w - 2 * pad_x) * (i / max(n - 1, 1))
            y = pad_y + (h - 2 * pad_y) * (1 - (v - mn) / span)
            pts.append(QPointF(x, y))
        path = QPainterPath(pts[0])
        for pt in pts[1:]:
            path.lineTo(pt)
        fill = QPainterPath(path)
        fill.lineTo(QPointF(pts[-1].x(), h - pad_y))
        fill.lineTo(QPointF(pts[0].x(), h - pad_y))
        fill.closeSubpath()
        p.fillPath(fill, QColor(color.red(), color.green(), color.blue(), 40))
        p.setPen(QPen(color, 2))
        p.drawPath(path)
        p.end()
