"""SQLite access: outage log and lookup cache share one file under %LOCALAPPDATA%\\NetPulse."""

from __future__ import annotations

import sqlite3
import threading

SCHEMA_VERSION = 1

_DDL_V1 = """
CREATE TABLE IF NOT EXISTS outages (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    start_ts      REAL    NOT NULL,           -- epoch seconds, first failed probe
    end_ts        REAL,                       -- NULL while the outage is still open
    last_seen_ts  REAL    NOT NULL,           -- last time the app saw the outage still going
    segment       TEXT    NOT NULL,           -- pc | gateway | dish | internet | unknown
    hop_ip        TEXT,                       -- address of the first failing hop, when known
    target        TEXT,                       -- probe target at the time
    headline      TEXT    NOT NULL,
    explanation   TEXT,
    confidence    TEXT,
    interrupted   INTEGER NOT NULL DEFAULT 0, -- 1 = NetPulse stopped while the outage was open
    evidence_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_outages_start ON outages(start_ts);
CREATE TABLE IF NOT EXISTS ip_cache (
    ip         TEXT NOT NULL,
    source     TEXT NOT NULL,                 -- cymru | rdap | rdns
    fetched_ts REAL NOT NULL,
    expires_ts REAL NOT NULL,
    data_json  TEXT NOT NULL,
    PRIMARY KEY (ip, source)
);
CREATE TABLE IF NOT EXISTS kv (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    fetched_ts REAL NOT NULL
);
"""


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=10, check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    ver = conn.execute("PRAGMA user_version").fetchone()[0]
    if ver < 1:
        conn.executescript(_DDL_V1)
        conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
    return conn


class Database:
    """One connection guarded by a lock; fine for this app's tiny write volume."""

    def __init__(self, path: str):
        self.path = path
        self.lock = threading.RLock()
        self.conn = connect(path)

    def close(self) -> None:
        with self.lock:
            try:
                self.conn.close()
            except sqlite3.Error:
                pass
