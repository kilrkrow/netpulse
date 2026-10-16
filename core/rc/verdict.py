"""Verdict engine: plain-English diagnosis built from pluggable evidence providers and rules.

    snapshot --> [EvidenceProvider ...] --> evidence --> [Rule(detect) ...] --> Finding(s)
                                                              |
                          highest priority finding --> [Rule(refine) ...] --> Verdict

* An EvidenceProvider turns some data source into Evidence items (one plain-English line each,
  plus structured data). The built-in one reads this PC's own hop probes. Later phases add
  providers (router data, dish telemetry) without touching the engine or the existing rules.
* A Rule with stage "detect" looks at the context and may return a Finding. The engine keeps the
  one with the highest priority. A Rule with stage "refine" may amend the winning finding
  (extra explanation, changed confidence) using evidence from any provider.
* Never guess: when the evidence is thin the answer is "can't tell", and it says why.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Protocol

from core.rc.model import (
    CONF_HIGH, CONF_LOW, CONF_MEDIUM, KIND_DEGRADED, KIND_HEALTHY, KIND_MEASURING, KIND_OUTAGE,
    KIND_UNKNOWN, SEG_DISH, SEG_GATEWAY, SEG_INTERNET, SEG_PC, SEGMENT_NAMES, STATUS_FAIL, STATUS_INFO,
    STATUS_OK, STATUS_WARN, Evidence, Finding, HopStats, HopView, PathSnapshot, Verdict, compute_stats)


# ----------------------------------------------------------------------------- configuration

@dataclass
class VerdictConfig:
    window: int = 30            # probes used for loss/latency now (about 30 s at 1 per second)
    min_samples: int = 8        # probes a hop needs before it is judged
    down_n: int = 5             # failures in a row that mean "not answering"
    loss_pct: float = 10.0      # loss that counts as a problem
    loss_min_sent: int = 15     # probes needed before loss is judged at all
    loss_min_lost: int = 4      # never call loss on fewer lost probes than this
    loss_clean_pct: float = 5.0  # below this a hop counts as clean
    lat_factor: float = 2.5     # elevated when this many times the hop's own baseline ...
    lat_floor_ms: float = 30.0  # ... and at least this much above it
    lat_recent: int = 10        # probes in the "recent" latency median
    baseline_min: int = 30      # samples older than the window needed for a baseline
    abs_high_ms: float = 400.0  # latency judged high with no baseline at all
    spike_frac: float = 0.4     # share of recent probes above the threshold = intermittent spikes


# ----------------------------------------------------------------------------- assessment

STATE_MEASURING = "measuring"
STATE_SILENT = "silent"      # never answered: no information (many routers ignore TTL probes)
STATE_DOWN = "down"
STATE_LOSSY = "lossy"
STATE_OK = "ok"


@dataclass
class HopAssessment:
    hop: HopView
    state: str
    stats: HopStats                    # over the recent window
    baseline_ms: Optional[float] = None
    recent_median_ms: Optional[float] = None
    elevated: bool = False
    lossy: bool = False

    @property
    def ttl(self) -> int:
        return self.hop.ttl

    @property
    def segment(self) -> str:
        return self.hop.segment

    @property
    def is_target(self) -> bool:
        return self.hop.is_target


def _median(vals: List[float]) -> Optional[float]:
    if not vals:
        return None
    s = sorted(vals)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def drop_outage_runs(samples: List, down_n: int) -> List:
    """Remove finished outage episodes (runs of down_n or more failures that are followed by a
    success). They belong to the outage log; counting them again as "packet loss" would keep a
    recovered network flagged for a whole window. A run still in progress at the tail is kept."""
    out: List = []
    i, n = 0, len(samples)
    while i < n:
        if samples[i].ok:
            out.append(samples[i])
            i += 1
            continue
        j = i
        while j < n and not samples[j].ok:
            j += 1
        if j - i >= down_n and j < n:
            pass                      # finished outage episode: dropped
        else:
            out.extend(samples[i:j])
        i = j
    return out


def assess_hop(h: HopView, cfg: VerdictConfig) -> HopAssessment:
    samples = h.samples
    win = drop_outage_runs(samples, cfg.down_n)[-cfg.window:]
    st = compute_stats(win)
    if st.consec_fail >= cfg.down_n:       # a long outage fills the window: take the true tail from the full history
        full = compute_stats(samples)
        st.consec_fail, st.last_ok_ts, st.first_fail_ts = full.consec_fail, full.last_ok_ts, full.first_fail_ts
    # state
    if len(samples) < cfg.down_n and not h.ever_ok:
        state = STATE_MEASURING
    elif not h.ever_ok and not h.is_target:
        state = STATE_SILENT if len(samples) >= cfg.min_samples else STATE_MEASURING
    elif st.consec_fail >= cfg.down_n:
        state = STATE_DOWN
    elif len(samples) < cfg.min_samples:
        state = STATE_MEASURING
    else:
        state = STATE_OK
    a = HopAssessment(h, state, st)
    # loss
    if state not in (STATE_MEASURING, STATE_SILENT, STATE_DOWN) and st.sent >= cfg.loss_min_sent:
        a.lossy = st.loss_pct >= cfg.loss_pct and (st.sent - st.recv) >= cfg.loss_min_lost
        if a.lossy:
            a.state = STATE_LOSSY
    # latency vs the hop's own baseline
    older = samples[:-cfg.window] if len(samples) > cfg.window else []
    base_rtts = [s.rtt_ms for s in older if s.ok and s.rtt_ms is not None]
    if len(base_rtts) >= cfg.baseline_min:
        a.baseline_ms = _median(base_rtts)
    recent = [s.rtt_ms for s in win if s.ok and s.rtt_ms is not None]
    last_recent = recent[-cfg.lat_recent:]
    if len(last_recent) >= max(5, cfg.lat_recent // 2):
        a.recent_median_ms = _median(last_recent)
        thr = elevated_threshold(a.baseline_ms, cfg)
        above = sum(1 for r in recent[-20:] if r > thr)
        frac = above / max(1, len(recent[-20:]))
        a.elevated = (a.recent_median_ms > thr) or (frac >= cfg.spike_frac and above >= 4)
    return a


def elevated_threshold(baseline: Optional[float], cfg: VerdictConfig) -> float:
    if baseline is None:
        return cfg.abs_high_ms
    return max(baseline * cfg.lat_factor, baseline + cfg.lat_floor_ms)


# ----------------------------------------------------------------------------- context

class VerdictContext:
    def __init__(self, snapshot: PathSnapshot, cfg: VerdictConfig):
        self.snapshot = snapshot
        self.cfg = cfg
        self.assessments: List[HopAssessment] = [
            assess_hop(h, cfg) for h in snapshot.hops if h.ttl >= 1]
        self.evidence: List[Evidence] = []
        self.notes: List[Evidence] = []      # derived lines added by rules

    # convenience -----------------------------------------------------------------
    @property
    def target(self) -> Optional[HopAssessment]:
        for a in self.assessments:
            if a.is_target:
                return a
        return self.assessments[-1] if self.assessments else None

    def responsive(self) -> List[HopAssessment]:
        """Hops that carry information: they have answered at some point (or are the target)."""
        return [a for a in self.assessments if a.state not in (STATE_SILENT, STATE_MEASURING)]

    def silent_count(self) -> int:
        return sum(1 for a in self.assessments if a.state == STATE_SILENT)

    def evidence_of(self, kind: str) -> List[Evidence]:
        return [e for e in self.evidence if e.kind == kind]

    def add_note(self, ev: Evidence) -> None:
        self.notes.append(ev)


def hop_name(a: HopAssessment) -> str:
    h = a.hop
    seg = {SEG_GATEWAY: "Gateway", SEG_DISH: "Dish side", SEG_INTERNET: "Internet"}.get(h.segment, "Hop")
    if h.is_target:
        return f"Target {h.ip}"
    if h.ip:
        return f"{seg} hop {h.ttl} ({h.ip})"
    return f"Hop {h.ttl} (no address)"


def _fmt_ms(v: Optional[float]) -> str:
    if v is None:
        return "-"
    return f"{v:.0f} ms" if v >= 10 else f"{v:.1f} ms"


def _ago(now: float, ts: Optional[float]) -> str:
    if ts is None:
        return "never"
    d = max(0, int(now - ts))
    return f"{d} s ago" if d < 120 else f"{d // 60} min ago"


# ----------------------------------------------------------------------------- protocols

class EvidenceProvider(Protocol):
    name: str

    def collect(self, ctx: VerdictContext) -> List[Evidence]: ...


class Rule(Protocol):
    id: str
    priority: int
    stage: str      # "detect" or "refine"

    def evaluate(self, ctx: VerdictContext, finding: Optional[Finding] = None) -> Optional[Finding]: ...


# ----------------------------------------------------------------------------- built-in provider

class PathProbeProvider:
    """Evidence from this PC's own per-hop ICMP probes (the only provider in the MVP)."""

    name = "path-probe"

    def collect(self, ctx: VerdictContext) -> List[Evidence]:
        out: List[Evidence] = []
        now = ctx.snapshot.ts
        for a in ctx.assessments:
            st = a.stats
            nm = hop_name(a)
            data = {"state": a.state, "loss_pct": round(st.loss_pct, 1), "sent": st.sent,
                    "rtt_ms": st.last_rtt, "median_ms": a.recent_median_ms, "baseline_ms": a.baseline_ms}
            if a.state == STATE_MEASURING:
                text, status = f"{nm}: only {a.hop.total_sent} probes so far.", STATUS_INFO
            elif a.state == STATE_SILENT:
                text, status = f"{nm}: never answers probes (many routers ignore them). No information from it.", STATUS_INFO
            elif a.state == STATE_DOWN:
                text = (f"{nm}: not answering. Last {st.consec_fail} probes failed; "
                        f"last answer {_ago(now, st.last_ok_ts)}.")
                status = STATUS_FAIL
            elif a.state == STATE_LOSSY:
                text = f"{nm}: {st.loss_pct:.0f}% of the last {st.sent} probes lost; answers take {_fmt_ms(a.recent_median_ms)}."
                status = STATUS_WARN
            else:
                lat = _fmt_ms(st.avg_rtt)
                text = f"{nm}: answering, {lat} average, {st.loss_pct:.0f}% loss over the last {st.sent} probes."
                status = STATUS_WARN if a.elevated else STATUS_OK
                if a.elevated:
                    text = (f"{nm}: slow. Now about {_fmt_ms(a.recent_median_ms)} "
                            f"(normally {_fmt_ms(a.baseline_ms)})." if a.baseline_ms is not None else
                            f"{nm}: slow. Answers take about {_fmt_ms(a.recent_median_ms)}.")
            out.append(Evidence(self.name, "hop-state", text, status, a.segment, a.ttl, data))
        for name, h in ctx.snapshot.side_probes.items():
            st = compute_stats(h.samples[-ctx.cfg.window:])
            if name == "dish-lan" and st.sent >= 3:
                if st.consec_fail >= ctx.cfg.down_n:
                    out.append(Evidence(self.name, "dish-lan", f"Dish address {h.ip} is not answering.",
                                        STATUS_FAIL, SEG_DISH, None, {"state": STATE_DOWN}))
                else:
                    out.append(Evidence(self.name, "dish-lan",
                                        f"Dish address {h.ip} answers in {_fmt_ms(st.avg_rtt)}.",
                                        STATUS_OK, SEG_DISH, None, {"state": STATE_OK}))
        return out


