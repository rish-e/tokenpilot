"""TokenPilot MCP Server — Token optimization for Claude Code.

Exposes tools for aggressiveness control, stats, and savings reporting.
Internal functions are called by Claude Code hooks via CLI.
"""

import json
import sys
from fastmcp import FastMCP

from config import get_level_config, DEFAULT_LEVEL
from classifier import classify_task
import db

mcp = FastMCP(
    "tokenpilot",
    instructions=(
        "TokenPilot optimizes token usage in Claude Code sessions. "
        "Use set_level to adjust aggressiveness (1=minimal, 10=maximum). "
        "Use get_stats for session metrics. Use get_savings for a savings report."
    ),
)


@mcp.tool()
def set_level(level: int) -> str:
    """Set TokenPilot aggressiveness level (1-10).

    1-2: Minimal — notify only, no caps
    3-4: Conservative (default) — suggest effort on trivial tasks, warn on redundant reads
    5-6: Balanced — suggest effort on all tasks, warn with ranges, 20K thinking cap
    7-8: Aggressive — strong effort recommendations, block redundant reads, 12K thinking cap
    9-10: Maximum — enforce effort levels, block + auto-range reads, 8K thinking cap
    """
    level = max(1, min(10, level))
    db.set_level(level)
    cfg = get_level_config(level)
    return json.dumps({
        "level": level,
        "effort_suggest": cfg.effort_suggest,
        "file_dedup": cfg.file_dedup,
        "thinking_cap": cfg.thinking_cap or "unlimited",
        "compact_reminder_at": f"{cfg.compact_reminder_pct}%",
        "shell_truncate": f"{cfg.shell_truncate_lines} lines" if cfg.shell_truncate_lines else "off",
    })


@mcp.tool()
def get_stats() -> str:
    """Get current session token usage statistics.

    Shows: prompts processed, task categories, files read, redundant reads blocked,
    estimated tokens consumed and saved.
    """
    return json.dumps(db.get_stats(), indent=2)


@mcp.tool()
def get_savings() -> str:
    """Get a summary of token savings this session.

    Shows: tokens saved from file dedup, reads blocked, and optimization tips.
    """
    return json.dumps(db.get_savings(), indent=2)


# --- CLI interface for hooks ---

def cli():
    if len(sys.argv) < 2:
        print("Usage: python3 server.py <command> [args]")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "classify":
        prompt = sys.argv[2] if len(sys.argv) > 2 else ""
        result = classify_task(prompt)
        db.record_classification(result["category"])
        level = db.get_level()
        cfg = get_level_config(level)

        should_suggest = False
        if cfg.effort_suggest == "trivial_only" and result["category"] == "trivial":
            should_suggest = True
        elif cfg.effort_suggest in ("all", "strong", "enforce"):
            should_suggest = True

        result["suggest"] = should_suggest
        result["level"] = level
        print(json.dumps(result))

    elif cmd == "check_file":
        path = sys.argv[2] if len(sys.argv) > 2 else ""
        offset = int(sys.argv[3]) if len(sys.argv) > 3 else 0
        limit = int(sys.argv[4]) if len(sys.argv) > 4 else 0
        result = db.check_file(path, offset, limit)

        level = db.get_level()
        cfg = get_level_config(level)
        if result["already_read"]:
            if cfg.file_dedup in ("block", "block_autorange"):
                result["action"] = "block"
            elif cfg.file_dedup == "warn_range":
                result["action"] = "warn"

        print(json.dumps(result))

    elif cmd == "record_read":
        path = sys.argv[2] if len(sys.argv) > 2 else ""
        offset = int(sys.argv[3]) if len(sys.argv) > 3 else 0
        limit = int(sys.argv[4]) if len(sys.argv) > 4 else 0
        lines = int(sys.argv[5]) if len(sys.argv) > 5 else 0
        db.record_read(path, offset, limit, lines)
        print(json.dumps({"status": "recorded"}))

    elif cmd == "init":
        level = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_LEVEL
        db.init_session(level)
        cfg = get_level_config(level)
        print(json.dumps({
            "status": "initialized",
            "level": level,
            "compact_reminder_pct": cfg.compact_reminder_pct,
        }))

    else:
        print(json.dumps({"error": f"Unknown command: {cmd}"}))
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] != "serve":
        cli()
    else:
        mcp.run()
