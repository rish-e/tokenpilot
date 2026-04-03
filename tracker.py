"""Session-level file read tracking and token estimation.

Maintains an in-memory cache of files read during the current session,
plus estimated token counts for savings reporting.
"""

import time
from dataclasses import dataclass, field

# Rough estimate: ~4 chars per token for code files
CHARS_PER_TOKEN = 4
# Average tokens per line of code
TOKENS_PER_LINE = 15


@dataclass
class ReadRecord:
    path: str
    offset: int        # 0 = from start
    limit: int         # 0 = entire file
    timestamp: float
    estimated_tokens: int


@dataclass
class SessionTracker:
    level: int = 4
    start_time: float = field(default_factory=time.time)

    # File read tracking
    reads: list[ReadRecord] = field(default_factory=list)
    redundant_reads_blocked: int = 0
    redundant_tokens_saved: int = 0

    # Aggregate stats
    total_file_tokens: int = 0
    total_prompts: int = 0
    classifications: dict = field(default_factory=lambda: {
        "trivial": 0, "research": 0, "standard": 0, "complex": 0
    })

    def record_read(self, path: str, offset: int = 0, limit: int = 0,
                    line_count: int = 0) -> None:
        estimated = line_count * TOKENS_PER_LINE if line_count else 500
        self.reads.append(ReadRecord(
            path=path, offset=offset, limit=limit,
            timestamp=time.time(), estimated_tokens=estimated,
        ))
        self.total_file_tokens += estimated

    def check_file(self, path: str, offset: int = 0, limit: int = 0) -> dict:
        """Check if a file (or range) has already been read.

        Returns:
            action: "allow" | "warn" | "block"
            message: human-readable guidance
            already_read: bool
            previous_ranges: list of (offset, limit) tuples
        """
        previous = [r for r in self.reads if r.path == path]
        if not previous:
            return {"action": "allow", "message": "", "already_read": False,
                    "previous_ranges": []}

        prev_ranges = [(r.offset, r.limit) for r in previous]

        # Check if the exact same range was already read
        for r in previous:
            if r.offset == offset and r.limit == limit:
                return {
                    "action": "warn",
                    "message": f"File already read in full (turn {self.reads.index(r)+1}). Content is in context.",
                    "already_read": True,
                    "previous_ranges": prev_ranges,
                }

        # Check if a full read covers the requested range
        for r in previous:
            if r.offset == 0 and r.limit == 0:
                return {
                    "action": "warn",
                    "message": f"Entire file already in context. Consider referencing specific lines instead of re-reading.",
                    "already_read": True,
                    "previous_ranges": prev_ranges,
                }

        # Partial overlap — suggest the unread range
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
            return "Consider using jCodeMunch for targeted code lookups instead of reading full files."
        if self.classifications.get("complex", 0) > 3:
            return "Many complex tasks this session. Consider /compact to free up context."
        return "TokenPilot is running. Use set_level(N) to adjust aggressiveness (1-10)."


# Global session tracker (one per MCP server process = one per Claude Code session)
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