# ----------------------------------------------------------------------------- built-in rules

def _since(ctx: VerdictContext, hops: List[HopAssessment]) -> Optional[float]:
    ts = [a.stats.first_fail_ts for a in hops if a.stats.first_fail_ts is not None]
    return min(ts) if ts else None


def _prev_good(ctx: VerdictContext, a: HopAssessment) -> Optional[HopAssessment]:
    prev = None
    for b in ctx.responsive():
        if b.ttl >= a.ttl:
            break
        if b.state in (STATE_OK, STATE_LOSSY):
            prev = b
    return prev


class NoRouteRule:
    id = "no-route"
    priority = 100
    stage = "detect"

    def evaluate(self, ctx, finding=None):
        if ctx.snapshot.route_ok:
            return None
        return Finding(
            self.id, KIND_OUTAGE, "No network connection on this PC",
            "This PC has no usable route to the internet: no default gateway or the network adapter "
            "is disconnected. Check the cable, Wi-Fi, or the adapter.",
            SEG_PC, 0, CONF_HIGH, self.priority, None, True)


class MeasuringRule:
    id = "measuring"
    priority = 20
    stage = "detect"

    def evaluate(self, ctx, finding=None):
        tgt = ctx.target
        have = tgt.hop.total_sent if tgt else 0
        if tgt is not None and tgt.state != STATE_MEASURING:
            return None
        need = ctx.cfg.min_samples
        return Finding(
            self.id, KIND_MEASURING, "Can't tell yet: still collecting probes",
            f"Only {have} of the {need} probes needed to judge the path have come back. "
            "Give it a few more seconds.", None, None, CONF_LOW, self.priority, None)


