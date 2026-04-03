"""Aggressiveness scale configuration for TokenPilot.

Levels 1-10 control how aggressively TokenPilot optimizes token usage.
Default: 4 (conservative-balanced).
"""

from dataclasses import dataclass

@dataclass
class LevelConfig:
    # Effort suggestion behavior
    effort_suggest: str          # "never", "trivial_only", "all", "strong", "enforce"
    # File read dedup behavior
    file_dedup: str              # "notify", "warn", "warn_range", "block", "block_autorange"
    # Shell compression (RTK handles this, we just set thresholds)
    shell_truncate_lines: int    # 0 = off, otherwise max lines before truncation
    # Thinking token cap (0 = no cap)
    thinking_cap: int
    # Context % at which to remind about /compact
    compact_reminder_pct: int

LEVELS: dict[int, LevelConfig] = {
    1:  LevelConfig("never",        "notify",         0,   0,     90),
    2:  LevelConfig("never",        "notify",         0,   0,     90),
    3:  LevelConfig("trivial_only", "warn",           200, 0,     75),
    4:  LevelConfig("trivial_only", "warn",           150, 0,     75),
    5:  LevelConfig("all",          "warn_range",     80,  20000, 65),
    6:  LevelConfig("all",          "warn_range",     80,  20000, 65),
    7:  LevelConfig("strong",       "block",          40,  12000, 55),
    8:  LevelConfig("strong",       "block",          40,  12000, 55),
    9:  LevelConfig("enforce",      "block_autorange", 20, 8000,  45),
    10: LevelConfig("enforce",      "block_autorange", 20, 8000,  45),
}

DEFAULT_LEVEL = 4

def get_level_config(level: int) -> LevelConfig:
    level = max(1, min(10, level))
    return LEVELS[level]
