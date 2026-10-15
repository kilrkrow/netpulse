"""Hop labeling: which segment of the path does each hop belong to?

Rules, in order (first match wins):
  1. User override (by address "ip:<addr>" or by hop number "ttl:<n>"), persisted in settings.
  2. Hop 0 is this PC.
  3. The hop whose address is the default gateway is the gateway.
  4. The dish: a CGNAT address (100.64.0.0/10), the dish's own address 192.168.100.1,
     or a hop whose origin ASN is Starlink (AS14593; known only once an ASN is available).
  5. A private/LAN address after the gateway that is not the dish is more of the local network:
     it is labeled gateway.
  6. Everything else is the wider internet.
"""

from __future__ import annotations

from typing import Dict, Optional

from core.rc.ipclass import STARLINK_ASN, STARLINK_DISH_IP, is_cgnat, is_private_like
from core.rc.model import SEG_DISH, SEG_GATEWAY, SEG_INTERNET, SEG_PC, SEGMENTS

OVERRIDE_AUTO = "auto"


def override_key_ip(ip: str) -> str:
    return f"ip:{ip}"


def override_key_ttl(ttl: int) -> str:
    return f"ttl:{ttl}"


def label_hop(
    ttl: int,
    ip: Optional[str],
    gateway_ip: Optional[str],
    overrides: Optional[Dict[str, str]] = None,
    asn: Optional[int] = None,
    gateway_ttl_hint: Optional[int] = 1,
    prev_segment: str = SEG_PC,
) -> "tuple[str, str]":
    """Return (segment, source) where source is "override" or "auto"."""
    overrides = overrides or {}
    if ip:
        v = overrides.get(override_key_ip(ip))
        if v in SEGMENTS:
            return v, "override"
    v = overrides.get(override_key_ttl(ttl))
    if v in SEGMENTS:
        return v, "override"
    if ttl == 0:
        return SEG_PC, "auto"
    if ip and gateway_ip and ip == gateway_ip:
        return SEG_GATEWAY, "auto"
    if ip:
        if is_cgnat(ip) or ip == STARLINK_DISH_IP:
            return SEG_DISH, "auto"
        if asn == STARLINK_ASN:
            return SEG_DISH, "auto"
        if is_private_like(ip):
            # A private address behind the dish is Starlink's own network; otherwise it is more LAN.
            return (SEG_DISH if prev_segment == SEG_DISH else SEG_GATEWAY), "auto"
        return SEG_INTERNET, "auto"
    # silent hop (no address): inherit from position
    if ttl == gateway_ttl_hint and gateway_ip is None:
        return SEG_GATEWAY, "auto"
    return SEG_INTERNET, "auto"


def label_path(hops, gateway_ip, overrides=None, asn_by_ip: Optional[Dict[str, int]] = None) -> None:
    """Label every HopView in place. Silent hops inherit the segment of the previous known hop
    when it is the dish (a dish-side router that does not answer is still dish-side)."""
    asn_by_ip = asn_by_ip or {}
    prev_seg = SEG_PC
    for h in hops:
        if h.label_source == "fixed":
            prev_seg = h.segment
            continue
        asn = asn_by_ip.get(h.ip) if h.ip else None
        seg, src = label_hop(h.ttl, h.ip, gateway_ip, overrides, asn, prev_segment=prev_seg)
        if h.ip is None and src != "override" and h.ttl >= 1 and prev_seg == SEG_DISH:
            seg = SEG_DISH
        h.segment, h.label_source = seg, src
        prev_seg = seg