class OutageRule:
    id = "outage"
    priority = 90
    stage = "detect"

    def evaluate(self, ctx, finding=None):
        tgt = ctx.target
        if tgt is None or tgt.state != STATE_DOWN:
            return None
        resp = ctx.responsive()
        # the frontier is the first hop of the trailing run of "down" hops
        idx = len(resp) - 1
        while idx > 0 and resp[idx - 1].state == STATE_DOWN:
            idx -= 1
        frontier = resp[idx]
        run = resp[idx:]
        prev = _prev_good(ctx, frontier)
        since = _since(ctx, run)
        silent = ctx.silent_count()
        tgt_only = len(run) == 1 and frontier.is_target

        # earlier hops that stopped answering although later ones still do: not a fault
        for a in resp[:idx]:
            if a.state == STATE_DOWN:
                ctx.add_note(Evidence(
                    "verdict", "ignored-hop",
                    f"{hop_name(a)} is not answering, but hops after it are. That router ignores "
                    "probes aimed at it; it is not a fault.", STATUS_INFO, a.segment, a.ttl))

        if tgt_only:
            if not tgt.hop.ever_ok:
                return Finding(
                    "target-silent", KIND_UNKNOWN, "Can't tell: the target never answers",
                    f"{tgt.hop.ip} has not answered a single probe since NetPulse started. It may block "
                    "ping. Pick another target in Settings; nothing can be concluded about your network.",
                    None, tgt.ttl, CONF_LOW, self.priority, None)
            beyond_gateway_known = prev is not None and prev.segment != SEG_GATEWAY
            if not beyond_gateway_known:
                return Finding(
                    "target-only-unmapped", KIND_UNKNOWN, "Can't tell which segment is down",
                    f"{'Your gateway' if prev else 'This PC'} answers, but {tgt.hop.ip} does not, and nothing "
                    "between them answers probes, so the break could be the dish link, your provider, or the "
                    "internet. More evidence is needed.", None, tgt.ttl, CONF_LOW, self.priority, since, True)
            extra = f" {silent} hop(s) past it never answer probes, so the exact spot is hidden." if silent else ""
            if prev.segment == SEG_DISH:
                head = "Internet side is down: your gateway and dish answer, nothing beyond"
                expl = (f"Your gateway and the dish side ({prev.hop.ip}) answer normally, but {tgt.hop.ip} "
                        f"stopped answering.{extra} The problem is past your equipment: Starlink's network "
                        "or the wider internet, or the target itself.")
            else:
                head = "Wider internet looks down: path stops answering past a working hop"
                expl = (f"Everything up to {prev.hop.ip} answers, but {tgt.hop.ip} stopped answering.{extra} "
                        "The break is beyond that hop on the wider internet, or the target itself is down.")
            return Finding(self.id, KIND_OUTAGE, head, expl, SEG_INTERNET, tgt.ttl, CONF_MEDIUM,
                           self.priority, since, True)

        seg = frontier.segment
        nm = hop_name(frontier)
        n_down = len(run)
        conf = CONF_HIGH if (n_down >= 2 or frontier.hop.ever_ok) else CONF_MEDIUM
        rest = (f" and the {n_down - 1} hop{'s' if n_down > 2 else ''} after it") if n_down > 1 else ""
        if seg == SEG_GATEWAY:
            head = "Gateway is down: your router stopped answering"
            expl = (f"{nm}{rest} stopped answering. Nothing past your router can be reached, so the problem is "
                    "the router itself or the link between this PC and the router (cable, Wi-Fi, router "
                    "rebooting).")
        elif seg == SEG_DISH:
            head = "Dish is down: your router is fine, the Starlink link is not"
            expl = (f"Your gateway answers, but {nm}{rest} stopped answering. The break is at the Starlink "
                    "dish or its link to the satellites. Check the dish for obstructions, power, or a "
                    "Starlink outage.")
        else:
            if prev is not None and prev.segment == SEG_DISH:
                head = "Internet side is down: gateway and dish answer, nothing beyond"
                expl = (f"Your gateway and the dish side answer, but {nm}{rest} stopped answering. The break "
                        "is past your equipment: Starlink's network or the wider internet.")
            elif prev is not None and prev.segment == SEG_GATEWAY:
                head = "Internet side is down: your router answers, nothing past it does"
                expl = (f"Your gateway answers, but {nm}{rest} stopped answering. The break is between your "
                        "router and your provider, or further out on the internet.")
            else:
                head = "Wider internet looks down: the path stops answering"
                where = f"past {prev.hop.ip}" if prev and prev.hop.ip else "at this point"
                expl = f"{nm}{rest} stopped answering {where}. The break is out on the wider internet."
        return Finding(self.id, KIND_OUTAGE, head, expl, seg, frontier.ttl, conf, self.priority, since, True)


