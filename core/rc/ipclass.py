"""IP address classification. Decides which addresses may ever be sent to outside services."""

from __future__ import annotations

import ipaddress
from typing import Optional, Tuple

CGNAT_NET = ipaddress.ip_network("100.64.0.0/10")
STARLINK_DISH_IP = "192.168.100.1"
STARLINK_ASN = 14593

_DOC_NETS = [ipaddress.ip_network(n) for n in
             ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24", "2001:db8::/32")]
_BENCH_NETS = [ipaddress.ip_network(n) for n in ("198.18.0.0/15",)]

CAT_PUBLIC = "public"
CAT_PRIVATE = "private"
CAT_CGNAT = "cgnat"
CAT_LOOPBACK = "loopback"
CAT_LINK_LOCAL = "link-local"
CAT_MULTICAST = "multicast"
CAT_DOC = "documentation"
CAT_RESERVED = "reserved"
CAT_INVALID = "invalid"

_CAT_TEXT = {
    CAT_PRIVATE: "private (LAN) address",
    CAT_CGNAT: "carrier-grade NAT address (100.64.0.0/10)",
    CAT_LOOPBACK: "loopback address",
    CAT_LINK_LOCAL: "link-local address",
    CAT_MULTICAST: "multicast address",
    CAT_DOC: "documentation-range address",
    CAT_RESERVED: "reserved address",
    CAT_INVALID: "not a valid IP address",
}


def parse_ip(text: str) -> Optional[ipaddress._BaseAddress]:
    try:
        return ipaddress.ip_address(text.strip())
    except (ValueError, AttributeError):
        return None


def classify_ip(text: str) -> str:
    ip = parse_ip(text)
    if ip is None:
        return CAT_INVALID
    if ip.is_loopback:
        return CAT_LOOPBACK
    if ip.is_link_local:
        return CAT_LINK_LOCAL
    if ip.is_multicast:
        return CAT_MULTICAST
    if any(ip in n for n in _DOC_NETS):
        return CAT_DOC
    if ip.version == 4 and ip in CGNAT_NET:
        return CAT_CGNAT
    if ip.is_private:
        return CAT_PRIVATE
    if ip.is_unspecified or ip.is_reserved or any(ip in n for n in _BENCH_NETS):
        return CAT_RESERVED
    if not ip.is_global:
        return CAT_RESERVED
    return CAT_PUBLIC


def lookup_allowed(text: str) -> bool:
    """True only for globally routable addresses. Everything else is never looked up."""
    return classify_ip(text) == CAT_PUBLIC


def skip_reason(text: str) -> Optional[str]:
    """Clear label for the UI when an address is skipped, or None when it may be looked up."""
    cat = classify_ip(text)
    if cat == CAT_PUBLIC:
        return None
    return f"Not looked up: {_CAT_TEXT.get(cat, cat)}. Only public addresses are ever sent to outside services."


def is_cgnat(text: str) -> bool:
    return classify_ip(text) == CAT_CGNAT


def is_private_like(text: str) -> bool:
    """LAN-side address (RFC1918, link-local, loopback)."""
    return classify_ip(text) in (CAT_PRIVATE, CAT_LINK_LOCAL, CAT_LOOPBACK)


def split_v4(text: str) -> Tuple[int, int, int, int]:
    a, b, c, d = (int(x) for x in text.split("."))
    return a, b, c, d
