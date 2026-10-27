from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from backend.config import get_settings
from backend.utils.logging import get_logger

logger = get_logger(__name__)

# Reentrant: `execute()` holds the lock and then calls `get_connection()`,
# which takes the same lock again to initialise the schema on first use.
# A plain Lock would self-deadlock in any process that writes before init_db().
_write_lock = threading.RLock()
_initialized = False

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id             TEXT PRIMARY KEY,
    github_login   TEXT NOT NULL,
    github_name    TEXT,
    github_avatar  TEXT,
    access_token   TEXT NOT NULL,
    scope          TEXT,
    created_at     TEXT NOT NULL,
    expires_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS oauth_states (
    state      TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS scans (
    id            TEXT PRIMARY KEY,
    owner         TEXT NOT NULL,
    repo          TEXT NOT NULL,
    branch        TEXT,
    status        TEXT NOT NULL,
    progress      REAL NOT NULL DEFAULT 0,
    stages_json   TEXT,
    error         TEXT,
    error_details TEXT,
    started_at    TEXT,
    finished_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_scans_repo ON scans(owner, repo, started_at);

CREATE TABLE IF NOT EXISTS projects (
    owner         TEXT NOT NULL,
    repo          TEXT NOT NULL,
    full_name     TEXT NOT NULL,
    branch        TEXT NOT NULL,
    summary_json  TEXT NOT NULL,
    scanned_at    TEXT NOT NULL,
    file_count    INTEGER NOT NULL DEFAULT 0,
    is_wordpress  INTEGER NOT NULL DEFAULT 0,
    has_elementor INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (owner, repo)
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT,
    owner           TEXT NOT NULL,
    repo            TEXT NOT NULL,
    role            TEXT NOT NULL,
    content         TEXT NOT NULL,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_conv ON chat_messages(conversation_id);

CREATE TABLE IF NOT EXISTS analysis_results (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT,
    owner           TEXT NOT NULL,
    repo            TEXT NOT NULL,
    question        TEXT NOT NULL,
    result_json     TEXT NOT NULL,
    created_at      TEXT NOT NULL
);
"""


def database_path() -> Path:
    path = get_settings().sqlite_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_connection() -> sqlite3.Connection:
    global _initialized
    path = database_path()
    conn = sqlite3.connect(str(path), check_same_thread=False, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA busy_timeout=5000;")
    if not _initialized:
        with _write_lock:
            if not _initialized:
                conn.executescript(SCHEMA)
                conn.commit()
                _initialized = True
    return conn


def execute(sql: str, params: tuple | list = ()) -> None:
    with _write_lock, get_connection() as conn:
        conn.execute(sql, params)


def query_one(sql: str, params: tuple | list = ()) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute(sql, params).fetchone()


def query_all(sql: str, params: tuple | list = ()) -> list[sqlite3.Row]:
    with get_connection() as conn:
        return list(conn.execute(sql, params).fetchall())


def init_db() -> Path:
    path = database_path()
    with get_connection() as conn:
        conn.commit()
    logger.info("Database ready at %s", path)
    return path


def reset_initialized_flag() -> None:
    """Used by tests when the database file is swapped out."""
    global _initialized
    _initialized = False
