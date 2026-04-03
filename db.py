"""SQLite persistence for TokenPilot session state.

Stores file read records and session config so state persists
across separate Python process invocations (hooks run as subprocesses).
"""

import json
import os
import sqlite3
import time

DB_PATH = os.path.join(os.path.dirname(__file__), "tokenpilot.db")

TOKENS_PER_LINE = 15


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS session (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS file_reads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL,
            offset_val INTEGER DEFAULT 0,
            limit_val INTEGER DEFAULT 0,
            line_count INTEGER DEFAULT 0,
            estimated_tokens INTEGER DEFAULT 0,
            timestamp REAL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS stats (
            key TEXT PRIMARY KEY,
            value INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    return conn


def init_session(level: int = 4):
    conn = _connect()
    # Clear previous session data
    conn.execute("DELETE FROM file_reads")
    conn.execute("DELETE FROM session")
    conn.execute("DELETE FROM stats")
    conn.execute("INSERT OR REPLACE INTO session VALUES ('level', ?)", (str(level),))
    conn.execute("INSERT OR REPLACE INTO session VALUES ('start_time', ?)", (str(time.time()),))
    conn.execute("INSERT OR REPLACE INTO stats VALUES ('total_prompts', 0)")
    conn.execute("INSERT OR REPLACE INTO stats VALUES ('trivial', 0)")
    conn.execute("INSERT OR REPLACE INTO stats VALUES ('research', 0)")
    conn.execute("INSERT OR REPLACE INTO stats VALUES ('standard', 0)")
    conn.execute("INSERT OR REPLACE INTO stats VALUES ('complex', 0)")
    conn.execute("INSERT OR REPLACE INTO stats VALUES ('redundant_blocked', 0)")
    conn.execute("INSERT OR REPLACE INTO stats VALUES ('tokens_saved', 0)")
    conn.commit()
    conn.close()


def get_level() -> int:
    conn = _connect()
    row = conn.execute("SELECT value FROM session WHERE key='level'").fetchone()
    conn.close()
    return int(row[0]) if row else 4


def set_level(level: int):
    conn = _connect()
    conn.execute("INSERT OR REPLACE INTO session VALUES ('level', ?)", (str(level),))
    conn.commit()
    conn.close()


def record_read(path: str, offset: int = 0, limit: int = 0, line_count: int = 0):
    estimated = line_count * TOKENS_PER_LINE if line_count else 500
    conn = _connect()
    conn.execute(
        "INSERT INTO file_reads (path, offset_val, limit_val, line_count, estimated_tokens, timestamp) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (path, offset, limit, line_count, estimated, time.time()),
    )
    conn.commit()
    conn.close()


def check_file(path: str, offset: int = 0, limit: int = 0) -> dict:
    conn = _connect()
    rows = conn.execute(
        "SELECT offset_val, limit_val, estimated_tokens FROM file_reads WHERE path = ?",
        (path,),
    ).fetchall()
    conn.close()

    if not rows:
        return {"action": "allow", "message": "", "already_read": False, "previous_ranges": []}

    prev_ranges = [(r[0], r[1]) for r in rows]

    # Exact same range already read
    for r in rows:
        if r[0] == offset and r[1] == limit:
            return {
                "action": "warn",
                "message": f"File already read in full. Content is in context.",
                "already_read": True,
                "previous_ranges": prev_ranges,
            }

    # Full read covers any requested range
    for r in rows:
        if r[0] == 0 and r[1] == 0:
            return {
                "action": "warn",
                "message": "Entire file already in context. Reference specific lines instead of re-reading.",
                "already_read": True,
                "previous_ranges": prev_ranges,
            }

    return {
        "action": "allow",
        "message": f"Partial reads exist: {prev_ranges}",
        "already_read": False,
        "previous_ranges": prev_ranges,
    }


def record_blocked(estimated_tokens: int = 500):
    conn = _connect()
    conn.execute("UPDATE stats SET value = value + 1 WHERE key = 'redundant_blocked'")
    conn.execute("UPDATE stats SET value = value + ? WHERE key = 'tokens_saved'", (estimated_tokens,))
    conn.commit()
    conn.close()


def record_classification(category: str):
    conn = _connect()
    conn.execute("UPDATE stats SET value = value + 1 WHERE key = 'total_prompts'")
    conn.execute("UPDATE stats SET value = value + 1 WHERE key = ?", (category,))
    conn.commit()
    conn.close()


def get_stats() -> dict:
    conn = _connect()
    start_row = conn.execute("SELECT value FROM session WHERE key='start_time'").fetchone()
    level_row = conn.execute("SELECT value FROM session WHERE key='level'").fetchone()
    stat_rows = conn.execute("SELECT key, value FROM stats").fetchall()
    file_count = conn.execute("SELECT COUNT(DISTINCT path) FROM file_reads").fetchone()[0]
    total_reads = conn.execute("SELECT COUNT(*) FROM file_reads").fetchone()[0]
    total_file_tokens = conn.execute("SELECT COALESCE(SUM(estimated_tokens), 0) FROM file_reads").fetchone()[0]
    conn.close()

    stats = dict(stat_rows)
    start_time = float(start_row[0]) if start_row else time.time()
    elapsed = time.time() - start_time
    minutes = max(1, int(elapsed / 60))

    return {
        "session_minutes": minutes,
        "level": int(level_row[0]) if level_row else 4,
        "total_prompts": stats.get("total_prompts", 0),
        "classifications": {
            "trivial": stats.get("trivial", 0),
            "research": stats.get("research", 0),
            "standard": stats.get("standard", 0),
            "complex": stats.get("complex", 0),
        },
        "files_read": file_count,
        "total_reads": total_reads,
        "redundant_reads_blocked": stats.get("redundant_blocked", 0),
        "estimated_file_tokens": total_file_tokens,
        "estimated_tokens_saved": stats.get("tokens_saved", 0),
    }


def get_savings() -> dict:
    stats = get_stats()
    return {
        "tokens_saved_file_dedup": stats["estimated_tokens_saved"],
        "reads_blocked": stats["redundant_reads_blocked"],
        "session_minutes": stats["session_minutes"],
    }
