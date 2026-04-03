# TokenPilot

Automatic token optimization for [Claude Code](https://claude.ai/code). Extends session duration by reducing wasted tokens across every dimension — effort tuning, redundant file reads, shell output noise, and smart task classification.

Built as a Claude Code hooks + MCP server system. Works alongside [RTK](https://github.com/rtk-ai/rtk) for shell compression and [MCP Compressor](https://github.com/atlassian-labs/mcp-compressor) for schema reduction.

## How It Works

TokenPilot runs as three layers:

1. **Hooks** — intercept Claude Code lifecycle events (session start, prompt submit, tool use) to inject optimization guidance
2. **MCP Server** — exposes tools for real-time control (`set_level`, `get_stats`, `get_savings`)
3. **SQLite Database** — persists session state across hook subprocess calls

```
┌── Claude Code Hooks ──────────────────────────────────┐
│                                                        │
│  SessionStart       → init session, inject hints       │
│  UserPromptSubmit   → classify task → suggest effort   │
│  PreToolUse (Read)  → detect redundant file reads      │
│                                                        │
└────────────────┬───────────────────────────────────────┘
                 │
    ┌────────────▼────────────┐
    │   TokenPilot MCP Server │
    │                         │
    │   set_level(1-10)       │  Aggressiveness dial
    │   get_stats()           │  Live session metrics
    │   get_savings()         │  Token savings report
    │                         │
    │   SQLite persistence    │  Cross-process state
    └─────────────────────────┘
```

## Aggressiveness Scale

Default: **4** (conservative-balanced). Adjustable 1-10 at any time.

| Level | Effort Suggestion | File Read Dedup | Thinking Cap | Compact Reminder |
|-------|-------------------|-----------------|-------------|-----------------|
| 1-2   | Never | Notify only | No cap | 90% context |
| 3-4   | Trivial tasks only | Warn on redundant | No cap | 75% context |
| 5-6   | All tasks | Warn + suggest ranges | 20K tokens | 65% context |
| 7-8   | Strong recommendation | Block re-reads | 12K tokens | 55% context |
| 9-10  | Enforce | Block + auto-range | 8K tokens | 45% context |

## Task Classifier

Lightweight regex + keyword classifier (no LLM calls, <10ms). Categories:

| Category | Effort | Model Hint | Example |
|----------|--------|-----------|---------|
| `trivial` | low | haiku | "fix typo in README" |
| `research` | medium | sonnet | "explain how the API routes work" |
| `standard` | medium | sonnet | "add a loading spinner" |
| `complex` | high | opus | "refactor auth across all microservices" |

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
          {
            "type": "command",
            "command": "~/MCPs/tokenpilot/hooks/session_start.sh",
            "timeout": 5
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "~/MCPs/tokenpilot/hooks/classify.sh",
            "timeout": 5
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Read",
        "hooks": [
          {
            "type": "command",
            "command": "~/MCPs/tokenpilot/hooks/check_read.sh",
            "timeout": 5
          }
        ]
      }
    ]
  },
  "mcpServers": {
    "tokenpilot": {
      "command": "python3",
      "args": ["~/MCPs/tokenpilot/server.py"],
      "env": {
        "PYTHONPATH": "~/MCPs/tokenpilot"
      }
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

### Optional: MCP Compressor for Schema Reduction

```bash
pip3 install mcp-compressor
```

Wraps heavy MCP servers to compress tool schemas by 70-97%.

## Usage

TokenPilot runs automatically after installation. You'll see `[TokenPilot]` messages:

- On trivial tasks: suggests switching to low effort / Haiku
- On redundant file reads: warns the file is already in context

### Slash Commands

Install the slash command for quick control:

```bash
cp ~/MCPs/tokenpilot/commands/tp.md ~/.claude/commands/tp.md
```

Then use in Claude Code:

| Command | What it does |
|---------|-------------|
| `/tp level 7` | Set aggressiveness to 7/10 |
| `/tp stats` | Show session metrics (prompts, files read, tokens) |
| `/tp savings` | Show tokens saved this session |
| `/tp status` | Show current config and classification breakdown |
| `/tp help` | List all commands |

### MCP Tools

You can also ask Claude directly to use these tools:

- **`set_level(5)`** — raise aggressiveness to 5/10
- **`get_stats()`** — see session metrics (prompts classified, files read, tokens estimated)
- **`get_savings()`** — see how many tokens were saved this session

### CLI (for testing)

```bash
cd ~/MCPs/tokenpilot

# Initialize session
python3 server.py init 4

# Classify a prompt
python3 server.py classify "fix typo in README"

# Record a file read
python3 server.py record_read "/src/app.py" 0 0 200

# Check if file was already read
python3 server.py check_file "/src/app.py" 0 0
```

## File Structure

```
tokenpilot/
├── server.py          # FastMCP server + CLI entry point
├── classifier.py      # Regex-based task classifier
├── config.py          # Aggressiveness scale definitions
├── tracker.py         # In-memory session tracker (used by MCP server process)
├── db.py              # SQLite persistence (used by hook subprocesses)
├── requirements.txt
├── commands/
│   └── tp.md              # /tp slash command (copy to ~/.claude/commands/)
├── hooks/
│   ├── session_start.sh    # SessionStart hook
│   ├── classify.sh         # UserPromptSubmit hook
│   └── check_read.sh       # PreToolUse (Read) hook
└── templates/
    └── claudeignore-default  # .claudeignore template for projects
```

## How Token Savings Stack

| Layer | What | Savings |
|-------|------|---------|
| TokenPilot classifier | Right effort level per task | Thinking token reduction |
| TokenPilot file dedup | Skip redundant file reads | ~2K tokens per blocked read |
| RTK | Compress shell output | 60-90% on Bash results |
| MCP Compressor | Compress MCP tool schemas | 70-97% per wrapped server |
| .claudeignore | Exclude build artifacts from search | 30-40% on exploration |

## License

MIT
