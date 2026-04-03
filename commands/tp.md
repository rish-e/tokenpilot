Run a TokenPilot command. TokenPilot optimizes token usage in Claude Code sessions.

Parse the argument: `$ARGUMENTS`

## Commands

- **`level <1-10>`** — Set aggressiveness level. Default is 4.
  - 1-2: Minimal (notify only, no caps)
  - 3-4: Conservative (suggest effort on trivial tasks, warn on redundant reads)
  - 5-6: Balanced (suggest on all tasks, 20K thinking cap)
  - 7-8: Aggressive (block redundant reads, 12K thinking cap)
  - 9-10: Maximum (enforce effort levels, 8K thinking cap)
  - Call the `set_level` MCP tool from the `tokenpilot` server with the given number.

- **`stats`** — Show session token usage statistics.
  - Call the `get_stats` MCP tool from the `tokenpilot` server.
  - Display the results in a clean table format.

- **`savings`** — Show token savings report for this session.
  - Call the `get_savings` MCP tool from the `tokenpilot` server.
  - Display the results concisely.

- **`status`** — Show current TokenPilot configuration (level, what's enabled).
  - Call `get_stats` and format just the level and classification breakdown.

- No argument or **`help`** — Show available commands:
  - `/tp level <1-10>` — Set aggressiveness
  - `/tp stats` — Session metrics
  - `/tp savings` — Token savings report
  - `/tp status` — Current config

## Rules

- Always call the TokenPilot MCP tools — do not simulate or fake the output.
- Keep responses short and formatted as a clean summary.
- If the MCP server is not connected, tell the user to restart Claude Code.
