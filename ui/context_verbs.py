"""Context-verb matrix builders for NetPulse Pro nouns."""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QWidget

from core.traceroute import TracerouteHop


class VerbCallbacks:
    """Wire these from the shell / command center."""

    def __init__(self):
        self.copy_text: Callable[[str], None] = lambda _t: None
        self.ping: Callable[[str], None] = lambda _t: None
        self.trace: Callable[[str], None] = lambda _t: None
        self.mtr: Callable[[str], None] = lambda _t: None
        self.open_path_lab: Callable[[Optional[TracerouteHop]], None] = lambda _h: None
        self.whois_rdns: Callable[[str], None] = lambda _t: None
        self.pin_watch: Callable[[str], None] = lambda _t: None
        self.set_target: Callable[[str], None] = lambda _t: None
        self.compare_prev: Callable[[TracerouteHop], None] = lambda _h: None
        self.mark_icmp_filtered: Callable[[TracerouteHop], None] = lambda _h: None
        self.copy_ipv4: Callable[[], None] = lambda: None
        self.copy_ipv6: Callable[[], None] = lambda: None
        self.copy_gateway: Callable[[], None] = lambda: None
        self.copy_dns: Callable[[], None] = lambda: None
        self.renew_dhcp: Callable[[], None] = lambda: None
        self.flush_dns: Callable[[], None] = lambda: None
        self.show_arp: Callable[[], None] = lambda: None
        self.start_capture: Callable[[], None] = lambda: None
        self.set_probe_source: Callable[[], None] = lambda: None
        self.paste_and_run: Callable[[], None] = lambda: None
        self.recent_targets: Callable[[], None] = lambda: None
        self.start_playbook: Callable[[str], None] = lambda _t: None


def _hop_target(hop: TracerouteHop) -> str:
    return hop.ip or hop.hostname or ""


def _add(menu: QMenu, text: str, slot, shortcut: str = "") -> QAction:
    act = QAction(text, menu)
    if shortcut:
        act.setShortcutVisibleInContextMenu(True)
        act.setText(f"{text}\t{shortcut}")
    act.triggered.connect(slot)
    menu.addAction(act)
    return act


def build_hop_menu(parent: QWidget, hop: TracerouteHop, cb: VerbCallbacks, *, table: bool = False) -> QMenu:
    menu = QMenu(parent)
    target = _hop_target(hop)
    host = hop.hostname or ""
    asn = getattr(hop, "asn", None) or ""

    _add(menu, "Copy address", lambda: cb.copy_text(hop.ip or target), "Ctrl+C")
    if host:
        _add(menu, "Copy hostname", lambda: cb.copy_text(host))
    if asn:
        _add(menu, "Copy ASN", lambda: cb.copy_text(str(asn)))
    else:
        act = QAction("Copy ASN (N/A)", menu)
        act.setEnabled(False)
        menu.addAction(act)

    menu.addSeparator()
    _add(menu, "Ping", lambda: cb.ping(target), "P")
    _add(menu, "Trace", lambda: cb.trace(target), "T")
    _add(menu, "MTR continuous", lambda: cb.mtr(target), "M")
    _add(menu, "Open in Path lab", lambda: cb.open_path_lab(hop), "L")

    menu.addSeparator()
    _add(menu, "Whois / reverse DNS", lambda: cb.whois_rdns(target))
    _add(menu, "Pin as watch target", lambda: cb.pin_watch(target))

    md = f"| {hop.hop_num} | {hop.hostname or ''} | {hop.ip or ''} | {hop.avg_rtt or ''} |"
    _add(menu, "Copy as Markdown row", lambda: cb.copy_text(md))

    if table:
        menu.addSeparator()
        _add(menu, "Compare to previous run", lambda: cb.compare_prev(hop))
        _add(menu, "Mark ICMP-filtered expected loss", lambda: cb.mark_icmp_filtered(hop))
        menu.addSeparator()
        # destructive-ish at bottom
        _add(menu, "Set as new target", lambda: cb.set_target(target))

    return menu


def build_hop_power_menu(parent: QWidget, hop: TracerouteHop, cb: VerbCallbacks) -> QMenu:
    menu = QMenu(parent)
    target = _hop_target(hop) or "target"
    _add(menu, "Copy: tracert", lambda: cb.copy_text(f"tracert -d {target}"))
    _add(menu, "Copy: pathping", lambda: cb.copy_text(f"pathping -n {target}"))
    _add(menu, "Copy: ping -t", lambda: cb.copy_text(f"ping -t {target}"))
    return menu


def build_footer_menu(parent: QWidget, cb: VerbCallbacks) -> QMenu:
    menu = QMenu(parent)
    _add(menu, "Copy IPv4", cb.copy_ipv4)
    _add(menu, "Copy IPv6", cb.copy_ipv6)
    _add(menu, "Copy gateway", cb.copy_gateway)
    _add(menu, "Copy DNS", cb.copy_dns)
    menu.addSeparator()
    _add(menu, "Renew DHCP", cb.renew_dhcp)
    _add(menu, "Flush DNS", cb.flush_dns)
    _add(menu, "Show ARP / neighbors", cb.show_arp)
    _add(menu, "Start timed capture", cb.start_capture)
    menu.addSeparator()
    _add(menu, "Set as default probe source", cb.set_probe_source)
    return menu


def build_footer_power_menu(parent: QWidget, cb: VerbCallbacks) -> QMenu:
    menu = QMenu(parent)
    _add(menu, "Copy: ipconfig /all", lambda: cb.copy_text("ipconfig /all"))
    _add(menu, "Copy: netsh wlan show interfaces", lambda: cb.copy_text("netsh wlan show interfaces"))
    _add(menu, "Copy: arp -a", lambda: cb.copy_text("arp -a"))
    return menu


def build_empty_canvas_menu(parent: QWidget, cb: VerbCallbacks) -> QMenu:
    menu = QMenu(parent)
    _add(menu, "Paste target & Run", cb.paste_and_run, "Ctrl+V")
    _add(menu, "Recent targets", cb.recent_targets)
    menu.addSeparator()
    _add(
        menu,
        "Start \"Can't reach internet\" playbook",
        lambda: cb.start_playbook("Can't reach internet"),
    )
    return menu
