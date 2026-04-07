"""SQLite persistence for TokenPilot session state.

Stores file read records, tool usage, and session config.
State persists across hook subprocess calls via SQLite with WAL mode.
"""

import os
import sqlite3
import time

DB_PATH = os.environ.get(
    "TOKENPILOT_DB",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "tokenpilot.db"),
)

TOKENS_PER_LINE = 15
CHARS_PER_TOKEN = 4


def _connect():
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
    except sqlite3.DatabaseError:
        # Corrupt DB — delete and recreate
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
        conn = sqlite3.connect(DB_PATH, timeout=5)

    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=3000")
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
        CREATE INDEX IF NOT EXISTS idx_file_reads_path ON file_reads(path)
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tool_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tool_name TEXT NOT NULL,
            output_chars INTEGER DEFAULT 0,
            estimated_tokens INTEGER DEFAULT 0,
            timestamp REAL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_tool_usage_name ON tool_usage(tool_name)
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
    conn.execute("DELETE FROM file_reads")
    conn.execute("DELETE FROM tool_usage")
    conn.execute("DELETE FROM session")
    conn.execute("DELETE FROM stats")
    conn.execute("INSERT OR REPLACE INTO session VALUES ('level', ?)", (str(level),))
    conn.execute("INSERT OR REPLACE INTO session VALUES ('enabled', '1')")
    conn.execute("INSERT OR REPLACE INTO session VALUES ('start_time', ?)", (str(time.time()),))
    for key in ("total_prompts", "trivial", "research", "standard", "complex",
                "redundant_blocked", "tokens_saved"):
        conn.execute("INSERT OR REPLACE INTO stats VALUES (?, 0)", (key,))
    conn.commit()
    conn.close()


def is_enabled() -> bool:
    conn = _connect()
    row = conn.execute("SELECT value FROM session WHERE key='enabled'").fetchone()
    conn.close()
    return row[0] != "0" if row else True


def set_enabled(enabled: bool):
    conn = _connect()
    conn.execute("INSERT OR REPLACE INTO session VALUES ('enabled', ?)", ("1" if enabled else "0",))
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
    """Check if file was already read. Uses BEGIN IMMEDIATE for serializable isolation."""
    conn = _connect()
    conn.execute("BEGIN IMMEDIATE")
    try:
        rows = conn.execute(
            "SELECT offset_val, limit_val, estimated_tokens FROM file_reads WHERE path = ?",
            (path,),
        ).fetchall()

        if not rows:
            conn.commit()
            conn.close()
            return {"action": "allow", "message": "", "already_read": False, "previous_ranges": []}

        prev_ranges = [(r[0], r[1]) for r in rows]

        for r in rows:
            if r[0] == offset and r[1] == limit:
                conn.commit()
                conn.close()
                return {
                    "action": "warn",
                    "message": "File already read in full. Content is in context.",
                    "already_read": True,
                    "previous_ranges": prev_ranges,
                }

        for r in rows:
            if r[0] == 0 and r[1] == 0:
                conn.commit()
                conn.close()
                return {
                    "action": "warn",
                    "message": "Entire file already in context. Reference specific lines instead of re-reading.",
                    "already_read": True,
                    "previous_ranges": prev_ranges,
                }

        conn.commit()
        conn.close()
        return {
            "action": "allow",
            "message": f"Partial reads exist: {prev_ranges}",
            "already_read": False,
            "previous_ranges": prev_ranges,
        }
    except Exception:
        conn.rollback()
        conn.close()
        return {"action": "allow", "message": "", "already_read": False, "previous_ranges": []}


def record_blocked(estimated_tokens: int = 500):
    conn = _connect()
    conn.execute("UPDATE stats SET value = value + 1 WHERE key = 'redundant_blocked'")
    conn.execute("UPDATE stats SET value = value + ? WHERE key = 'tokens_saved'", (estimated_tokens,))
    conn.commit()
    conn.close()


def record_classification(category: str):
    conn = _connect()
    conn.execute("UPDATE stats SET value = value + 1 WHERE key = 'total_prompts'")
    if category in ("trivial", "research", "standard", "complex"):
        conn.execute("UPDATE stats SET value = value + 1 WHERE key = ?", (category,))
    conn.commit()
    conn.close()


def record_prompt_timestamp():
    """Record when a prompt was submitted for rapid-fire detection."""
    conn = _connect()
    conn.execute("INSERT OR REPLACE INTO session VALUES ('last_prompt_time', ?)", (str(time.time()),))
    # Track consecutive short prompts
    prev = conn.execute("SELECT value FROM session WHERE key='rapid_fire_count'").fetchone()
    count = int(prev[0]) if prev else 0
    conn.execute("INSERT OR REPLACE INTO session VALUES ('rapid_fire_count', ?)", (str(count + 1),))
    conn.commit()
    conn.close()


def reset_rapid_fire():
    conn = _connect()
    conn.execute("INSERT OR REPLACE INTO session VALUES ('rapid_fire_count', '0')")
    conn.commit()
    conn.close()


def get_rapid_fire_count() -> int:
    conn = _connect()
    row = conn.execute("SELECT value FROM session WHERE key='rapid_fire_count'").fetchone()
    conn.close()
    return int(row[0]) if row else 0


def get_prompt_count() -> int:
    conn = _connect()
    row = conn.execute("SELECT value FROM stats WHERE key='total_prompts'").fetchone()
    conn.close()
    return int(row[0]) if row else 0


def get_session_start_time() -> float:
    conn = _connect()
    row = conn.execute("SELECT value FROM session WHERE key='start_time'").fetchone()
    conn.close()
    return float(row[0]) if row else time.time()


