# TokenPilot

Automatic token optimization for [Claude Code](https://claude.ai/code). Extends session duration by reducing wasted tokens across every dimension — effort tuning, redundant file reads, tool cost routing, context health tracking, and smart task classification.

Built as a Claude Code hooks + MCP server system. Works alongside [RTK](https://github.com/rtk-ai/rtk) for shell compression and [MCP Compressor](https://github.com/atlassian-labs/mcp-compressor) for schema reduction.

## How It Works

TokenPilot runs as four layers:

1. **Hooks** — intercept Claude Code lifecycle events (session start, prompt submit, pre/post tool use)
2. **MCP Server** — exposes tools for real-time control and monitoring
3. **SQLite Database** — persists session state across hook subprocess calls with WAL mode + serializable isolation
4. **Tool Registry** — maps known tools to estimated costs and cheaper alternatives

```
┌── Claude Code Hooks ──────────────────────────────────────┐
│                                                            │
│  SessionStart        → init session, inject hints          │
│  UserPromptSubmit    → classify task → suggest effort      │
│  PreToolUse (Read)   → dedup file reads + suggest cheaper  │
│  PostToolUse (all)   → track real tool output token costs  │
│                                                            │
└────────────────┬───────────────────────────────────────────┘
                 │
    ┌────────────▼──────────────────┐
    │   TokenPilot MCP Server       │
    │                               │
    │   set_level(1-10)             │  Aggressiveness dial
    │   get_stats()                 │  Live session metrics
    │   get_savings()               │  Token savings report
    │   get_context_health()        │  Context window status
    │   get_tool_report()           │  Most expensive tools
    │   get_file_report(path)       │  File read history
    │   explain_classification(p)   │  Debug classifier
    │   reset_file_tracking()       │  Clear dedup cache
    │                               │
    │   SQLite + Tool Registry      │  Persistent state
    └───────────────────────────────┘
```

## Aggressiveness Scale

Default: **4** (conservative-balanced). Adjustable 1-10 at any time via `/tp level N`.

| Level | Effort Suggestion | File Read Dedup | Thinking Cap | Compact Reminder |
|-------|-------------------|-----------------|-------------|-----------------|
| 1-2   | Never | Notify only | No cap | 90% context |
| 3-4   | Trivial tasks only | Warn on redundant | No cap | 75% context |
| 5-6   | All tasks | Warn + suggest alternatives | Adaptive (10-30K) | 65% context |
| 7-8   | Strong recommendation | Block re-reads | Adaptive (6-18K) | 55% context |
| 9-10  | Enforce | Block + auto-range | Adaptive (4-12K) | 45% context |

**Thinking caps are adaptive** — they scale based on task complexity and classifier confidence. A "trivial" task gets a tighter cap than a "complex" task. If the classifier is uncertain (confidence < 0.5), no cap is applied.

## Task Classifier (v2)

Lightweight regex + keyword classifier with negation detection, adjacency scoring, and quoted-code filtering. No LLM calls, <10ms execution.

| Category | Effort | Model Hint | Example |
|----------|--------|-----------|---------|
| `trivial` | low | haiku | "fix typo in README" |
| `research` | medium | sonnet | "explain how the API routes work" |
| `standard` | medium | sonnet | "add a loading spinner" |
| `complex` | high | opus | "refactor auth across all microservices" |

**v2 improvements:**
- **Negation detection**: "don't refactor" no longer matches the refactor pattern
- **Quoted-code filtering**: backtick-wrapped code is stripped before classification
- **Adjacency scoring**: "add auth to 12 routes" correctly detects complexity from keyword pairs
- **Confidence calibration**: very short prompts get low confidence (0.3) instead of false high confidence

Debug any classification with `/tp explain <prompt>`.

## Tool Cost Registry

TokenPilot knows the estimated token cost of common tools and suggests cheaper alternatives:

| Tool | Avg Tokens | Alternative | Alt Tokens | Savings |
|------|-----------|-------------|-----------|---------|
| Read | ~2000 | jCodeMunch symbol lookup | ~200 | 90% |
| WebSearch | ~2000 | Context7 docs query | ~800 | 60% |
| WebFetch | ~3000 | Context7 docs query | ~800 | 73% |

At level 5+, TokenPilot suggests alternatives when a cheaper tool could do the job.

## Installation

### Prerequisites

- Python 3.10+
- [Claude Code](https://claude.ai/code) CLI
- [FastMCP](https://github.com/jlowin/fastmcp) (`pip3 install fastmcp`)

### Setup

1. Clone to your MCPs directory:

```bash
git clone https://github.com/rish-e/tokenpilot.git ~/MCPs/tokenpilot
```

2. Install dependencies:

```bash
pip3 install -r ~/MCPs/tokenpilot/requirements.txt
```

3. Add hooks and MCP server to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          { "type": "command", "command": "~/MCPs/tokenpilot/hooks/session_start.sh", "timeout": 5 }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [
          { "type": "command", "command": "~/MCPs/tokenpilot/hooks/classify.sh", "timeout": 5 }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Read",
        "hooks": [
          { "type": "command", "command": "~/MCPs/tokenpilot/hooks/check_read.sh", "timeout": 5 }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": ".*",
        "hooks": [
          { "type": "command", "command": "~/MCPs/tokenpilot/hooks/post_tool.sh", "timeout": 3 }
        ]
      }
    ]
  },
  "mcpServers": {
    "tokenpilot": {
      "command": "python3",
      "args": ["~/MCPs/tokenpilot/server.py"],
      "env": { "PYTHONPATH": "~/MCPs/tokenpilot" }
    }
  }
}
```

4. Install the `/tp` slash command:

```bash
cp ~/MCPs/tokenpilot/commands/tp.md ~/.claude/commands/tp.md
```

5. Restart Claude Code.

### Optional: RTK for Shell Compression

```bash
brew install rtk-ai/tap/rtk
rtk init -g
```

Adds 60-90% token savings on shell output (build logs, test output, git).

## Usage

TokenPilot runs automatically after installation. You'll see `[TokenPilot]` messages when it detects optimization opportunities.

### Slash Commands

| Command | What it does |
|---------|-------------|
| `/tp level 7` | Set aggressiveness to 7/10 |
| `/tp stats` | Session metrics (prompts, files, tools, tokens) |
| `/tp savings` | Token savings report |
| `/tp context` | Context window health check |
| `/tp tools` | Most expensive tools ranked |
| `/tp explain <prompt>` | Debug why a prompt was classified a certain way |
| `/tp file <path>` | Read history for a specific file |
| `/tp reset` | Clear file dedup cache |
| `/tp status` | Quick overview |
| `/tp help` | List all commands |

### MCP Tools

All `/tp` commands map to MCP tools you can also call directly:

- `set_level(N)` — aggressiveness 1-10
- `get_stats()` — full session metrics
- `get_savings()` — savings report
- `get_context_health()` — context window status
- `get_tool_report()` — tool cost ranking
- `get_file_report(path)` — file read history
- `explain_classification(prompt)` — classifier debug
- `reset_file_tracking()` — clear dedup

### CLI (for testing)

```bash
cd ~/MCPs/tokenpilot

python3 server.py init 4                    # Initialize session
python3 server.py classify "fix typo"       # Classify prompt
python3 server.py classify_debug "fix typo" # Debug classification
python3 server.py check_file "/src/app.py"  # Check file dedup
python3 server.py context_health            # Context window status
```

## File Structure

```
tokenpilot/
├── server.py            # FastMCP server + CLI entry point
├── classifier.py        # Task classifier (v2: negation, adjacency, debug)
├── config.py            # Aggressiveness scale + adaptive thinking caps
├── db.py                # SQLite persistence (WAL, indexed, serializable)
├── tool_registry.py     # Tool cost estimates + cheaper alternatives
├── tracker.py           # In-memory tracker (used by MCP server process)
├── requirements.txt
├── commands/
│   └── tp.md            # /tp slash command (copy to ~/.claude/commands/)
├── hooks/
│   ├── session_start.sh # SessionStart hook
│   ├── classify.sh      # UserPromptSubmit hook
│   ├── check_read.sh    # PreToolUse (Read) hook
│   └── post_tool.sh     # PostToolUse (all tools) hook
└── templates/
    └── claudeignore-default
```

## How Token Savings Stack

| Layer | What | Savings |
|-------|------|---------|
| TokenPilot classifier | Right effort level per task | Thinking token reduction |
| TokenPilot file dedup | Skip redundant file reads | ~2K tokens per blocked read |
| TokenPilot tool routing | Suggest cheaper tool alternatives | 60-90% per substitution |
| TokenPilot PostToolUse | Track actual token costs (visibility) | Measurement enables optimization |
| RTK | Compress shell output | 60-90% on Bash results |
| MCP Compressor | Compress MCP tool schemas | 70-97% per wrapped server |
| .claudeignore | Exclude build artifacts from search | 30-40% on exploration |

## License

MIT
