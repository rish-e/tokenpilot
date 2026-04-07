Run a TokenPilot command. TokenPilot optimizes token usage in Claude Code sessions.

Parse the argument: `$ARGUMENTS`

## Commands

- **`<1-10>`** (just a number) — Set aggressiveness level.
  - Call the `set_level` MCP tool from the `tokenpilot` server with the number.

- **`on`** — Enable TokenPilot. Call `toggle` with `enabled=true`.

- **`off`** — Disable TokenPilot. Call `toggle` with `enabled=false`.

- **`stats`** — Show session dashboard: level, prompts by category, files read, tool calls, tokens tracked, context health, and savings. Call `get_stats` and `get_context_health`, format as a clean summary.

- **`note <text>`** — Add a note to the Project Brain. Call `add_note` with the text.

- **`explain <prompt>`** — Debug the classifier. Call `explain_classification` with the prompt text.

- No argument or **`help`** — Show:
  ```
  /tp <1-10>           Set aggressiveness (0 = off)
  /tp on | off         Toggle TokenPilot
  /tp stats            Session dashboard
  /tp note <text>      Add note to Project Brain
  /tp explain <prompt> Debug classifier
  ```

## Rules

- Always call the TokenPilot MCP tools — do not simulate output.
- Keep responses short. Format stats as a clean table.
- If MCP server is not connected, tell the user to restart Claude Code.
