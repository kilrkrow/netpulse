"""Small QPainter-drawn icons in the instrument style (1px traces, mitered joins, no fills).

Every icon is drawn at several sizes with a 4x supersampled pixmap, in the text color at rest, cyan when hot and dim
when disabled, so they stay crisp on any DPI."""

from __future__ import annotations

import math
from typing import Callable

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

from ui.rc import theme

_SIZES = (16, 20, 24, 32, 48)


def _gear_path(size: float, teeth: int = 8) -> QPainterPath:
    c = size / 2.0
    r_tip, r_root = size * 0.47, size * 0.345
    pts = []
    step = 2 * math.pi / teeth
    for i in range(teeth):
        a = i * step - math.pi / 2
        for ang, rad in ((a - step * 0.30, r_root), (a - step * 0.17, r_tip), (a + step * 0.17, r_tip),
                         (a + step * 0.30, r_root)):
            pts.append(QPointF(c + rad * math.cos(ang), c + rad * math.sin(ang)))
    path = QPainterPath()
    path.moveTo(pts[0])
    for p in pts[1:]:
        path.lineTo(p)
    path.closeSubpath()
    path.addEllipse(QPointF(c, c), size * 0.15, size * 0.15)
    return path


def _draw_gear(p: QPainter, s: float) -> None:
    p.drawPath(_gear_path(s))


def _draw_download(p: QPainter, s: float) -> None:
    """A tray (open box) with a down arrow."""
    def pt(x, y):
        return QPointF(x * s, y * s)
    tray = QPainterPath()
    tray.moveTo(pt(0.16, 0.60))
    tray.lineTo(pt(0.16, 0.86))
    tray.lineTo(pt(0.84, 0.86))
    tray.lineTo(pt(0.84, 0.60))
    p.drawPath(tray)
    arrow = QPainterPath()
    arrow.moveTo(pt(0.5, 0.10))
    arrow.lineTo(pt(0.5, 0.66))
    arrow.moveTo(pt(0.28, 0.44))
    arrow.lineTo(pt(0.5, 0.68))
    arrow.lineTo(pt(0.72, 0.44))
    p.drawPath(arrow)


def _draw_share(p: QPainter, s: float) -> None:
    """The universal share glyph: three nodes joined at the left one."""
    def pt(x, y):
        return QPointF(x * s, y * s)
    r = s * 0.115
    a, b, c = pt(0.78, 0.20), pt(0.22, 0.50), pt(0.78, 0.80)
    for n in (a, b, c):
        p.drawEllipse(n, r, r)
    for n in (a, c):
        d = QPointF(n.x() - b.x(), n.y() - b.y())
        ln = math.hypot(d.x(), d.y())
        ux, uy = d.x() / ln, d.y() / ln
        p.drawLine(QPointF(b.x() + ux * r, b.y() + uy * r), QPointF(n.x() - ux * r, n.y() - uy * r))


def _pixmap(draw: Callable, size: int, color: str, scale: int = 4) -> QPixmap:
    pm = QPixmap(size * scale, size * scale)
    pm.setDevicePixelRatio(scale)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(color), max(1.0, size / 14.0))
    pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
    pen.setCapStyle(Qt.PenCapStyle.FlatCap)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    draw(p, float(size))
    p.end()
    return pm


def _icon(draw: Callable) -> QIcon:
    ic = QIcon()
    for s in _SIZES:
        ic.addPixmap(_pixmap(draw, s, theme.TEXT), QIcon.Mode.Normal)
        ic.addPixmap(_pixmap(draw, s, theme.CYAN), QIcon.Mode.Active)
        ic.addPixmap(_pixmap(draw, s, theme.DIMMER), QIcon.Mode.Disabled)
    return ic


def gear_icon() -> QIcon:
    return _icon(_draw_gear)


def download_icon() -> QIcon:
    return _icon(_draw_download)


def share_icon() -> QIcon:
    return _icon(_draw_share)