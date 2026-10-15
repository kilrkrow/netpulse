"""Instrument widgets: VFD meter, phosphor history graph, readout cell. All painted with QPainter.

Conventions: 1 px traces, square corners, a dense dim grid, source-colored lines, VFD segments whose
gap is about one cell wide, live readouts around 16 pt in a monospace face.
"""

from __future__ import annotations

import math
import time
from typing import List, Optional, Sequence, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from ui.rc import theme


def nice_ceiling(v: float) -> float:
    """Round a value up to a tidy axis maximum (10, 20, 50, 100, 200, 500 ...)."""
    if v <= 10:
        return 10.0
    mag = 10 ** math.floor(math.log10(v))
    for m in (1, 2, 5, 10):
        if v <= m * mag:
            return float(m * mag)
    return float(10 * mag)


def log_fraction(ms: Optional[float], lo: float = 1.0, hi: float = 500.0) -> float:
    if ms is None:
        return 0.0
    ms = max(lo, min(hi, ms))
    return math.log10(ms / lo) / math.log10(hi / lo)


def ascii_elide(text: str, fm, width: int) -> str:
    """Shorten text to fit, ending in three ASCII dots (Qt's own elision uses a Unicode ellipsis)."""
    if fm.horizontalAdvance(text) <= width:
        return text
    dots = "..."
    while text and fm.horizontalAdvance(text + dots) > width:
        text = text[:-1]
    return (text + dots) if text else ""


def harden_text(root) -> None:
    """Qt shortens clipped text with a Unicode ellipsis; clip instead so only ASCII ever shows."""
    from PySide6.QtWidgets import QAbstractItemView, QTabBar
    for w in root.findChildren(QAbstractItemView):
        w.setTextElideMode(Qt.TextElideMode.ElideNone)
    for w in root.findChildren(QTabBar):
        w.setElideMode(Qt.TextElideMode.ElideNone)


