Run a TokenPilot command. TokenPilot optimizes token usage in Claude Code sessions.

Parse the argument: `$ARGUMENTS`

## Commands

- **`level <1-10>`** — Set aggressiveness level.
  - Call the `set_level` MCP tool from the `tokenpilot` server with the given number.
  - Display the result as a clean summary.

- **`stats`** — Show session token usage statistics.
  - Call the `get_stats` MCP tool from the `tokenpilot` server.
  - Format as a clean table with: session time, level, prompts by category, files read, tool calls, tokens tracked, tokens saved.

- **`savings`** — Show token savings report.
  - Call the `get_savings` MCP tool from the `tokenpilot` server.

- **`context`** — Show context window health.
  - Call the `get_context_health` MCP tool from the `tokenpilot` server.
  - Show usage %, recommendation, and whether /compact is needed.

- **`tools`** — Show which tools cost the most tokens.
  - Call the `get_tool_report` MCP tool from the `tokenpilot` server.
  - Format as a ranked table: tool name, calls, total tokens, avg tokens.

- **`explain <prompt>`** — Debug the classifier on a specific prompt.
  - Call the `explain_classification` MCP tool from the `tokenpilot` server with the prompt text after "explain".
  - Show: category, confidence, matched patterns, negated patterns, adjacency score.

- **`file <path>`** — Show read history for a specific file.
  - Call the `get_file_report` MCP tool from the `tokenpilot` server with the file path.

- **`reset`** — Clear file dedup tracking without resetting the session.
  - Call the `reset_file_tracking` MCP tool from the `tokenpilot` server.

- **`on`** — Enable TokenPilot (all hooks active).
  - Call the `toggle` MCP tool from the `tokenpilot` server with `enabled=true`.

- **`off`** — Disable TokenPilot (all hooks bypass, zero overhead).
  - Call the `toggle` MCP tool from the `tokenpilot` server with `enabled=false`.

- **`status`** — Quick overview of current config.
  - Call `get_stats` and format just: level, session time, total prompts, total tracked tokens.

- No argument or **`help`** — Show available commands:
  ```
  /tp on               Enable TokenPilot
  /tp off              Disable TokenPilot
  /tp level <1-10>     Set aggressiveness
  /tp stats            Session metrics
  /tp savings          Token savings report
  /tp context          Context window health
  /tp tools            Most expensive tools
  /tp explain <prompt> Debug classifier
  /tp file <path>      File read history
  /tp reset            Clear file dedup cache
  /tp status           Quick overview
  ```

## Rules

- Always call the TokenPilot MCP tools — do not simulate or fake the output.
- Keep responses short and formatted as a clean summary.
- If the MCP server is not connected, tell the user to restart Claude Code.
