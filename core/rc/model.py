"""Plain data model shared by the probe engine, verdict engine and UI (no Qt, no I/O)."""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

SEG_PC = "pc"
SEG_GATEWAY = "gateway"
SEG_DISH = "dish"
SEG_INTERNET = "internet"
SEGMENTS = (SEG_PC, SEG_GATEWAY, SEG_DISH, SEG_INTERNET)

SEGMENT_NAMES = {
    SEG_PC: "THIS PC",
    SEG_GATEWAY: "GATEWAY",
    SEG_DISH: "DISH",
    SEG_INTERNET: "INTERNET",
}

# Plain-English noun phrases used in verdict text.
SEGMENT_PHRASES = {
    SEG_PC: "this PC",
    SEG_GATEWAY: "your gateway (router)",
    SEG_DISH: "the Starlink dish and its link",
    SEG_INTERNET: "the wider internet",
}


@dataclass(frozen=True)
class Sample:
    """One probe result for one hop."""

    ts: float                       # epoch seconds when the probe was sent
    ok: bool                        # True when the hop (or target) answered
    rtt_ms: Optional[float] = None  # round trip in ms when ok
    ip: Optional[str] = None        # address that answered (hop router or target)
    status: str = ""                # short status text, e.g. "ttl-expired", "timeout"


@dataclass
class HopStats:
    sent: int = 0
    recv: int = 0
    loss_pct: float = 0.0
    last_rtt: Optional[float] = None
    avg_rtt: Optional[float] = None
    min_rtt: Optional[float] = None
    max_rtt: Optional[float] = None
    median_rtt: Optional[float] = None
    jitter: Optional[float] = None       # mean abs difference of consecutive RTTs
    consec_fail: int = 0                 # failures in a row at the tail
    consec_ok: int = 0
    last_ok_ts: Optional[float] = None
    first_fail_ts: Optional[float] = None  # ts of the first failure in the trailing run


def compute_stats(samples: Sequence[Sample]) -> HopStats:
    st = HopStats()
    st.sent = len(samples)
    if not samples:
        return st
    rtts = [s.rtt_ms for s in samples if s.ok and s.rtt_ms is not None]
    st.recv = sum(1 for s in samples if s.ok)
    st.loss_pct = 100.0 * (st.sent - st.recv) / st.sent
    if rtts:
        st.last_rtt = None
        for s in reversed(samples):
            if s.ok and s.rtt_ms is not None:
                st.last_rtt = s.rtt_ms
                break
        st.avg_rtt = sum(rtts) / len(rtts)
        st.min_rtt = min(rtts)
        st.max_rtt = max(rtts)
        st.median_rtt = statistics.median(rtts)
        if len(rtts) > 1:
            st.jitter = sum(abs(rtts[i] - rtts[i - 1]) for i in range(1, len(rtts))) / (len(rtts) - 1)
        else:
            st.jitter = 0.0
    # trailing runs
    n_fail = 0
    for s in reversed(samples):
        if s.ok:
            break
        n_fail += 1
    n_ok = 0
    for s in reversed(samples):
        if not s.ok:
            break
        n_ok += 1
    st.consec_fail, st.consec_ok = n_fail, n_ok
    if n_fail:
        st.first_fail_ts = samples[len(samples) - n_fail].ts
    for s in reversed(samples):
        if s.ok:
            st.last_ok_ts = s.ts
            break
    return st


@dataclass
class HopView:
    """A hop as seen by the verdict engine and the UI (a frozen copy of engine state)."""

    ttl: int                          # 0 = this PC, 1.. = routers
    ip: Optional[str]                 # best known address for this hop
    segment: str                      # SEG_*
    label_source: str = "auto"        # "auto" | "override" | "fixed"
    is_target: bool = False
    samples: List[Sample] = field(default_factory=list)   # oldest first
    ever_ok: bool = False             # has ever answered since the path was mapped
    total_sent: int = 0
    seen_ips: List[str] = field(default_factory=list)
    hostname: Optional[str] = None
    asn: Optional[int] = None
    note: str = ""

    def stats(self, window: Optional[int] = None) -> HopStats:
        s = self.samples if window is None else self.samples[-window:]
        return compute_stats(s)

    @property
    def key(self) -> str:
        return f"ttl:{self.ttl}"


@dataclass
class PathSnapshot:
    """Everything the verdict engine needs, as of one moment."""

    ts: float
    target: str
    hops: List[HopView]                       # ttl 0 (this PC) first, then routers, target last
    route_ok: bool = True                     # False when this PC has no usable default route
    gateway_ip: Optional[str] = None
    source_ip: Optional[str] = None
    mapped: bool = False                      # True once traceroute mapping found beyond-gateway hops
    side_probes: Dict[str, HopView] = field(default_factory=dict)  # e.g. "dish-lan"
    started_ts: float = 0.0

    def probed_hops(self) -> List[HopView]:
        return [h for h in self.hops if h.ttl >= 1]

    def hop_by_ttl(self, ttl: int) -> Optional[HopView]:
        for h in self.hops:
            if h.ttl == ttl:
                return h
        return None


# ---------------------------------------------------------------- evidence / verdict

STATUS_OK = "ok"
STATUS_INFO = "info"
STATUS_WARN = "warn"
STATUS_FAIL = "fail"


@dataclass
class Evidence:
    """One observation. Providers emit these; rules reason over them; the UI lists them."""

    source: str                       # provider name, e.g. "path-probe"
    kind: str                         # machine kind, e.g. "hop-state", "dish-obstruction"
    text: str                         # one plain-English line shown under the verdict
    status: str = STATUS_INFO         # STATUS_*
    segment: Optional[str] = None     # SEG_* the observation belongs to
    ttl: Optional[int] = None         # hop it concerns, when any
    data: Dict[str, object] = field(default_factory=dict)


KIND_HEALTHY = "healthy"
KIND_DEGRADED = "degraded"
KIND_OUTAGE = "outage"
KIND_UNKNOWN = "unknown"          # "can't tell"
KIND_MEASURING = "measuring"      # still gathering the first probes (also "can't tell yet")

CONF_HIGH = "high"
CONF_MEDIUM = "medium"
CONF_LOW = "low"


@dataclass
class Finding:
    """A rule's conclusion."""

    rule: str
    kind: str
    headline: str
    explanation: str
    segment: Optional[str] = None
    ttl: Optional[int] = None         # first hop the fault is attributed to
    confidence: str = CONF_MEDIUM
    priority: int = 0                 # higher wins
    since_ts: Optional[float] = None  # when the condition began, when known
    disconnect: bool = False          # True when this PC has lost its connection (logged as an outage)


@dataclass
class Verdict:
    kind: str
    headline: str
    explanation: str
    segment: Optional[str]
    ttl: Optional[int]
    confidence: str
    rule: str
    evidence: List[Evidence]
    ts: float
    since_ts: Optional[float] = None
    disconnect: bool = False

    @property
    def is_cant_tell(self) -> bool:
        return self.kind in (KIND_UNKNOWN, KIND_MEASURING)
