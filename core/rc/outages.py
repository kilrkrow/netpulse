"""Disconnect log: outages persisted in SQLite, the tracker that records them, and the report."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Callable, List, Optional

from core.rc.db import Database
from core.rc.model import (KIND_DEGRADED, KIND_HEALTHY, SEGMENT_NAMES, PathSnapshot, Verdict)


@dataclass
class Outage:
    id: int
    start_ts: float
    end_ts: Optional[float]
    last_seen_ts: float
    segment: str
    hop_ip: Optional[str]
    target: Optional[str]
    headline: str
    explanation: str
    confidence: str
    interrupted: bool

    @property
    def open(self) -> bool:
        return self.end_ts is None

    def duration(self, now: Optional[float] = None) -> float:
        end = self.end_ts if self.end_ts is not None else (now if now is not None else self.last_seen_ts)
        return max(0.0, end - self.start_ts)


def _row(r) -> Outage:
    return Outage(r["id"], r["start_ts"], r["end_ts"], r["last_seen_ts"], r["segment"], r["hop_ip"],
                  r["target"], r["headline"], r["explanation"] or "", r["confidence"] or "",
                  bool(r["interrupted"]))


class OutageStore:
    def __init__(self, db: Database):
        self.db = db

    def open_outage(self, start_ts: float, now: float, segment: str, hop_ip: Optional[str],
                    target: str, headline: str, explanation: str, confidence: str,
                    evidence: Optional[list] = None) -> int:
        with self.db.lock:
            cur = self.db.conn.execute(
                "INSERT INTO outages(start_ts,last_seen_ts,segment,hop_ip,target,headline,explanation,"
                "confidence,evidence_json) VALUES (?,?,?,?,?,?,?,?,?)",
                (start_ts, now, segment, hop_ip, target, headline, explanation, confidence,
                 json.dumps(evidence or [])))
            return int(cur.lastrowid)

    def touch(self, outage_id: int, now: float, segment: Optional[str] = None, hop_ip: Optional[str] = None,
              headline: Optional[str] = None, explanation: Optional[str] = None,
              confidence: Optional[str] = None) -> None:
        with self.db.lock:
            self.db.conn.execute(
                "UPDATE outages SET last_seen_ts=?, segment=COALESCE(?,segment), hop_ip=COALESCE(?,hop_ip),"
                " headline=COALESCE(?,headline), explanation=COALESCE(?,explanation),"
                " confidence=COALESCE(?,confidence) WHERE id=?",
                (now, segment, hop_ip, headline, explanation, confidence, outage_id))

    def close_outage(self, outage_id: int, end_ts: float) -> None:
        with self.db.lock:
            self.db.conn.execute("UPDATE outages SET end_ts=?, last_seen_ts=MAX(last_seen_ts,?) WHERE id=?",
                                 (end_ts, end_ts, outage_id))

    def recover_interrupted(self) -> int:
        """At start-up: outages left open by a previous run (app killed or PC shut down) are closed at
        the last moment they were seen, and flagged so the log says the end is approximate."""
        with self.db.lock:
            cur = self.db.conn.execute(
                "UPDATE outages SET end_ts=last_seen_ts, interrupted=1 WHERE end_ts IS NULL")
            return cur.rowcount

    def list(self, limit: int = 200) -> List[Outage]:
        with self.db.lock:
            rows = self.db.conn.execute(
                "SELECT * FROM outages ORDER BY start_ts DESC LIMIT ?", (limit,)).fetchall()
        return [_row(r) for r in rows]

    def clear(self) -> None:
        with self.db.lock:
            self.db.conn.execute("DELETE FROM outages")


class OutageTracker:
    """Turns the verdict stream into logged outages.

    An outage opens once the verdict has reported a disconnect for `open_after` consecutive updates and
    closes once the connection has been confirmed back for `close_after` updates. The start is
    back-dated to the first failed probe; the end is the first successful update of the recovery.
    """

    def __init__(self, store: OutageStore, open_after: int = 2, close_after: int = 3,
                 touch_every_s: float = 5.0, on_change: Optional[Callable[[], None]] = None):
        self.store = store
        self.open_after = open_after
        self.close_after = close_after
        self.touch_every_s = touch_every_s
        self.on_change = on_change
        self.current_id: Optional[int] = None
        self._bad = 0
        self._good = 0
        self._first_good_ts: Optional[float] = None
        self._last_touch = 0.0

    def feed(self, verdict: Verdict, snapshot: PathSnapshot) -> None:
        now = verdict.ts
        if verdict.disconnect:
            self._bad += 1
            self._good = 0
            self._first_good_ts = None
            seg = verdict.segment or "unknown"
            hop = snapshot.hop_by_ttl(verdict.ttl) if verdict.ttl is not None else None
            hop_ip = hop.ip if hop else None
            if self.current_id is None:
                if self._bad >= self.open_after:
                    start = verdict.since_ts or now
                    self.current_id = self.store.open_outage(
                        start, now, seg, hop_ip, snapshot.target, verdict.headline, verdict.explanation,
                        verdict.confidence, [e.text for e in verdict.evidence[:8]])
                    self._last_touch = now
                    self._changed()
            elif now - self._last_touch >= self.touch_every_s:
                self.store.touch(self.current_id, now, seg, hop_ip, verdict.headline, verdict.explanation,
                                 verdict.confidence)
                self._last_touch = now
        elif verdict.kind in (KIND_HEALTHY, KIND_DEGRADED):
            self._bad = 0
            if self.current_id is not None:
                self._good += 1
                if self._first_good_ts is None:
                    self._first_good_ts = now
                if self._good >= self.close_after:
                    self.store.close_outage(self.current_id, self._first_good_ts)
                    self.current_id = None
                    self._good = 0
                    self._first_good_ts = None
                    self._changed()
        # unknown / measuring that is not a disconnect: hold the current state

    def _changed(self) -> None:
        if self.on_change:
            try:
                self.on_change()
            except Exception:
                pass

    def finish(self, now: float) -> None:
        """Clean exit with an outage still open: leave it open-ended; recover_interrupted() will mark it."""
        if self.current_id is not None:
            self.store.touch(self.current_id, now)


# ------------------------------------------------------------------------------ formatting / report

def fmt_duration(sec: float) -> str:
    s = int(round(sec))
    if s < 60:
        return f"{s} s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m} min {s:02d} s"
    h, m = divmod(m, 60)
    return f"{h} h {m:02d} min"


def fmt_time(ts: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


def segment_label(seg: str) -> str:
    return SEGMENT_NAMES.get(seg, "UNKNOWN")


def build_report(verdict: Optional[Verdict], snapshot: Optional[PathSnapshot], outages: List[Outage],
                 version: str, now: Optional[float] = None, max_outages: int = 15) -> str:
    """Plain-text report for a support call (ASCII only)."""
    now = now if now is not None else time.time()
    L: List[str] = []
    L.append(f"NetPulse network report (NetPulse {version})")
    L.append(f"Generated: {fmt_time(now)} local time")
    L.append("")
    if verdict is not None:
        L.append("CURRENT VERDICT")
        L.append(f"  {verdict.headline}")
        L.append(f"  {verdict.explanation}")
        L.append(f"  Confidence: {verdict.confidence}")
        L.append("")
    if snapshot is not None:
        L.append(f"PATH TO {snapshot.target} (probed once per second from this PC)")
        L.append(f"  {'Hop':<4}{'Segment':<10}{'Address':<17}{'Loss':>6}{'Avg':>10}{'Last':>10}")
        for h in snapshot.hops:
            if h.ttl < 1:
                continue
            st = h.stats(30)
            avg = f"{st.avg_rtt:.1f} ms" if st.avg_rtt is not None else "-"
            last = f"{st.last_rtt:.1f} ms" if st.last_rtt is not None else "-"
            addr = h.ip or "(no reply)"
            L.append(f"  {h.ttl:<4}{SEGMENT_NAMES.get(h.segment, h.segment):<10}{addr:<17}"
                     f"{st.loss_pct:>5.0f}%{avg:>10}{last:>10}")
        L.append("")
    if verdict is not None and verdict.evidence:
        L.append("EVIDENCE")
        for e in verdict.evidence[:12]:
            L.append(f"  - {e.text}")
        L.append("")
    L.append(f"RECENT OUTAGES (newest first, up to {max_outages})")
    if not outages:
        L.append("  none recorded")
    for o in outages[:max_outages]:
        tail = " (still ongoing)" if o.open else (" (end approximate: NetPulse was not running)" if o.interrupted else "")
        L.append(f"  {fmt_time(o.start_ts)}  lasted {fmt_duration(o.duration(now))}{tail}")
        L.append(f"      failing segment: {segment_label(o.segment)}"
                 + (f" at {o.hop_ip}" if o.hop_ip else "") + f" - {o.headline}")
    L.append("")
    L.append("Measured with ICMP echo from this PC only; no router or provider data was used.")
    return "\n".join(L)
