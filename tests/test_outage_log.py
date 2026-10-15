"""Outage log: persistence across restart, interrupted recovery, tracker debounce, report text."""

import os

from core.rc.db import Database
from core.rc.model import KIND_HEALTHY, KIND_OUTAGE, Verdict
from core.rc.outages import OutageStore, OutageTracker, build_report, fmt_duration
from core.rc.verdict import VerdictEngine
from tests.fixture_loader import load_snapshot


def verdict(kind, ts, disconnect=False, segment="dish", since=None, headline="h"):
    return Verdict(kind, headline, "why", segment if disconnect else None, 2 if disconnect else None, "high", "r", [],
                   ts, since, disconnect)


def feed_seq(tracker, snap, seq, t0=1000.0):
    for i, (kind, disc) in enumerate(seq):
        tracker.feed(verdict(kind, t0 + i, disc, since=t0 + 1 if disc else None), snap)


def test_outage_opens_after_debounce_and_closes_after_recovery(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    store = OutageStore(db)
    tr = OutageTracker(store)
    snap = load_snapshot("sim_healthy.json")
    seq = [(KIND_HEALTHY, False)] * 3 + [(KIND_OUTAGE, True)] * 10 + [(KIND_HEALTHY, False)] * 5
    feed_seq(tr, snap, seq)
    rows = store.list()
    assert len(rows) == 1
    o = rows[0]
    assert o.segment == "dish" and not o.open
    assert o.start_ts == 1001.0                      # back-dated to the first failure
    assert o.end_ts == 1013.0                        # first successful update of the recovery
    assert o.duration() == 12.0


def test_single_blip_is_not_logged(tmp_path):
    store = OutageStore(Database(str(tmp_path / "t.db")))
    tr = OutageTracker(store)
    snap = load_snapshot("sim_healthy.json")
    feed_seq(tr, snap, [(KIND_HEALTHY, False), (KIND_OUTAGE, True), (KIND_HEALTHY, False)] * 3)
    assert store.list() == []


def test_history_survives_restart_and_open_outage_is_recovered(tmp_path):
    path = str(tmp_path / "np.db")
    db = Database(path)
    store = OutageStore(db)
    tr = OutageTracker(store)
    snap = load_snapshot("sim_healthy.json")
    # one finished outage, then one still open when the "app is killed"
    feed_seq(tr, snap, [(KIND_OUTAGE, True)] * 4 + [(KIND_HEALTHY, False)] * 4, t0=1000.0)
    feed_seq(tr, snap, [(KIND_OUTAGE, True)] * 8, t0=2000.0)
    assert len(store.list()) == 2 and store.list()[0].open
    db.conn.close()                                   # simulate kill: no clean shutdown
    db2 = Database(path)                              # relaunch
    store2 = OutageStore(db2)
    assert store2.recover_interrupted() == 1
    rows = store2.list()
    assert len(rows) == 2
    assert not rows[0].open and rows[0].interrupted and rows[0].end_ts == rows[0].last_seen_ts
    assert not rows[1].interrupted and rows[1].segment == "dish"


def test_db_lives_where_told_and_schema_is_versioned(tmp_path):
    db = Database(str(tmp_path / "x.db"))
    assert os.path.exists(tmp_path / "x.db")
    assert db.conn.execute("PRAGMA user_version").fetchone()[0] == 1
    tables = {r[0] for r in db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"outages", "ip_cache", "kv"} <= tables


def test_report_is_ascii_plain_text_with_verdict_path_and_outages(tmp_path):
    store = OutageStore(Database(str(tmp_path / "t.db")))
    tr = OutageTracker(store)
    snap = load_snapshot("sim_dish_outage.json")
    v = VerdictEngine().evaluate(snap)
    feed_seq(tr, snap, [(KIND_OUTAGE, True)] * 5 + [(KIND_HEALTHY, False)] * 4)
    text = build_report(v, snap, store.list(), "1.4.0", now=snap.ts)
    text.encode("ascii")                               # no smart punctuation, no ellipsis glyph
    assert "CURRENT VERDICT" in text and "PATH TO 1.1.1.1" in text and "RECENT OUTAGES" in text
    assert "failing segment: DISH" in text and "Dish is down" in text


def test_fmt_duration():
    assert fmt_duration(9) == "9 s" and fmt_duration(75) == "1 min 15 s" and fmt_duration(3720) == "1 h 02 min"