# --- Project Brain ---

def record_project_note(note: str):
    """Store a user note for the project brain."""
    conn = _connect()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS brain_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            note TEXT NOT NULL,
            timestamp REAL
        )
    """)
    conn.execute("INSERT INTO brain_notes (note, timestamp) VALUES (?, ?)", (note, time.time()))
    conn.commit()
    conn.close()


def get_brain_notes() -> list[str]:
    conn = _connect()
    try:
        rows = conn.execute("SELECT note FROM brain_notes ORDER BY timestamp").fetchall()
    except sqlite3.OperationalError:
        rows = []
    conn.close()
    return [r[0] for r in rows]


# --- Tool usage tracking (Phase 2) ---

def record_tool_use(tool_name: str, output_chars: int = 0):
    estimated = max(1, output_chars // CHARS_PER_TOKEN)
    conn = _connect()
    conn.execute(
        "INSERT INTO tool_usage (tool_name, output_chars, estimated_tokens, timestamp) "
        "VALUES (?, ?, ?, ?)",
        (tool_name, output_chars, estimated, time.time()),
    )
    conn.commit()
    conn.close()


def get_tool_usage_report() -> dict:
    conn = _connect()
    rows = conn.execute("""
        SELECT tool_name,
               COUNT(*) as calls,
               SUM(estimated_tokens) as total_tokens,
               AVG(estimated_tokens) as avg_tokens
        FROM tool_usage
        GROUP BY tool_name
        ORDER BY total_tokens DESC
    """).fetchall()
    total = conn.execute("SELECT COALESCE(SUM(estimated_tokens), 0) FROM tool_usage").fetchone()[0]
    conn.close()

    tools = []
    for r in rows:
        tools.append({
            "tool": r[0],
            "calls": r[1],
            "total_tokens": r[2],
            "avg_tokens": round(r[3]),
        })

    return {
        "total_tool_tokens": total,
        "tool_count": len(tools),
        "tools": tools[:10],  # Top 10 most expensive
    }


# --- Context health tracking (Phase 4) ---

def get_estimated_context_usage() -> int:
    """Sum of all tracked token estimates (file reads + tool outputs)."""
    conn = _connect()
    file_tokens = conn.execute("SELECT COALESCE(SUM(estimated_tokens), 0) FROM file_reads").fetchone()[0]
    tool_tokens = conn.execute("SELECT COALESCE(SUM(estimated_tokens), 0) FROM tool_usage").fetchone()[0]
    conn.close()
    return file_tokens + tool_tokens


def get_context_health(context_limit: int = 200000) -> dict:
    used = get_estimated_context_usage()
    pct = min(100, round(used / context_limit * 100, 1))
    level = get_level()

    from config import get_level_config
    cfg = get_level_config(level)
    compact_at = cfg.compact_reminder_pct

    if pct >= compact_at:
        recommendation = "Run /compact now to free context space."
    elif pct >= compact_at - 15:
        recommendation = f"Approaching compact threshold ({compact_at}%). Consider /compact soon."
    else:
        recommendation = "Context is healthy."

    return {
        "estimated_tokens_used": used,
        "context_limit": context_limit,
        "usage_pct": pct,
        "compact_threshold_pct": compact_at,
        "recommendation": recommendation,
    }


# --- Stats ---

def get_stats() -> dict:
    conn = _connect()
    start_row = conn.execute("SELECT value FROM session WHERE key='start_time'").fetchone()
    level_row = conn.execute("SELECT value FROM session WHERE key='level'").fetchone()
    stat_rows = conn.execute("SELECT key, value FROM stats").fetchall()
    file_count = conn.execute("SELECT COUNT(DISTINCT path) FROM file_reads").fetchone()[0]
    total_reads = conn.execute("SELECT COUNT(*) FROM file_reads").fetchone()[0]
    total_file_tokens = conn.execute("SELECT COALESCE(SUM(estimated_tokens), 0) FROM file_reads").fetchone()[0]
    total_tool_tokens = conn.execute("SELECT COALESCE(SUM(estimated_tokens), 0) FROM tool_usage").fetchone()[0]
    tool_calls = conn.execute("SELECT COUNT(*) FROM tool_usage").fetchone()[0]
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
        "total_tool_calls": tool_calls,
        "redundant_reads_blocked": stats.get("redundant_blocked", 0),
        "estimated_file_tokens": total_file_tokens,
        "estimated_tool_tokens": total_tool_tokens,
        "estimated_total_tokens": total_file_tokens + total_tool_tokens,
        "estimated_tokens_saved": stats.get("tokens_saved", 0),
    }


def get_savings() -> dict:
    stats = get_stats()
    return {
        "tokens_saved_file_dedup": stats["estimated_tokens_saved"],
        "reads_blocked": stats["redundant_reads_blocked"],
        "estimated_total_tracked": stats["estimated_total_tokens"],
        "session_minutes": stats["session_minutes"],
    }


def get_file_report(path: str) -> dict:
    """Get read history for a specific file."""
    conn = _connect()
    rows = conn.execute(
        "SELECT offset_val, limit_val, line_count, estimated_tokens, timestamp FROM file_reads WHERE path = ?",
        (path,),
    ).fetchall()
    conn.close()

    if not rows:
        return {"path": path, "reads": 0, "message": "File not read this session."}

    reads = []
    for r in rows:
        reads.append({
            "offset": r[0], "limit": r[1], "lines": r[2],
            "tokens": r[3], "ago_seconds": round(time.time() - r[4]),
        })

    total_tokens = sum(r[3] for r in rows)
    return {
        "path": path,
        "reads": len(rows),
        "total_tokens": total_tokens,
        "history": reads,
    }