class PendingRule:
    """Probes to the target have just begun failing: too early to say outage, too late for "healthy"."""
    id = "pending"
    priority = 75
    stage = "detect"

    def evaluate(self, ctx, finding=None):
        tgt = ctx.target
        if tgt is None or tgt.state in (STATE_DOWN, STATE_MEASURING):
            return None
        if 2 <= tgt.stats.consec_fail < ctx.cfg.down_n:
            return Finding(
                self.id, KIND_MEASURING, "Can't tell yet: probes just started failing",
                f"The last {tgt.stats.consec_fail} probes to {tgt.hop.ip} got no answer. Waiting for a few more "
                "before calling it an outage or a blip.", None, None, CONF_LOW, self.priority, None)
        return None


class LossRule:
    id = "loss"
    priority = 70
    stage = "detect"

    def evaluate(self, ctx, finding=None):
        cfg = ctx.cfg
        tgt = ctx.target
        if tgt is None or tgt.state in (STATE_DOWN, STATE_MEASURING) or tgt.stats.sent < cfg.loss_min_sent:
            return None
        resp = [a for a in ctx.responsive() if a.state != STATE_DOWN]
        lossy = [a for a in resp if a.lossy]
        # lossy hops whose later hops are clean: ICMP rate limiting, not a fault
        for a in lossy:
            later = [b for b in resp if b.ttl > a.ttl]
            if later and all(b.stats.loss_pct < cfg.loss_clean_pct for b in later):
                ctx.add_note(Evidence(
                    "verdict", "rate-limited-hop",
                    f"{hop_name(a)} shows {a.stats.loss_pct:.0f}% loss, but every hop after it is clean. "
                    "That router rate-limits its ICMP replies; this is not a fault.",
                    STATUS_INFO, a.segment, a.ttl))
        if not tgt.lossy:
            return None
        f = None
        for i, a in enumerate(resp):
            if not a.lossy:
                continue
            later = resp[i + 1:]
            if all(b.stats.loss_pct >= cfg.loss_pct / 2.0 for b in later):
                f = a
                break
        since = None
        if f is None or f.ttl == tgt.ttl:     # loss that first shows at the far end cannot be pinned on a segment
            return Finding(
                self.id, KIND_DEGRADED, "Packet loss, but can't tell which segment causes it",
                f"{tgt.stats.loss_pct:.0f}% of probes to {tgt.hop.ip} are lost, but the hops on the way do not "
                "show where it starts. It may be the far end or an intermittent link.",
                None, tgt.ttl, CONF_LOW, self.priority, since)
        later_lossy = [b for b in resp if b.ttl > f.ttl and b.lossy]
        inherited = " Later hops also show it, which is that same loss carried along, not extra faults." \
            if later_lossy else ""
        seg = f.segment
        nm = hop_name(f)
        pct = f"{f.stats.loss_pct:.0f}%"
        if seg == SEG_GATEWAY:
            head = f"Packet loss starts at your gateway ({pct})"
            expl = (f"{nm} loses {pct} of probes and the loss continues to {tgt.hop.ip}.{inherited} Likely the "
                    "link between this PC and the router (weak Wi-Fi, bad cable) or an overloaded router.")
        elif seg == SEG_DISH:
            head = f"Packet loss starts on the Starlink link ({pct})"
            expl = (f"Your gateway is clean, but {nm} loses {pct} of probes and the loss continues to "
                    f"{tgt.hop.ip}.{inherited} Likely obstructions or the satellite link.")
        else:
            head = f"Packet loss starts on the internet side ({pct})"
            expl = (f"Your own equipment is clean, but {nm} loses {pct} of probes and the loss continues to "
                    f"{tgt.hop.ip}.{inherited} The problem is beyond your gateway and dish.")
        return Finding(self.id, KIND_DEGRADED, head, expl, seg, f.ttl, CONF_HIGH if len(later_lossy) else CONF_MEDIUM,
                       self.priority, since)


