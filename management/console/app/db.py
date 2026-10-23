"""SQLite storage for the ROS console.

SQLite is a deliberate choice, not a placeholder: a console for a few hundred
workstations is a read-mostly workload that fits in one file, and one file is
something a small IT team can actually back up and restore.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Any, Dict, Iterable, List, Optional

DB_PATH = os.environ.get("ROS_DB_PATH", os.path.join(os.path.dirname(__file__), "..", "ros.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS groups (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    policy      TEXT NOT NULL DEFAULT '{}',
    revision    INTEGER NOT NULL DEFAULT 1,
    is_default  INTEGER NOT NULL DEFAULT 0,
    created_at  INTEGER NOT NULL,
    updated_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS devices (
    id              TEXT PRIMARY KEY,
    hostname        TEXT NOT NULL,
    machine_id      TEXT NOT NULL UNIQUE,
    token_hash      TEXT NOT NULL,
    group_id        INTEGER REFERENCES groups(id) ON DELETE SET NULL,
    enrolled_at     INTEGER NOT NULL,
    last_seen       INTEGER,
    agent_version   TEXT NOT NULL DEFAULT '',
    policy_revision INTEGER NOT NULL DEFAULT 0,
    policy_status   TEXT NOT NULL DEFAULT 'pending',
    inventory       TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS applications (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    slug        TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    tagline     TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    category    TEXT NOT NULL DEFAULT 'Other',
    upstream    TEXT NOT NULL DEFAULT '',
    source      TEXT NOT NULL DEFAULT 'apt',
    reference   TEXT NOT NULL DEFAULT '',
    desktop_id  TEXT NOT NULL DEFAULT '',
    icon        TEXT NOT NULL DEFAULT 'application-x-executable-symbolic',
    published   INTEGER NOT NULL DEFAULT 1,
    created_at  INTEGER NOT NULL,
    updated_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT,
    ts        INTEGER NOT NULL,
    kind      TEXT NOT NULL,
    message   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token      TEXT PRIMARY KEY,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts DESC);
CREATE INDEX IF NOT EXISTS idx_applications_slug ON applications(slug);
CREATE INDEX IF NOT EXISTS idx_devices_group ON devices(group_id);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(default_policy: Dict[str, Any], catalogue: Optional[List[Dict[str, Any]]] = None) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    with connect() as conn:
        conn.executescript(SCHEMA)
        existing = conn.execute("SELECT COUNT(*) AS n FROM groups").fetchone()["n"]
        if not existing:
            now = int(time.time())
            conn.execute(
                "INSERT INTO groups (name, description, policy, revision, is_default,"
                " created_at, updated_at) VALUES (?, ?, ?, 1, 1, ?, ?)",
                (
                    "Default",
                    "Applied to every workstation that has not been assigned a group.",
                    json.dumps(default_policy),
                    now,
                    now,
                ),
            )

        # The catalogue is seeded once. After that it belongs to whoever runs
        # the console: an upgrade must not undo an edit or resurrect something
        # that was deliberately removed.
        if catalogue and not conn.execute(
            "SELECT COUNT(*) AS n FROM applications"
        ).fetchone()["n"]:
            now = int(time.time())
            for app in catalogue:
                conn.execute(
                    "INSERT INTO applications (slug, name, tagline, description,"
                    " category, upstream, source, reference, desktop_id, icon,"
                    " published, created_at, updated_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
                    (
                        app["slug"], app["name"], app.get("tagline", ""),
                        app.get("description", ""), app.get("category", "Other"),
                        app.get("upstream", ""), app.get("source", "apt"),
                        app.get("reference", ""), app.get("desktop_id", ""),
                        app.get("icon", "application-x-executable-symbolic"),
                        now, now,
                    ),
                )


# --------------------------------------------------------------------------- #
# Small helpers so routes never build SQL by hand
# --------------------------------------------------------------------------- #
def query(sql: str, params: Iterable[Any] = ()) -> List[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(sql, tuple(params)).fetchall()


def query_one(sql: str, params: Iterable[Any] = ()) -> Optional[sqlite3.Row]:
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: Iterable[Any] = ()) -> int:
    with connect() as conn:
        cur = conn.execute(sql, tuple(params))
        return cur.lastrowid


def log_event(kind: str, message: str, device_id: Optional[str] = None) -> None:
    execute(
        "INSERT INTO events (device_id, ts, kind, message) VALUES (?, ?, ?, ?)",
        (device_id, int(time.time()), kind, message),
    )


def get_setting(key: str, default: str = "") -> str:
    row = query_one("SELECT value FROM settings WHERE key = ?", (key,))
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    execute(
        "INSERT INTO settings (key, value) VALUES (?, ?)"
        " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
