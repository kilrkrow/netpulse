"""The hero: the path from this PC to the target as a row of instrument cells under a segment ribbon."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QScrollArea, QSizePolicy, QWidget

from core.rc.model import (KIND_DEGRADED, KIND_OUTAGE, SEG_PC, SEGMENT_NAMES, HopView, PathSnapshot, Verdict)
from core.rc.verdict import (STATE_DOWN, STATE_LOSSY, STATE_MEASURING, STATE_OK, STATE_SILENT, VerdictConfig,
                             assess_hop)
from ui.rc import theme
from ui.rc.widgets import PhosphorGraph, ascii_elide, log_fraction, paint_vfd

CELL_H = 196
RIBBON_H = 22
GAP = 12
MARK_H = 18

STATE_TEXT = {STATE_OK: "UP", STATE_LOSSY: "LOSS", STATE_DOWN: "DOWN", STATE_SILENT: "NO INFO",
              STATE_MEASURING: "WAIT"}


@dataclass
class CellModel:
    hop: HopView
    state: str = STATE_MEASURING
    slow: bool = False
    last_rtt: Optional[float] = None
    avg_rtt: Optional[float] = None
    loss: float = 0.0
    jitter: Optional[float] = None

    @property
    def seg(self) -> str:
        """Segment shown for this cell: a hop that never gave an address cannot honestly be placed."""
        h = self.hop
        if h.ttl >= 1 and not h.ip and not h.is_target:
            return "unmapped"
        return h.segment

    @property
    def color(self) -> str:
        if self.state == STATE_DOWN:
            return theme.FAIL
        if self.state == STATE_LOSSY or self.slow:
            return theme.WARN
        if self.state == STATE_SILENT:
            return theme.DIMMER
        if self.state == STATE_MEASURING:
            return theme.INFO
        return theme.OK

    @property
    def badge(self) -> str:
        if self.state == STATE_OK and self.slow:
            return "SLOW"
        return STATE_TEXT.get(self.state, "")


def build_models(snap: PathSnapshot, cfg: Optional[VerdictConfig] = None) -> List[CellModel]:
    cfg = cfg or VerdictConfig()
    out: List[CellModel] = []
    for h in snap.hops:
        if h.ttl == 0:
            out.append(CellModel(h, STATE_OK))
            continue
        a = assess_hop(h, cfg)
        out.append(CellModel(h, a.state, a.elevated and a.state == STATE_OK, a.stats.last_rtt, a.stats.avg_rtt,
                             a.stats.loss_pct, a.stats.jitter))
    return out


class HopCell(QWidget):
    clicked = Signal(int)
    context = Signal(int, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.model: Optional[CellModel] = None
        self.selected = False
        self._series_now = 0.0
        self.spark = PhosphorGraph(window_s=60.0, compact=True, parent=self)
        self.spark.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setMinimumWidth(136)
        self.setFixedHeight(CELL_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_model(self, m: CellModel, now: float, selected: bool) -> None:
        self.model, self.selected = m, selected
        self._series_now = now
        if m.hop.ttl >= 1:
            pts = [(s.ts, s.rtt_ms if s.ok else None) for s in m.hop.samples[-90:]]
            self.spark.set_series([(theme.SEG_COLORS.get(m.hop.segment, theme.OK), pts, False)], now)
            self.spark.show()
        else:
            self.spark.hide()
        self.update()

    def resizeEvent(self, _e):
        self.spark.setGeometry(8, self.height() - 46, self.width() - 16, 38)

    def mousePressEvent(self, e):
        if self.model is None:
            return
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.model.hop.ttl)
        elif e.button() == Qt.MouseButton.RightButton:
            self.context.emit(self.model.hop.ttl, e.globalPosition().toPoint())

    def paintEvent(self, _e):
        m = self.model
        p = QPainter(self)
        w, h = self.width(), self.height()
        if m is None:
            return
        hop = m.hop
        seg_color = theme.SEG_COLORS.get(m.seg, theme.DIMMER)
        down = m.state == STATE_DOWN
        bg = QColor("#150a0d") if down else QColor(theme.PANEL)
        p.fillRect(self.rect(), bg)
        border = QColor(theme.FAIL) if down else QColor(seg_color)
        border.setAlphaF(1.0 if self.selected else (0.85 if down else 0.45))
        p.setPen(QPen(border, 1))
        p.drawRect(0, 0, w - 1, h - 1)
        if self.selected:
            p.setPen(QPen(QColor(seg_color), 1))
            p.drawRect(2, 2, w - 5, h - 5)
        pad = 9
        # header: hop number left, state badge right
        p.setFont(theme.mono(8.5))
        p.setPen(QColor(theme.DIM))
        head = "THIS PC" if hop.ttl == 0 else (f"HOP {hop.ttl}" + ("  TARGET" if hop.is_target else ""))
        p.drawText(QRectF(pad, 5, w - 2 * pad, 14), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, head)
        if hop.ttl >= 1:
            p.setFont(theme.mono(8.5, True))
            p.setPen(QColor(m.color))
            p.drawText(QRectF(pad, 5, w - 2 * pad, 14), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       m.badge)
        # address
        p.setFont(theme.mono(9))
        fm = QFontMetrics(p.font())
        if hop.ttl == 0:
            addr = hop.ip or "local"
        else:
            addr = hop.ip or "no address"
        p.setPen(QColor(theme.TEXT if hop.ip else theme.DIMMER))
        p.drawText(QRectF(pad, 22, w - 2 * pad, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   ascii_elide(addr, fm, w - 2 * pad))
        if hop.label_source == "override":
            p.setFont(theme.mono(7.5))
            p.setPen(QColor(theme.CYAN))
            p.drawText(QRectF(pad, 22, w - 2 * pad, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       "SET")
        if hop.ttl == 0:
            p.setFont(theme.mono(16, True))
            p.setPen(QColor(seg_color))
            p.drawText(QRectF(pad, 44, w - 2 * pad, 28), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       "SOURCE")
            p.setFont(theme.ui_font(8))
            p.setPen(QColor(theme.DIM))
            p.drawText(QRectF(pad, 76, w - 2 * pad, 70), Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignTop,
                       "Probes start here. Nothing is installed or logged in to.")
            return
        # live latency readout (about 16 pt)
        if m.last_rtt is not None and m.state != STATE_DOWN:
            txt = f"{m.last_rtt:.0f} ms" if m.last_rtt >= 10 else f"{m.last_rtt:.1f} ms"
            rcol = m.color
        elif m.state == STATE_DOWN:
            txt, rcol = "NO REPLY", theme.FAIL
        elif m.state == STATE_SILENT:
            txt, rcol = "-- ms", theme.DIMMER
        else:
            txt, rcol = "-- ms", theme.DIM
        p.setFont(theme.mono(16, True))
        p.setPen(QColor(rcol))
        p.drawText(QRectF(pad, 42, w - 2 * pad, 28), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, txt)
        # latency meter
        frac = None if (m.last_rtt is None or m.state == STATE_DOWN) else log_fraction(m.last_rtt)
        paint_vfd(p, pad, 74, w - 2 * pad, 9, frac, rcol if frac is not None else theme.DIMMER)
        # loss readout and meter
        p.setFont(theme.mono(8))
        p.setPen(QColor(theme.DIM))
        p.drawText(QRectF(pad, 88, 40, 14), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "LOSS")
        lcol = theme.FAIL if m.loss >= 50 else (theme.WARN if m.loss >= 10 else theme.OK)
        if m.state in (STATE_SILENT, STATE_MEASURING):
            lcol = theme.DIMMER
        p.setFont(theme.mono(12, True))
        p.setPen(QColor(lcol))
        have = m.hop.total_sent > 0 and m.state != STATE_SILENT
        p.drawText(QRectF(pad + 38, 86, w - 2 * pad - 38, 18),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, f"{m.loss:.0f}%" if have else "--")
        paint_vfd(p, pad, 106, w - 2 * pad, 9, (min(1.0, m.loss / 50.0) if have else None), lcol)
        # jitter / average
        p.setFont(theme.mono(8))
        p.setPen(QColor(theme.DIM))
        jit = f"{m.jitter:.1f}" if m.jitter is not None else "--"
        avg = f"{m.avg_rtt:.0f}" if m.avg_rtt is not None else "--"
        p.drawText(QRectF(pad, 122, w - 2 * pad, 14), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   f"AVG {avg} ms   JIT {jit}")
        p.drawText(QRectF(pad, 136, w - 2 * pad, 12), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   "last 60 s")


class _Strip(QWidget):
    def __init__(self, view: "PathView"):
        super().__init__()
        self.view = view
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def paintEvent(self, _e):
        self.view.paint_strip(self)


class PathView(QScrollArea):
    hop_selected = Signal(int)
    hop_context = Signal(int, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self._strip = _Strip(self)
        self.setWidget(self._strip)
        self.setFixedHeight(RIBBON_H + 10 + CELL_H + MARK_H + 14)
        self._cells: List[HopCell] = []
        self._models: List[CellModel] = []
        self._verdict: Optional[Verdict] = None
        self._selected_ttl: Optional[int] = None
        self._cw = 140
        self._now = 0.0

    # ------------------------------------------------------------------ data
    def update_data(self, snap: PathSnapshot, verdict: Verdict) -> None:
        self._models = build_models(snap)
        self._verdict = verdict
        self._now = snap.ts
        while len(self._cells) < len(self._models):
            c = HopCell(self._strip)
            c.clicked.connect(self._on_clicked)
            c.context.connect(self.hop_context)
            c.show()
            self._cells.append(c)
        while len(self._cells) > len(self._models):
            self._cells.pop().deleteLater()
        if self._selected_ttl is None and len(self._models) > 1:
            self._selected_ttl = 1
        for c, m in zip(self._cells, self._models):
            c.set_model(m, snap.ts, m.hop.ttl == self._selected_ttl)
        self._layout()
        self._strip.update()

    def selected_ttl(self) -> Optional[int]:
        return self._selected_ttl

    def select(self, ttl: int) -> None:
        self._selected_ttl = ttl
        for c in self._cells:
            c.selected = bool(c.model and c.model.hop.ttl == ttl)
            c.update()

    def _on_clicked(self, ttl: int) -> None:
        self.select(ttl)
        self.hop_selected.emit(ttl)

    # ------------------------------------------------------------------ layout
    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._layout()

    def _layout(self) -> None:
        n = len(self._cells)
        if not n:
            return
        avail = self.viewport().width() - 2
        cw = max(136, int((avail - (n - 1) * GAP) / n))
        self._cw = cw
        total = n * cw + (n - 1) * GAP + 2
        self._strip.resize(max(total, avail), RIBBON_H + 10 + CELL_H + MARK_H + 10)
        y = RIBBON_H + 10
        for i, c in enumerate(self._cells):
            c.setGeometry(1 + i * (cw + GAP), y, cw, CELL_H)

    def _cell_x(self, i: int) -> int:
        return 1 + i * (self._cw + GAP)

    # ------------------------------------------------------------------ painting (ribbon, links, fault mark)
    def paint_strip(self, w: QWidget) -> None:
        p = QPainter(w)
        p.fillRect(w.rect(), QColor(theme.BG))
        if not self._models:
            p.setPen(QColor(theme.DIM))
            p.setFont(theme.ui_font(11))
            p.drawText(w.rect(), Qt.AlignmentFlag.AlignCenter, "Mapping the path...")
            return
        # segment ribbon: contiguous runs of one segment share a bar
        i = 0
        n = len(self._models)
        while i < n:
            seg = self._models[i].seg
            j = i
            while j + 1 < n and self._models[j + 1].seg == seg:
                j += 1
            x1 = self._cell_x(i)
            x2 = self._cell_x(j) + self._cw
            col = QColor(theme.SEG_COLORS.get(seg, theme.DIMMER))
            bar = QColor(col)
            bar.setAlphaF(0.14)
            p.fillRect(QRectF(x1, 0, x2 - x1, RIBBON_H), bar)
            p.setPen(QPen(col, 1))
            p.drawLine(QPointF(x1, 0.5), QPointF(x2, 0.5))
            p.drawLine(QPointF(x1 + 0.5, 0), QPointF(x1 + 0.5, RIBBON_H - 1))
            p.drawLine(QPointF(x2 - 0.5, 0), QPointF(x2 - 0.5, RIBBON_H - 1))
            p.setFont(theme.mono(9, True))
            p.drawText(QRectF(x1, 0, x2 - x1, RIBBON_H), Qt.AlignmentFlag.AlignCenter, SEGMENT_NAMES.get(seg, "UNMAPPED"))
            i = j + 1
        # links between cells, colored by the later hop's state; broken (dashed) when it is down
        yl = RIBBON_H + 10 + 31
        for k in range(1, n):
            a, b = self._models[k - 1], self._models[k]
            x1 = self._cell_x(k - 1) + self._cw
            x2 = self._cell_x(k)
            col = QColor(b.color if b.hop.ttl >= 1 else theme.DIM)
            pen = QPen(col, 1)
            if b.state == STATE_DOWN:
                pen.setStyle(Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawLine(QPointF(x1, yl + 0.5), QPointF(x2, yl + 0.5))
        # fault marker under the cell the verdict points at
        v = self._verdict
        if v and v.kind in (KIND_OUTAGE, KIND_DEGRADED) and v.ttl is not None:
            for k, m in enumerate(self._models):
                if m.hop.ttl == v.ttl:
                    x = self._cell_x(k)
                    col = QColor(theme.FAIL if v.kind == KIND_OUTAGE else theme.WARN)
                    y = RIBBON_H + 10 + CELL_H + 3
                    p.fillRect(QRectF(x, y, self._cw, 3), col)
                    p.setFont(theme.mono(9, True))
                    p.setPen(col)
                    p.drawText(QRectF(x, y + 4, self._cw, 14), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                               "FAULT STARTS HERE" if v.kind == KIND_OUTAGE else "TROUBLE STARTS HERE")