class LatencyRule:
    id = "latency"
    priority = 60
    stage = "detect"

    def evaluate(self, ctx, finding=None):
        tgt = ctx.target
        if tgt is None or tgt.state in (STATE_DOWN, STATE_MEASURING):
            return None
        resp = [a for a in ctx.responsive() if a.state != STATE_DOWN]
        for a in resp:
            if a.elevated:
                later = [b for b in resp if b.ttl > a.ttl]
                if later and not any(b.elevated for b in later):
                    ctx.add_note(Evidence(
                        "verdict", "slow-hop-ignored",
                        f"{hop_name(a)} answers slowly, but hops after it do not. That router is slow to "
                        "answer probes aimed at it; traffic through it is fine.",
                        STATUS_INFO, a.segment, a.ttl))
        if not tgt.elevated:
            return None
        f = None
        for i, a in enumerate(resp):
            if a.elevated and all(b.elevated for b in resp[i + 1:]):
                f = a
                break
        base = tgt.baseline_ms
        now_ms = tgt.recent_median_ms
        delta = (f"about {_fmt_ms(now_ms)} now versus {_fmt_ms(base)} normally"
                 if base is not None else f"about {_fmt_ms(now_ms)}")
        if f is None:
            return Finding(
                self.id, KIND_DEGRADED, "Latency spikes, but can't tell which segment causes them",
                f"Round trips to {tgt.hop.ip} are {delta}, but no earlier hop shows the same slowdown, so "
                "the cause is not visible from here.", None, tgt.ttl, CONF_LOW, self.priority, None)
        seg = f.segment
        nm = hop_name(f)
        where = {SEG_GATEWAY: "at your gateway", SEG_DISH: "on the Starlink link",
                 SEG_INTERNET: "on the internet side"}.get(seg, "here")
        head = f"Latency spike {where}"
        expl = (f"{nm} is slow ({delta} to {tgt.hop.ip}) and every hop after it is slow too, so the delay "
                f"begins {where}.")
        return Finding(self.id, KIND_DEGRADED, head, expl, seg, f.ttl, CONF_MEDIUM, self.priority, None)


