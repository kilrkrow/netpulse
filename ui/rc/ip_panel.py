"""IP research panel: ASN, owner, country, reverse DNS and RDAP registration for any public address."""

from __future__ import annotations

import threading
from typing import Callable, Optional

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
                               QSizePolicy, QVBoxLayout, QWidget)

from core.rc.ipclass import skip_reason
from core.rc.ipinfo import IpReport
from ui.rc import theme

NOTICE = ("Lookups send the IP address to Team Cymru (DNS), the registry's RDAP server and your DNS resolver. "
          "Private, LAN, carrier-grade NAT, link-local and documentation addresses are never sent.")


class _Worker(QObject):
    done = Signal(object)


class IpResearchPanel(QWidget):
    identified = Signal(str)

    def __init__(self, controller, settings_store, parent=None):
        super().__init__(parent)
        self.ctl = controller
        self.settings = settings_store
        self._worker = _Worker()
        self._worker.done.connect(self._show_report)
        self._current = ""
        self._pending: Optional[str] = None
        self.setMinimumWidth(360)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(6)
        title = QLabel("IP RESEARCH")
        title.setFont(theme.mono(9, True))
        title.setStyleSheet(f"color: {theme.CYAN};")
        root.addWidget(title)

        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Enter an IP address")
        self.input.returnPressed.connect(self._on_lookup)          # Enter runs the primary action
        self.go = QPushButton("Look up")
        self.go.setObjectName("primary")
        self.go.clicked.connect(self._on_lookup)
        row.addWidget(self.input, 1)
        row.addWidget(self.go)
        root.addLayout(row)

        self.notice = QLabel(NOTICE)
        self.notice.setWordWrap(True)
        self.notice.setStyleSheet(f"color: {theme.WARN}; font-size: 8.5pt;")
        self.allow = QPushButton("Allow lookups")
        self.allow.clicked.connect(self._allow)
        root.addWidget(self.notice)
        root.addWidget(self.allow, 0, Qt.AlignmentFlag.AlignLeft)

        self.status = QLabel("Click a hop or enter an address.")
        self.status.setWordWrap(True)
        self.status.setStyleSheet(f"color: {theme.DIM};")
        root.addWidget(self.status)

        holder = QWidget()
        self.grid = QGridLayout(holder)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(10)
        self.grid.setVerticalSpacing(2)
        self._keys = ["ADDRESS", "ASN / OWNER", "PREFIX", "REGISTRY", "REVERSE DNS", "RDAP NAME", "RDAP ORG",
                      "RDAP RANGE", "DATES"]
        self._vals = {}
        for i, k in enumerate(self._keys):
            kl = QLabel(k)
            kl.setFont(theme.mono(7.5))
            kl.setStyleSheet(f"color: {theme.DIM};")
            kl.setMinimumWidth(86)
            vl = QLabel("")
            vl.setFont(theme.mono(9.5))
            vl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            vl.setWordWrap(True)
            self.grid.addWidget(kl, i, 0, Qt.AlignmentFlag.AlignTop)
            self.grid.addWidget(vl, i, 1)
            self._vals[k] = (kl, vl)
        self.grid.setColumnStretch(1, 1)
        self.grid.setRowStretch(len(self._keys), 1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(holder)
        holder.setStyleSheet(f"background: {theme.PANEL};")
        root.addWidget(scroll, 1)
        self.errors = QLabel("")
        self.errors.setWordWrap(True)
        self.errors.setStyleSheet(f"color: {theme.WARN}; font-size: 8.5pt;")
        root.addWidget(self.errors)
        self.footer = QLabel("Lookups send the address to Team Cymru, RDAP servers and your DNS resolver. "
                             "Registry country is where a block was registered, not where a device is.")
        self.footer.setWordWrap(True)
        self.footer.setStyleSheet(f"color: {theme.DIMMER}; font-size: 8pt;")
        root.addWidget(self.footer)
        self._clear_rows()
        self._refresh_notice()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(theme.PANEL))
        p.setPen(QPen(QColor(theme.BORDER), 1))
        p.drawRect(0, 0, self.width() - 1, self.height() - 1)

    # ------------------------------------------------------------------ consent
    def _refresh_notice(self) -> None:
        allowed = self.settings.value.lookups_allowed
        self.allow.setVisible(not allowed)
        self.notice.setVisible(not allowed)          # once allowed, the dim footer carries the same notice
        self.footer.setVisible(allowed)

    def _allow(self) -> None:
        self.settings.value.lookups_allowed = True
        self.settings.value.lookups_notice_seen = True
        self.settings.save()
        self._refresh_notice()
        if self._pending:
            ip, self._pending = self._pending, None
            self.lookup(ip)

    # ------------------------------------------------------------------ actions
    def _on_lookup(self) -> None:
        self.lookup(self.input.text().strip())

    def lookup(self, ip: str) -> None:
        """Entry point used by the hop cells and the context menu."""
        if not ip:
            return
        self.input.setText(ip)
        self._current = ip
        reason = skip_reason(ip)
        if reason:                                      # never leaves the machine
            self._clear_rows()
            self._set("ADDRESS", ip)
            self.status.setText(reason)
            self.status.setStyleSheet(f"color: {theme.WARN};")
            self.errors.setText("")
            return
        if not self.settings.value.lookups_allowed:
            self._pending = ip
            self._clear_rows()
            self._set("ADDRESS", ip)
            self.status.setText("Press Allow lookups to continue. Nothing has been sent yet.")
            self.status.setStyleSheet(f"color: {theme.WARN};")
            return
        self.status.setText(f"Looking up {ip} ...")
        self.status.setStyleSheet(f"color: {theme.DIM};")
        self.go.setEnabled(False)

        def work():
            try:
                rep = self.ctl.lookup_ip(ip)
            except Exception as exc:
                rep = IpReport(ip=ip, errors={"lookup": f"Lookup failed ({exc.__class__.__name__})."})
            self._worker.done.emit(rep)

        threading.Thread(target=work, name="np-ipresearch", daemon=True).start()

    # ------------------------------------------------------------------ display
    def _clear_rows(self) -> None:
        for k in self._keys:
            self._set(k, "")

    def _set(self, key: str, value: str) -> None:
        kl, vl = self._vals[key]
        vl.setText(value)
        kl.setVisible(bool(value))
        vl.setVisible(bool(value))

    def _show_report(self, rep: IpReport) -> None:
        self.go.setEnabled(True)
        if rep.ip != self._current:
            return
        self._clear_rows()
        self._set("ADDRESS", rep.ip)
        if rep.skipped:
            self.status.setText(rep.skipped)
            self.status.setStyleSheet(f"color: {theme.WARN};")
            return
        r = rep.rdap or {}
        self._set("ASN / OWNER", (f"AS{rep.asn}  " if rep.asn else "") + (rep.asn_name or ""))
        self._set("PREFIX", rep.prefix)
        reg = " / ".join(x for x in ((rep.country or "").upper(), (rep.registry or "").upper()) if x)
        self._set("REGISTRY", reg)
        self._set("REVERSE DNS", rep.rdns or ("(none)" if rep.rdns_checked else ""))
        self._set("RDAP NAME", str(r.get("name", "")))
        self._set("RDAP ORG", str(r.get("org", "")))
        rng = f"{r['startAddress']} - {r['endAddress']}" if r.get("startAddress") else str(r.get("cidr", ""))
        self._set("RDAP RANGE", rng)
        ev = r.get("events", {}) or {}
        dates = []
        if ev.get("registration"):
            dates.append("registered " + str(ev["registration"]))
        if ev.get("last changed"):
            dates.append("changed " + str(ev["last changed"]))
        self._set("DATES", ", ".join(dates))
        cached = [k for k, v in rep.cached.items() if v]
        if rep.has_data:
            self.status.setText("Results" + (f" (cached: {', '.join(cached)})" if cached else "") + ".")
            self.status.setStyleSheet(f"color: {theme.OK};")
        else:
            self.status.setText("No data came back.")
            self.status.setStyleSheet(f"color: {theme.WARN};")
        self.errors.setText("  ".join(rep.errors.values()))
        if rep.asn:
            self.identified.emit(rep.ip)
