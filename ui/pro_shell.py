"""NetPulse Pro shell: rail, target bar, Command Center, footer, tray."""

from __future__ import annotations

import socket
import subprocess
from typing import List, Optional

from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtGui import QBrush, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QSystemTrayIcon,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.local_net import (
    LocalNetInfo,
    arp_neighbors,
    flush_dns,
    gather_local_net,
    load_json,
    renew_dhcp,
    save_json,
    start_timed_capture,
)
from core.traceroute import TracerouteEngine, TracerouteHop
from ui.command_center import CommandCenterView
from ui.context_verbs import VerbCallbacks
from ui.path_lab import PathLabView
from ui.theme import CORAL, EMERALD, PRO_STYLE


def make_pulse_icon(color: str = EMERALD) -> QIcon:
    pm = QPixmap(32, 32)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QBrush(QColor(color)))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(3, 3, 26, 26)
    p.setPen(QColor("#04140f"))
    p.setBrush(Qt.BrushStyle.NoBrush)
    # simple heartbeat polyline
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QPen, QPolygonF
    pen = QPen(QColor("#04140f"))
    pen.setWidth(2)
    p.setPen(pen)
    pts = [
        QPointF(6, 16), QPointF(11, 16), QPointF(13, 10),
        QPointF(16, 22), QPointF(19, 14), QPointF(22, 16), QPointF(26, 16),
    ]
    for i in range(len(pts) - 1):
        p.drawLine(pts[i], pts[i + 1])
    p.end()
    return QIcon(pm)


class PlaceholderPage(QWidget):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t = QLabel(title)
        t.setStyleSheet("font-size: 16pt; font-weight: 600;")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h = QLabel("Coming soon...")
        h.setObjectName("EmptyHint")
        h.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(t)
        lay.addWidget(h)
        self._title = title
        self._extra = QLabel("")
        self._extra.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._extra)

    def set_playbook_hint(self, name: str):
        self._extra.setText(f"Playbook preselected: {name}")