def paint_vfd(p: QPainter, x: float, y: float, w: float, h: float, value: Optional[float], color: str,
              cell: int = 5) -> None:
    """Draw one VFD run in the given box. Cell gap equals the cell width. None = unknown (nothing lit)."""
    step = cell * 2
    n = max(1, int((w + cell) // step))
    lit = 0 if value is None else int(round(max(0.0, min(1.0, value)) * n))
    if value is not None and value > 0 and lit == 0:
        lit = 1                                     # "small" must never read as "none"
    x0 = x + (w - (n * step - cell)) / 2.0
    base = QColor(color)
    for i in range(n):
        cx = x0 + i * step
        r = QRectF(cx, y, cell, h)
        if i < lit:
            glow = QColor(base)
            glow.setAlphaF(0.22)
            p.fillRect(r.adjusted(-1, -1, 1, 1), glow)
            p.fillRect(r, base)
            p.fillRect(QRectF(cx + cell / 2.0 - 0.5, y + 1, 1, max(1.0, h - 2)), QColor(255, 255, 255, 110))
        else:
            dim = QColor(base)
            dim.setAlphaF(0.12)
            p.fillRect(r, dim)


class VfdMeter(QWidget):
    """Horizontal run of discrete cells. Lit cells carry a bright filament and a small bloom; unlit cells
    are the same hue at very low luminance so the full scale stays visible. The gap between cells is about
    one cell wide. A value of None lights nothing (unknown), which is different from 0.0 (idle)."""

    def __init__(self, color: str = theme.OK, cell: int = 5, parent=None):
        super().__init__(parent)
        self._color = color
        self._value: Optional[float] = None
        self._cell = cell
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(12)

    def set_value(self, value: Optional[float], color: Optional[str] = None) -> None:
        if color:
            self._color = color
        self._value = value
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        paint_vfd(p, 0, 1, self.width(), self.height() - 2, self._value, self._color, self._cell)


class ReadoutCell(QWidget):
    """Small caption over a big live readout (about 16 pt monospace)."""

    def __init__(self, caption: str, parent=None):
        super().__init__(parent)
        self._caption = caption
        self._text = "--"
        self._color = theme.TEXT
        self.setMinimumSize(78, 44)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_value(self, text: str, color: str = theme.TEXT) -> None:
        self._text, self._color = text, color
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(theme.PANEL))
        p.setPen(QPen(QColor(theme.BORDER), 1))
        p.drawRect(0, 0, self.width() - 1, self.height() - 1)
        p.setFont(theme.ui_font(7.5))
        p.setPen(QColor(theme.DIM))
        p.drawText(QRectF(7, 3, self.width() - 10, 12), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   self._caption)
        p.setFont(theme.mono(16, True))
        p.setPen(QColor(self._color))
        p.drawText(QRectF(7, 15, self.width() - 10, 26), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   self._text)


Series = Tuple[str, Sequence[Tuple[float, Optional[float]]], bool]   # (color, [(ts, rtt|None)], dashed)


class PhosphorGraph(QWidget):
    """History graph: dense dim grid, 1 px traces with persistence (older samples fade), loss ticks along
    the bottom edge, a marker on the newest point. Each series is colored by its source."""

    def __init__(self, window_s: float = 300.0, compact: bool = False, parent=None):
        super().__init__(parent)
        self.window_s = window_s
        self.compact = compact
        self._series: List[Series] = []
        self._now = time.time()
        self._ymax = 50.0
        self._title = ""
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(34 if compact else 120)

    def set_series(self, series: List[Series], now: Optional[float] = None, title: str = "") -> None:
        self._series = series
        self._now = now if now is not None else time.time()
        self._title = title
        vals = [r for _c, pts, _d in series for t, r in pts if r is not None and t >= self._now - self.window_s]
        if vals:
            vals.sort()
            top = vals[min(len(vals) - 1, int(len(vals) * 0.98))]      # ignore the single worst outlier
            target = nice_ceiling(top * 1.15)
        else:
            target = 10.0
        # ease the scale so it does not jump on every update
        self._ymax = target if target > self._ymax else self._ymax * 0.8 + target * 0.2
        if abs(self._ymax - target) < 0.5:
            self._ymax = target
        self.update()

    # ------------------------------------------------------------------ painting
    def paintEvent(self, _e):
        p = QPainter(self)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor(theme.PANEL if self.compact else "#05070a"))
        left = 0 if self.compact else 40
        bottom_pad = 0 if self.compact else 14
        loss_h = 5 if self.compact else 8
        plot = QRectF(left, 2, w - left - 3, h - 4 - bottom_pad)
        # grid
        gx = 6 if self.compact else 10
        gy = 2 if self.compact else 5
        p.setPen(QPen(QColor(theme.GRID), 1))
        for i in range(gx + 1):
            x = round(plot.left() + plot.width() * i / gx) + 0.5
            p.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
        for j in range(gy + 1):
            y = round(plot.top() + plot.height() * j / gy) + 0.5
            p.setPen(QPen(QColor(theme.GRID_MAJOR if j in (0, gy) else theme.GRID), 1))
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
        if not self.compact:
            p.setFont(theme.mono(8))
            p.setPen(QColor(theme.DIM))
            for j in range(gy + 1):
                val = self._ymax * (gy - j) / gy
                y = plot.top() + plot.height() * j / gy
                p.drawText(QRectF(0, y - 7, left - 5, 14), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                           f"{val:.0f}")
            p.drawText(QRectF(plot.left(), h - 14, 80, 14), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       f"-{int(self.window_s // 60)} min" if self.window_s >= 120 else f"-{int(self.window_s)} s")
            p.drawText(QRectF(plot.right() - 60, h - 14, 60, 14),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "now")
            if self._title:
                p.setFont(theme.ui_font(8))
                p.drawText(QRectF(plot.left() + 6, plot.top() + 2, plot.width() - 12, 14),
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._title)
        t0 = self._now - self.window_s
        sx = plot.width() / self.window_s
        sy = (plot.height() - loss_h - 2) / max(self._ymax, 1.0)
        yb = plot.bottom() - loss_h - 1

        def px(t):
            return plot.left() + (t - t0) * sx

        def py(r):
            return yb - min(r, self._ymax) * sy

        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        for color, pts, dashed in self._series:
            base = QColor(color)
            # loss ticks first (behind the trace)
            tick = QColor(theme.FAIL)
            tick.setAlphaF(0.75)
            p.setPen(QPen(tick, 1))
            for t, r in pts:
                if r is None and t >= t0:
                    x = round(px(t)) + 0.5
                    p.drawLine(QPointF(x, plot.bottom() - loss_h), QPointF(x, plot.bottom()))
            # trace, in chunks so older samples can fade (phosphor persistence)
            path = [(px(t), py(r), t) for t, r in pts if r is not None and t >= t0]
            if len(path) < 2:
                if path:
                    p.fillRect(QRectF(path[0][0] - 1, path[0][1] - 1, 3, 3), base)
                continue
            chunks = 14
            n = len(path)
            size = max(2, n // chunks + 1)
            for k in range(0, n - 1, size):
                seg = path[k:k + size + 1]
                age = k / max(1, n - 1)                  # 0 = oldest, 1 = newest
                col = QColor(base)
                col.setAlphaF(0.30 + 0.70 * age)
                pen = QPen(col, 1)
                if dashed:
                    pen.setStyle(Qt.PenStyle.DashLine)
                p.setPen(pen)
                for (x1, y1, ta), (x2, y2, tb) in zip(seg, seg[1:]):
                    if tb - ta > 4.5:               # a long silence is a break in the line, not a slope
                        continue
                    p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
            x, y, _t = path[-1]
            p.fillRect(QRectF(x - 2, y - 2, 5, 5), QColor(base).lighter(130))
        p.setPen(QPen(QColor(theme.BORDER), 1))
        p.drawRect(QRectF(plot.left() + 0.5, plot.top() + 0.5, plot.width() - 1, plot.height() - 1))
