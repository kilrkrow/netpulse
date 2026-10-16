"""The verdict banner: status block, plain-English headline and explanation, evidence listed beneath."""

from __future__ import annotations

import html
import time
from typing import Optional

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QSizePolicy, QTextBrowser, QVBoxLayout, QWidget)

from core.rc.model import KIND_DEGRADED, KIND_OUTAGE, Verdict
from core.rc.outages import fmt_duration, fmt_time
from ui.rc import theme

STATUS_TAG = {"ok": "OK", "info": "--", "warn": "!!", "fail": "XX"}


class StatusBlock(QWidget):
    """A square status lamp: two-letter glyph in a glowing 1px frame."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.kind = "measuring"
        self.setFixedSize(76, 76)

    def set_kind(self, kind: str) -> None:
        self.kind = kind
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        col = QColor(theme.KIND_COLORS.get(self.kind, theme.UNKNOWN))
        glow = QColor(col)
        glow.setAlphaF(0.10)
        p.fillRect(self.rect(), glow)
        p.setPen(QPen(col, 1))
        p.drawRect(0, 0, self.width() - 1, self.height() - 1)
        p.drawRect(4, 4, self.width() - 9, self.height() - 9)
        p.setFont(theme.mono(24, True))
        p.setPen(col)
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, theme.KIND_GLYPH.get(self.kind, "??"))


class VerdictPanel(QWidget):
    copy_report = Signal()
    open_settings = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._last_html = ""
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(14)
        self.block = StatusBlock()
        root.addWidget(self.block, 0, Qt.AlignmentFlag.AlignTop)

        mid = QVBoxLayout()
        mid.setSpacing(4)
        self.headline = QLabel("Starting...")
        self.headline.setFont(theme.ui_font(17, True))
        self.headline.setWordWrap(True)
        self.explain = QLabel("")
        self.explain.setFont(theme.ui_font(10.5))
        self.explain.setWordWrap(True)
        self.explain.setStyleSheet(f"color: {theme.TEXT};")
        self.meta = QLabel("")
        self.meta.setFont(theme.mono(8.5))
        self.meta.setStyleSheet(f"color: {theme.DIM};")
        mid.addWidget(self.headline)
        mid.addWidget(self.explain)
        mid.addWidget(self.meta)
        self.evidence = QTextBrowser()
        self.evidence.setFrameShape(QTextBrowser.Shape.NoFrame)
        self.evidence.setStyleSheet(f"QTextBrowser {{ background: {theme.PANEL_HI}; border: 1px solid {theme.BORDER}; }}")
        self.evidence.setFixedHeight(124)
        self.evidence.setOpenLinks(False)
        mid.addWidget(self.evidence)
        root.addLayout(mid, 1)

        side = QVBoxLayout()
        self.copy_btn = QPushButton("Copy report")
        self.copy_btn.setObjectName("primary")
        self.copy_btn.setToolTip("Copy a plain-text report of this verdict, the path and recent outages to the clipboard")
        self.copy_btn.clicked.connect(self.copy_report)
        self.settings_btn = QPushButton("Settings")
        self.settings_btn.clicked.connect(self.open_settings)
        side.addWidget(self.copy_btn)
        side.addWidget(self.settings_btn)
        side.addStretch()
        root.addLayout(side)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(theme.PANEL))
        p.setPen(QPen(QColor(theme.BORDER), 1))
        p.drawRect(0, 0, self.width() - 1, self.height() - 1)

    def show_verdict(self, v: Verdict, now: Optional[float] = None) -> None:
        now = now if now is not None else time.time()
        col = theme.KIND_COLORS.get(v.kind, theme.UNKNOWN)
        self.block.set_kind(v.kind)
        self.headline.setText(v.headline)
        self.headline.setStyleSheet(f"color: {col};")
        self.explain.setText(v.explanation)
        bits = [f"CONFIDENCE {v.confidence.upper()}"]
        if v.kind in (KIND_OUTAGE, KIND_DEGRADED) and v.since_ts:
            bits.append(f"SINCE {fmt_time(v.since_ts)[11:]} ({fmt_duration(max(0.0, now - v.since_ts))})")
        bits.append("BASED ON THIS PC'S OWN ICMP PROBES")
        self.meta.setText("   |   ".join(bits))
        rows = []
        for e in v.evidence:
            c = theme.STATUS_COLORS.get(e.status, theme.DIM)
            tag = STATUS_TAG.get(e.status, "--")
            rows.append(f'<tr><td style="color:{c}; font-family:Consolas; padding-right:8px; white-space:pre;">[{tag}]</td>'
                        f'<td style="color:{theme.TEXT if e.status != "ok" else theme.DIM};">{html.escape(e.text)}</td></tr>')
        doc = ('<table cellspacing="0" cellpadding="1" style="font-size:9pt;">' + "".join(rows) + "</table>"
               if rows else '<span style="color:#8aa2ad;">No evidence yet.</span>')
        if doc != self._last_html:
            sb = self.evidence.verticalScrollBar()
            pos = sb.value()
            self.evidence.setHtml(doc)
            sb.setValue(pos)
            self._last_html = doc
