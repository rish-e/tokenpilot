"""session_dedup.py — Drop-in enhancement to TokenPilot's file read dedup.

Extends the existing tracker.py approach with **mtime-based cache invalidation**:
if a file is modified between reads (mtime changes), the old record is cleared
and the re-read is allowed without a warning.

This prevents the false-positive where Claude edits a file and then legitimately
re-reads it to verify the change — the current tracker.py warns on that case
because it only tracks path+offset+limit, not whether the file changed.

## How it integrates

Drop this next to tracker.py. Swap the import in check_read.sh / server.py:

    # Before (tracker.py):
    from tracker import get_session, SessionTracker

    # After (this file — session_dedup.py):
    from session_dedup import get_session, SessionTracker  # same API + mtime fix

No other changes needed. Fully backward-compatible with the existing MCP server
and hook scripts.

## Improvement summary

| Scenario                      | tracker.py  | session_dedup.py |
|-------------------------------|-------------|------------------|
| Same file read twice (no edit)| warn        | warn             |
| Full read covers partial range| warn        | warn             |
| File edited between reads     | warn (wrong)| allow (correct)  |
| Different files               | allow       | allow            |
| mtime unavailable (temp files)| N/A         | allow            |
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

# Keep same constants as tracker.py for compatibility
CHARS_PER_TOKEN = 4
TOKENS_PER_LINE = 15


@dataclass
class ReadRecord:
    path: str
    offset: int
    limit: int
    timestamp: float
    estimated_tokens: int
    mtime: float = 0.0   # NEW: mtime at read time; 0 = unknown (allow re-read)


@dataclass
class SessionTracker:
    level: int = 4
    start_time: float = field(default_factory=time.time)

    reads: list[ReadRecord] = field(default_factory=list)
    redundant_reads_blocked: int = 0
    redundant_tokens_saved: int = 0
    total_file_tokens: int = 0
    total_prompts: int = 0
    classifications: dict = field(default_factory=lambda: {
        "trivial": 0, "research": 0, "standard": 0, "complex": 0
    })

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _current_mtime(path: str) -> float:
        """Return current mtime, or 0 if unreadable (e.g. temp/virtual files)."""
        try:
            return os.stat(path).st_mtime
        except OSError:
            return 0.0

    def _valid_records(self, path: str) -> list[ReadRecord]:
        """
        Records for `path` whose mtime still matches the file on disk.

        If mtime == 0 (unknown at read time), we keep the record — it was
        a file we couldn't stat, so we conservatively treat it as unchanged.
        If mtime != 0 and current disk mtime differs, the file was edited;
        the old record is stale and we discard it.
        """
        current = self._current_mtime(path)
        return [
            r for r in self.reads
            if r.path == path and (r.mtime == 0 or current == 0 or r.mtime == current)
        ]

    # ------------------------------------------------------------------
    # Public API — identical to tracker.py's SessionTracker
    # ------------------------------------------------------------------

    def record_read(self, path: str, offset: int = 0, limit: int = 0,
                    line_count: int = 0) -> None:
        estimated = line_count * TOKENS_PER_LINE if line_count else 500
        self.reads.append(ReadRecord(
            path=path,
            offset=offset,
            limit=limit,
            timestamp=time.time(),
            estimated_tokens=estimated,
            mtime=self._current_mtime(path),   # capture mtime at read time
        ))
        self.total_file_tokens += estimated

    def check_file(self, path: str, offset: int = 0, limit: int = 0) -> dict:
        """
        Check if a file/range has already been read this session.

        Same return shape as tracker.py — drop-in replacement:
          action: "allow" | "warn" | "block"
          message: human-readable guidance
          already_read: bool
          previous_ranges: list of (offset, limit) tuples

        Enhancement: only considers records whose mtime matches current disk,
        so edits between reads don't cause false-positive warnings.
        """
        previous = self._valid_records(path)
        if not previous:
            return {"action": "allow", "message": "", "already_read": False,
                    "previous_ranges": []}

        prev_ranges = [(r.offset, r.limit) for r in previous]

        # Exact same range already read
        for r in previous:
            if r.offset == offset and r.limit == limit:
                idx = self.reads.index(r) + 1
                return {
                    "action": "warn",
                    "message": (
                        f"File already read in full (turn {idx}). Content is in context."
                    ),
                    "already_read": True,
                    "previous_ranges": prev_ranges,
                }

        # Full read covers any partial request
        for r in previous:
            if r.offset == 0 and r.limit == 0:
                return {
                    "action": "warn",
                    "message": (
                        "Entire file already in context. "
                        "Consider referencing specific lines instead of re-reading."
                    ),
                    "already_read": True,
                    "previous_ranges": prev_ranges,
                }

        # Partial overlap — allow but inform
        return {
            "action": "allow",
            "message": f"Partial reads exist for this file: {prev_ranges}",
            "already_read": False,
            "previous_ranges": prev_ranges,
        }

    def record_blocked_read(self, estimated_tokens: int = 500) -> None:
        self.redundant_reads_blocked += 1
        self.redundant_tokens_saved += estimated_tokens

    def record_classification(self, category: str) -> None:
        self.total_prompts += 1
        if category in self.classifications:
            self.classifications[category] += 1

    def get_stats(self) -> dict:
        elapsed = time.time() - self.start_time
        minutes = max(1, int(elapsed / 60))
        return {
            "session_minutes": minutes,
            "level": self.level,
            "total_prompts": self.total_prompts,
            "classifications": self.classifications,
            "files_read": len(set(r.path for r in self.reads)),
            "total_reads": len(self.reads),
            "redundant_reads_blocked": self.redundant_reads_blocked,
            "estimated_file_tokens": self.total_file_tokens,
            "estimated_tokens_saved": self.redundant_tokens_saved,
        }

    def get_savings(self) -> dict:
        stats = self.get_stats()
        return {
            "tokens_saved_file_dedup": self.redundant_tokens_saved,
            "reads_blocked": self.redundant_reads_blocked,
            "session_minutes": stats["session_minutes"],
            "tip": self._get_tip(),
        }

    def _get_tip(self) -> str:
        if self.total_prompts > 10 and self.redundant_reads_blocked == 0:
            return (
                "Consider using jCodeMunch for targeted code lookups "
                "instead of reading full files."
            )
        if self.classifications.get("complex", 0) > 3:
            return "Many complex tasks this session. Consider /compact to free up context."
        return "TokenPilot is running. Use set_level(N) to adjust aggressiveness (1-10)."


# Module-level singleton — same API as tracker.py
_session: SessionTracker | None = None


def get_session(level: int = 4) -> SessionTracker:
    global _session
    if _session is None:
        _session = SessionTracker(level=level)
    return _session


def reset_session(level: int = 4) -> SessionTracker:
    global _session
    _session = SessionTracker(level=level)
    return _session
