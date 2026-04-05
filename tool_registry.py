"""Tool cost registry for TokenPilot.

Maps known tools to estimated per-call token costs and cheaper alternatives.
Used by PreToolUse hooks to suggest or enforce cheaper tool choices.
"""

TOOL_COSTS = {
    # Built-in tools
    "Read": {
        "avg_tokens": 2000,
        "description": "Full file read",
        "alternative": "mcp__jcodemunch__get_symbol",
        "alt_description": "jCodeMunch symbol lookup (~200 tokens)",
        "alt_when": "Looking up a specific function/class (not reading entire file)",
    },
    "Grep": {
        "avg_tokens": 500,
        "description": "Content search",
        "alternative": None,
    },
    "Glob": {
        "avg_tokens": 300,
        "description": "File pattern search",
        "alternative": None,
    },
    "Bash": {
        "avg_tokens": 1500,
        "description": "Shell command (RTK compresses output)",
        "alternative": None,
    },
    "Agent": {
        "avg_tokens": 5000,
        "description": "Subagent delegation (separate context)",
        "alternative": None,
    },
    "WebSearch": {
        "avg_tokens": 2000,
        "description": "Web search",
        "alternative": "mcp__context7__query-docs",
        "alt_description": "Context7 docs lookup (~800 tokens)",
        "alt_when": "Looking up library/framework documentation",
    },
    "WebFetch": {
        "avg_tokens": 3000,
        "description": "Fetch web page",
        "alternative": "mcp__context7__query-docs",
        "alt_description": "Context7 docs lookup (~800 tokens)",
        "alt_when": "Fetching library documentation pages",
    },

    # MCP tools (cheaper alternatives)
    "mcp__jcodemunch__get_symbol": {
        "avg_tokens": 200,
        "description": "AST symbol lookup",
        "alternative": None,
    },
    "mcp__jcodemunch__search_symbols": {
        "avg_tokens": 300,
        "description": "Symbol search",
        "alternative": None,
    },
    "mcp__context7__query-docs": {
        "avg_tokens": 800,
        "description": "On-demand docs fetch",
        "alternative": None,
    },
}


def get_tool_cost(tool_name: str) -> dict | None:
    """Get cost info for a tool. Returns None if unknown."""
    return TOOL_COSTS.get(tool_name)


def get_alternative(tool_name: str) -> dict | None:
    """Get cheaper alternative for a tool, if one exists."""
    info = TOOL_COSTS.get(tool_name)
    if not info or not info.get("alternative"):
        return None

    alt_name = info["alternative"]
    alt_info = TOOL_COSTS.get(alt_name, {})
    return {
        "current_tool": tool_name,
        "current_avg_tokens": info["avg_tokens"],
        "alternative": alt_name,
        "alt_avg_tokens": alt_info.get("avg_tokens", 0),
        "alt_description": info.get("alt_description", ""),
        "alt_when": info.get("alt_when", ""),
        "savings": info["avg_tokens"] - alt_info.get("avg_tokens", 0),
    }