class HealthyRule:
    id = "healthy"
    priority = 10
    stage = "detect"

    def evaluate(self, ctx, finding=None):
        tgt = ctx.target
        if tgt is None or tgt.state != STATE_OK:
            return None
        st = tgt.stats
        n_ok = sum(1 for a in ctx.assessments if a.state == STATE_OK)
        return Finding(
            self.id, KIND_HEALTHY, "Network is healthy",
            f"Probes to {tgt.hop.ip} answer in {_fmt_ms(st.avg_rtt)} on average with "
            f"{st.loss_pct:.0f}% loss; {n_ok} of {len(ctx.assessments)} hops on the path look normal.",
            None, None, CONF_HIGH, self.priority, None)


# ----------------------------------------------------------------------------- engine

_STATUS_ORDER = {STATUS_FAIL: 0, STATUS_WARN: 1, STATUS_INFO: 2, STATUS_OK: 3}


class VerdictEngine:
    def __init__(self, config: Optional[VerdictConfig] = None,
                 providers: Optional[List[EvidenceProvider]] = None,
                 rules: Optional[List[Rule]] = None):
        self.cfg = config or VerdictConfig()
        self.providers: List[EvidenceProvider] = providers if providers is not None else [PathProbeProvider()]
        self.rules: List[Rule] = rules if rules is not None else [
            NoRouteRule(), OutageRule(), PendingRule(), LossRule(), LatencyRule(), MeasuringRule(), HealthyRule()]

    def add_provider(self, provider: EvidenceProvider) -> None:
        self.providers.append(provider)

    def add_rule(self, rule: Rule) -> None:
        self.rules.append(rule)

    def evaluate(self, snapshot: PathSnapshot) -> Verdict:
        ctx = VerdictContext(snapshot, self.cfg)
        for p in self.providers:
            try:
                ctx.evidence.extend(p.collect(ctx))
            except Exception as exc:    # a broken provider must never take the verdict down
                ctx.evidence.append(Evidence(getattr(p, "name", "provider"), "provider-error",
                                             f"Evidence source failed: {exc.__class__.__name__}.", STATUS_INFO))
        findings: List[Finding] = []
        for r in (r for r in self.rules if r.stage == "detect"):
            try:
                f = r.evaluate(ctx)
            except Exception as exc:
                ctx.add_note(Evidence("verdict", "rule-error", f"Rule {r.id} failed: {exc.__class__.__name__}.",
                                      STATUS_INFO))
                continue
            if f is not None:
                findings.append(f)
        if not findings:
            top = Finding("none", KIND_UNKNOWN, "Can't tell: not enough evidence",
                          "No rule could reach a conclusion from the probes collected so far.",
                          None, None, CONF_LOW, 0, None)
        else:
            top = max(findings, key=lambda f: (f.priority, _conf_rank(f.confidence)))
        for r in (r for r in self.rules if r.stage == "refine"):
            try:
                top = r.evaluate(ctx, top) or top
            except Exception:
                pass
        ev = ctx.evidence + ctx.notes
        order = {id(e): i for i, e in enumerate(ev)}
        ev.sort(key=lambda e: (_STATUS_ORDER.get(e.status, 2), order[id(e)]))
        return Verdict(top.kind, top.headline, top.explanation, top.segment, top.ttl, top.confidence,
                       top.rule, ev, snapshot.ts, top.since_ts, top.disconnect)


def _conf_rank(c: str) -> int:
    return {CONF_HIGH: 2, CONF_MEDIUM: 1, CONF_LOW: 0}.get(c, 0)
