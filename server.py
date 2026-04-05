"""TokenPilot MCP Server — Token optimization for Claude Code.

Exposes tools for aggressiveness control, stats, savings, context health,
tool reports, and classifier debugging.
v2: Added tool tracking, context health, tool registry, classifier debug.
"""

import json
import sys
from fastmcp import FastMCP

from config import get_level_config, adaptive_thinking_cap, DEFAULT_LEVEL
from classifier import classify_task, classify_debug
from tool_registry import get_alternative
import db

mcp = FastMCP(
    "tokenpilot",
    instructions=(
        "TokenPilot optimizes token usage in Claude Code sessions. "
        "Use set_level to adjust aggressiveness (1=minimal, 10=maximum). "
        "Use get_stats for session metrics. Use get_savings for a savings report. "
        "Use get_context_health to check context window status. "
        "Use get_tool_report to see which tools cost the most tokens."
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
        "thinking_cap_base": cfg.thinking_cap_base or "unlimited",
        "compact_reminder_at": f"{cfg.compact_reminder_pct}%",
        "shell_truncate": f"{cfg.shell_truncate_lines} lines" if cfg.shell_truncate_lines else "off",
    })


@mcp.tool()
def get_stats() -> str:
    """Get current session token usage statistics.

    Shows: prompts processed, task categories, files read, tool calls,
    redundant reads blocked, estimated tokens consumed and saved.
    """
    return json.dumps(db.get_stats(), indent=2)


@mcp.tool()
def get_savings() -> str:
    """Get a summary of token savings this session."""
    return json.dumps(db.get_savings(), indent=2)


@mcp.tool()
def get_context_health() -> str:
    """Check context window health — estimated usage %, recommendation for /compact."""
    return json.dumps(db.get_context_health(), indent=2)


@mcp.tool()
def get_tool_report() -> str:
    """Show which tools consumed the most tokens this session.

    Lists top 10 tools by total token cost with call counts and averages.
    """
    return json.dumps(db.get_tool_usage_report(), indent=2)


@mcp.tool()
def get_file_report(path: str) -> str:
    """Show read history for a specific file — how many times read, tokens consumed."""
    return json.dumps(db.get_file_report(path), indent=2)


@mcp.tool()
def explain_classification(prompt: str) -> str:
    """Debug the classifier — show which patterns matched and why a prompt was classified."""
    return json.dumps(classify_debug(prompt), indent=2)


@mcp.tool()
def toggle(enabled: bool) -> str:
    """Turn TokenPilot on or off. When off, all hooks are bypassed (zero overhead)."""
    db.set_enabled(enabled)
    state = "ON" if enabled else "OFF"
    return json.dumps({"status": state, "message": f"TokenPilot is now {state}."})


@mcp.tool()
def reset_file_tracking() -> str:
    """Clear file read dedup tracking without resetting the full session."""
    conn = db._connect()
    conn.execute("DELETE FROM file_reads")
    conn.execute("UPDATE stats SET value = 0 WHERE key = 'redundant_blocked'")
    conn.commit()
    conn.close()
    return json.dumps({"status": "File tracking reset. Dedup cache cleared."})


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

        # Adaptive thinking cap
        cap = adaptive_thinking_cap(level, result["category"], result["confidence"])

        result["suggest"] = should_suggest
        result["level"] = level
        result["thinking_cap"] = cap
        print(json.dumps(result))

    elif cmd == "classify_debug":
        prompt = sys.argv[2] if len(sys.argv) > 2 else ""
        print(json.dumps(classify_debug(prompt), indent=2))

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

        # Check tool registry for cheaper alternative
        alt = get_alternative("Read")
        if alt and level >= 5:
            result["alternative"] = alt

        print(json.dumps(result))

    elif cmd == "record_read":
        path = sys.argv[2] if len(sys.argv) > 2 else ""
        offset = int(sys.argv[3]) if len(sys.argv) > 3 else 0
        limit = int(sys.argv[4]) if len(sys.argv) > 4 else 0
        lines = int(sys.argv[5]) if len(sys.argv) > 5 else 0
        db.record_read(path, offset, limit, lines)
        print(json.dumps({"status": "recorded"}))

    elif cmd == "record_tool":
        tool_name = sys.argv[2] if len(sys.argv) > 2 else ""
        output_chars = int(sys.argv[3]) if len(sys.argv) > 3 else 0
        db.record_tool_use(tool_name, output_chars)
        print(json.dumps({"status": "recorded"}))

    elif cmd == "context_health":
        print(json.dumps(db.get_context_health(), indent=2))

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