class ProShell(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NetPulse Pro")
        self.resize(1280, 800)
        self.setMinimumSize(960, 640)
        self.setStyleSheet(PRO_STYLE)
        self.setWindowIcon(make_pulse_icon())

        self._tracer = TracerouteEngine()
        self._net = LocalNetInfo()
        self._recent: List[str] = load_json("recent_targets.json", [])
        self._pins: List[str] = load_json("watch_pins.json", [])
        _ps = load_json("probe_source.json", {"iface": ""})
        self._probe_source: str = _ps.get("iface", "") if isinstance(_ps, dict) else ""
        self._last_error: Optional[str] = None
        self._snapshot_mode = False
        self._prev_hops: List[TracerouteHop] = []

        self._cb = VerbCallbacks()
        self._wire_callbacks()

        self._build_ui()
        self._build_tray()
        self._connect_engine()

        self._footer_timer = QTimer(self)
        self._footer_timer.timeout.connect(self._refresh_footer)
        self._footer_timer.start(5000)
        self._refresh_footer()

    # --- UI ---
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_rail())

        right = QVBoxLayout()
        right.setContentsMargins(10, 10, 10, 8)
        right.setSpacing(8)
        right.addWidget(self._build_top_bar())

        self._stack = QStackedWidget()
        self._cc = CommandCenterView()
        self._cc.set_callbacks(self._cb)
        self._path_lab = PathLabView()
        self._path_lab.set_callbacks(self._cb)
        self._pages = {
            "path": self._cc,
            "path_lab": self._path_lab,
            "link": PlaceholderPage("Link"),
            "dns": PlaceholderPage("DNS"),
            "ports": PlaceholderPage("Ports"),
            "capture": PlaceholderPage("Capture"),
            "playbooks": PlaceholderPage("Playbooks"),
        }
        for key in ("path", "path_lab", "link", "dns", "ports", "capture", "playbooks"):
            self._stack.addWidget(self._pages[key])
        right.addWidget(self._stack, 1)
        right.addWidget(self._build_footer())

        wrap = QWidget()
        wrap.setLayout(right)
        root.addWidget(wrap, 1)

        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage("NetPulse Pro - Command Center")

        self._rail_btns["path"].setChecked(True)
        self._stack.setCurrentWidget(self._cc)

    def _build_rail(self) -> QFrame:
        rail = QFrame()
        rail.setObjectName("Rail")
        rail.setFixedWidth(84)
        lay = QVBoxLayout(rail)
        lay.setContentsMargins(8, 12, 8, 12)
        lay.setSpacing(6)

        brand = QLabel("NP")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand.setStyleSheet(f"color: {EMERALD}; font-weight: 700; font-size: 14pt;")
        lay.addWidget(brand)
        lay.addSpacing(8)

        self._rail_btns = {}
        items = [
            ("path", "Path"),
            ("link", "Link"),
            ("dns", "DNS"),
            ("ports", "Ports"),
            ("capture", "Capture"),
            ("playbooks", "Playbooks"),
        ]
        for key, label in items:
            btn = QToolButton()
            btn.setObjectName("RailBtn")
            btn.setText(label)
            btn.setCheckable(True)
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            btn.setAutoExclusive(True)
            btn.clicked.connect(lambda checked=False, k=key: self._nav(k))
            lay.addWidget(btn)
            self._rail_btns[key] = btn
        lay.addStretch()

        legacy = QToolButton()
        legacy.setObjectName("RailBtn")
        legacy.setText("Classic")
        legacy.setToolTip("Open classic NetPulse tabs")
        legacy.clicked.connect(self._open_classic)
        lay.addWidget(legacy)
        return rail

    def _build_top_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("TopBar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(10)

        self._target = QComboBox()
        self._target.setObjectName("TargetCombo")
        self._target.setEditable(True)
        self._target.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._target.setSizePolicy(
            self._target.sizePolicy().horizontalPolicy(),
            self._target.sizePolicy().verticalPolicy(),
        )
        self._target.setMinimumWidth(320)
        for t in self._recent[:20]:
            self._target.addItem(t)
        self._target.setCurrentText("")
        le = self._target.lineEdit()
        if le:
            le.setPlaceholderText("Hostname or IP - Enter runs")
            le.returnPressed.connect(self._run)
        lay.addWidget(self._target, 1)

        self._run_btn = QPushButton("Run")
        self._run_btn.setObjectName("PrimaryRun")
        self._run_btn.setDefault(True)
        self._run_btn.setAutoDefault(True)
        self._run_btn.clicked.connect(self._run)
        lay.addWidget(self._run_btn)

        self._live_btn = QPushButton("Live")
        self._live_btn.setObjectName("ModeToggle")
        self._live_btn.setCheckable(True)
        self._live_btn.setChecked(True)
        self._snap_btn = QPushButton("Snapshot")
        self._snap_btn.setObjectName("ModeToggle")
        self._snap_btn.setCheckable(True)
        self._snap_btn.setToolTip("Snapshot mode stub - stores last path for Compare")
        self._live_btn.clicked.connect(lambda: self._set_mode(False))
        self._snap_btn.clicked.connect(lambda: self._set_mode(True))
        lay.addWidget(self._live_btn)
        lay.addWidget(self._snap_btn)
        return bar

    def _build_footer(self) -> QFrame:
        foot = QFrame()
        foot.setObjectName("FooterStrip")
        foot.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        foot.customContextMenuRequested.connect(self._on_footer_ctx)
        lay = QHBoxLayout(foot)
        lay.setContentsMargins(14, 8, 14, 8)
        lay.setSpacing(18)

        def pair(label: str):
            box = QHBoxLayout()
            lab = QLabel(label)
            lab.setObjectName("FooterLabel")
            val = QLabel("-")
            val.setObjectName("FooterValue")
            box.addWidget(lab)
            box.addWidget(val)
            w = QWidget()
            w.setLayout(box)
            return w, val

        self._f_iface_w, self._f_iface = pair("IFACE")
        self._f_v4_w, self._f_v4 = pair("IPv4")
        self._f_v6_w, self._f_v6 = pair("IPv6")
        self._f_gw_w, self._f_gw = pair("GW")
        self._f_dns_w, self._f_dns = pair("DNS")
        for w in (self._f_iface_w, self._f_v4_w, self._f_v6_w, self._f_gw_w, self._f_dns_w):
            lay.addWidget(w)
        lay.addStretch()
        return foot

    def _build_tray(self):
        self._tray = QSystemTrayIcon(make_pulse_icon(), self)
        self._tray.setToolTip("NetPulse Pro")
        from PySide6.QtWidgets import QMenu
        menu = QMenu()
        menu.addAction("Show", self.showNormal)
        menu.addAction("Run path", self._run)
        menu.addSeparator()
        menu.addAction("Quit", QApplication.instance().quit)
        self._tray.setContextMenu(menu)
        self._tray.show()

    def _connect_engine(self):
        self._tracer.started.connect(lambda: self._run_btn.setEnabled(False))
        self._tracer.hop_found.connect(self._on_hop)
        self._tracer.finished.connect(self._on_finished)
        self._tracer.error_occurred.connect(self._on_trace_error)

    # --- nav / mode ---
    def _nav(self, key: str):
        if key == "path":
            self._stack.setCurrentWidget(self._cc)
        elif key in self._pages:
            self._stack.setCurrentWidget(self._pages[key])
        if key in self._rail_btns:
            self._rail_btns[key].setChecked(True)

    def _set_mode(self, snapshot: bool):
        self._snapshot_mode = snapshot
        self._live_btn.setChecked(not snapshot)
        self._snap_btn.setChecked(snapshot)
        if snapshot:
            self._status.showMessage("Snapshot mode (stub): last path kept for Compare")
        else:
            self._status.showMessage("Live mode")

    def _open_classic(self):
        from ui.main_window import MainWindow
        self._classic = MainWindow()
        self._classic.show()

    # --- run path ---
    @Slot()
    def _run(self):
        target = self._target.currentText().strip()
        if not target:
            self._status.showMessage("Enter a hostname or IP first.")
            return
        self._remember_target(target)
        self._last_error = None
        self._nav("path")
        self._cc.begin_run(target)
        self._tracer.run(target)

    def _remember_target(self, target: str):
        if target in self._recent:
            self._recent.remove(target)
        self._recent.insert(0, target)
        self._recent = self._recent[:30]
        save_json("recent_targets.json", self._recent)
        if self._target.findText(target) < 0:
            self._target.insertItem(0, target)

    @Slot(object)
    def _on_hop(self, hop: TracerouteHop):
        # cheap reverse DNS if hostname missing
        if hop.ip and not hop.hostname:
            try:
                hop.hostname = socket.gethostbyaddr(hop.ip)[0]
            except Exception:
                pass
        hop.asn = "N/A"  # stub
        self._cc.add_hop(hop)

    @Slot(list)
    def _on_finished(self, hops: List[TracerouteHop]):
        self._run_btn.setEnabled(True)
        if self._snapshot_mode or self._prev_hops is not None:
            # keep previous for compare when starting a new run we already swapped
            pass
        self._cc.finish_run(hops, self._last_error)
        self._path_lab.set_hops(hops)
        self._prev_hops = list(hops)

    @Slot(str)
    def _on_trace_error(self, msg: str):
        self._last_error = msg
        self._status.showMessage(msg)

    # --- footer ---
    def _refresh_footer(self):
        try:
            self._net = gather_local_net()
        except Exception:
            return
        self._f_iface.setText(self._net.iface)
        self._f_v4.setText(self._net.ipv4)
        self._f_v6.setText(self._net.ipv6)
        self._f_gw.setText(self._net.gateway)
        self._f_dns.setText(", ".join(self._net.dns[:3]) if self._net.dns else "-")

    def _on_footer_ctx(self, pos):
        from ui.context_verbs import build_footer_menu, build_footer_power_menu
        mods = QApplication.keyboardModifiers()
        foot = self.sender()
        global_pos = foot.mapToGlobal(pos) if foot else self.mapToGlobal(pos)
        if mods & Qt.KeyboardModifier.ShiftModifier:
            build_footer_power_menu(self, self._cb).exec(global_pos)
        else:
            build_footer_menu(self, self._cb).exec(global_pos)

    # --- verb callbacks ---
    def _wire_callbacks(self):
        cb = self._cb
        cb.copy_text = self._copy
        cb.ping = self._verb_ping
        cb.trace = self._verb_trace
        cb.mtr = self._verb_mtr
        cb.open_path_lab = lambda _h: self._open_path_lab()
        cb.whois_rdns = self._verb_whois
        cb.pin_watch = self._verb_pin
        cb.set_target = self._verb_set_target
        cb.compare_prev = self._verb_compare
        cb.mark_icmp_filtered = lambda h: self._path_lab.mark_filtered(h)
        cb.copy_ipv4 = lambda: self._copy(self._net.ipv4)
        cb.copy_ipv6 = lambda: self._copy(self._net.ipv6)
        cb.copy_gateway = lambda: self._copy(self._net.gateway)
        cb.copy_dns = lambda: self._copy(", ".join(self._net.dns))
        cb.renew_dhcp = self._verb_renew
        cb.flush_dns = self._verb_flush
        cb.show_arp = self._verb_arp
        cb.start_capture = self._verb_capture
        cb.set_probe_source = self._verb_probe
        cb.paste_and_run = self._verb_paste_run
        cb.recent_targets = self._verb_recent
        cb.start_playbook = self._verb_playbook

    def _copy(self, text: str):
        if not text or text == "-":
            self._status.showMessage("Nothing to copy.")
            return
        QApplication.clipboard().setText(text)
        self._status.showMessage(f"Copied: {text[:80]}")

    def _verb_ping(self, target: str):
        if not target:
            return
        try:
            subprocess.Popen(
                ["ping", target],
                creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
            )
            self._status.showMessage(f"Ping started: {target}")
        except Exception as e:
            QMessageBox.warning(self, "Ping", str(e))

    def _verb_trace(self, target: str):
        if not target:
            return
        self._target.setCurrentText(target)
        self._run()

    def _verb_mtr(self, target: str):
        # minimal continuous ping console
        if not target:
            return
        try:
            subprocess.Popen(
                ["ping", "-t", target],
                creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
            )
            self._status.showMessage(f"MTR-continuous (ping -t): {target}")
            self._open_path_lab()
        except Exception as e:
            QMessageBox.warning(self, "MTR", str(e))

    def _open_path_lab(self):
        self._path_lab.set_hops(self._cc.hops() or self._prev_hops)
        self._stack.setCurrentWidget(self._path_lab)
        # path lab is under Path conceptually
        if "path" in self._rail_btns:
            self._rail_btns["path"].setChecked(True)

    def _verb_whois(self, target: str):
        if not target:
            return
        lines = []
        try:
            if self._looks_ip(target):
                try:
                    host = socket.gethostbyaddr(target)[0]
                    lines.append(f"Reverse DNS: {host}")
                except Exception as e:
                    lines.append(f"Reverse DNS: {e}")
            else:
                try:
                    ip = socket.gethostbyname(target)
                    lines.append(f"A: {ip}")
                    try:
                        lines.append(f"Reverse: {socket.gethostbyaddr(ip)[0]}")
                    except Exception:
                        pass
                except Exception as e:
                    lines.append(str(e))
            try:
                import whois
                w = whois.whois(target if not self._looks_ip(target) else (lines[0].split()[-1] if lines else target))
                lines.append(f"Registrar: {getattr(w, 'registrar', None)}")
                lines.append(f"Org: {getattr(w, 'org', None)}")
            except Exception as e:
                lines.append(f"WHOIS: {e}")
        except Exception as e:
            lines.append(str(e))
        QMessageBox.information(self, "Whois / reverse DNS", "\n".join(lines) or "No data")

    @staticmethod
    def _looks_ip(s: str) -> bool:
        parts = s.split(".")
        return len(parts) == 4 and all(p.isdigit() for p in parts)

    def _verb_pin(self, target: str):
        if not target:
            return
        if target not in self._pins:
            self._pins.insert(0, target)
            save_json("watch_pins.json", self._pins)
        self._status.showMessage(f"Pinned watch target: {target}")

    def _verb_set_target(self, target: str):
        if target:
            self._target.setCurrentText(target)
            self._status.showMessage(f"Target set to {target}")

    def _verb_compare(self, hop: TracerouteHop):
        if not self._prev_hops:
            QMessageBox.information(self, "Compare", "No previous run to compare yet.")
            return
        match = next((h for h in self._prev_hops if h.hop_num == hop.hop_num), None)
        if not match:
            QMessageBox.information(self, "Compare", f"No hop {hop.hop_num} in previous run.")
            return
        msg = (
            f"Hop {hop.hop_num}\n"
            f"Current: {hop.avg_rtt} ms ({hop.ip})\n"
            f"Previous: {match.avg_rtt} ms ({match.ip})"
        )
        QMessageBox.information(self, "Compare to previous run", msg)

    def _verb_renew(self):
        ok, msg = renew_dhcp()
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Renew DHCP", msg)
        self._refresh_footer()

    def _verb_flush(self):
        ok, msg = flush_dns()
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Flush DNS", msg)

    def _verb_arp(self):
        rows = arp_neighbors()
        dlg = QDialog(self)
        dlg.setWindowTitle("ARP / neighbors")
        dlg.resize(520, 360)
        lay = QVBoxLayout(dlg)
        table = QTableWidget(len(rows), 3)
        table.setHorizontalHeaderLabels(["IP", "MAC", "Type"])
        for i, (ip, mac, typ) in enumerate(rows):
            table.setItem(i, 0, QTableWidgetItem(ip))
            table.setItem(i, 1, QTableWidgetItem(mac))
            table.setItem(i, 2, QTableWidgetItem(typ))
        lay.addWidget(table)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btns.accepted.connect(dlg.accept)
        lay.addWidget(btns)
        dlg.exec()

    def _verb_capture(self):
        ok, msg = start_timed_capture(30)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Timed capture", msg)

    def _verb_probe(self):
        self._probe_source = self._net.iface
        save_json("probe_source.json", {"iface": self._probe_source})
        self._status.showMessage(f"Default probe source: {self._probe_source}")

    def _verb_paste_run(self):
        text = QApplication.clipboard().text().strip().split()[0] if QApplication.clipboard().text().strip() else ""
        if not text:
            self._status.showMessage("Clipboard empty.")
            return
        self._target.setCurrentText(text)
        self._run()

    def _verb_recent(self):
        if not self._recent:
            QMessageBox.information(self, "Recent", "No recent targets yet.")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Recent targets")
        lay = QVBoxLayout(dlg)
        from PySide6.QtWidgets import QListWidget
        lw = QListWidget()
        lw.addItems(self._recent)
        lay.addWidget(lw)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        if dlg.exec() and lw.currentItem():
            self._target.setCurrentText(lw.currentItem().text())
            self._run()

    def _verb_playbook(self, name: str):
        page = self._pages["playbooks"]
        if isinstance(page, PlaceholderPage):
            page.set_playbook_hint(name)
        self._nav("playbooks")
        self._status.showMessage(f"Playbook: {name} (placeholder)")
