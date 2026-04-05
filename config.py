"""Aggressiveness scale configuration for TokenPilot.

Levels 1-10 control how aggressively TokenPilot optimizes token usage.
Default: 4 (conservative-balanced).
v2: Adaptive thinking caps based on task category + confidence.
"""

from dataclasses import dataclass

@dataclass
class LevelConfig:
    effort_suggest: str          # "never", "trivial_only", "all", "strong", "enforce"
    file_dedup: str              # "notify", "warn", "warn_range", "block", "block_autorange"
    shell_truncate_lines: int    # 0 = off
    thinking_cap_base: int       # Base thinking cap (0 = no cap). Adjusted by adaptive_thinking_cap().
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


def adaptive_thinking_cap(level: int, category: str, confidence: float) -> int:
    """Compute thinking cap adjusted for task complexity and classifier confidence.

    Rules:
    - If base cap is 0 (levels 1-4), never cap.
    - If confidence < 0.5, don't cap (classifier is uncertain, don't risk restricting).
    - trivial tasks: cap at 50% of base (save the most).
    - research/standard: use base cap as-is.
    - complex tasks: cap at 150% of base (allow more thinking).
    """
    cfg = get_level_config(level)
    base = cfg.thinking_cap_base

    if base == 0:
        return 0  # No capping at this level

    if confidence < 0.5:
        return 0  # Uncertain — don't restrict

    multipliers = {
        "trivial": 0.5,
        "research": 1.0,
        "standard": 1.0,
        "complex": 1.5,
    }
    multiplier = multipliers.get(category, 1.0)
    return int(base * multiplier)
