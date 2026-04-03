#!/bin/bash
# TokenPilot: PreToolUse hook for Read tool — detects redundant file reads.

set -e

TOKENPILOT_DIR="$(dirname "$(dirname "$0")")"
INPUT=$(cat)

# Extract tool name
TOOL_NAME=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_name',''))" 2>/dev/null || echo "")

if [ "$TOOL_NAME" != "Read" ]; then
    exit 0
fi

FILE_PATH=$(echo "$INPUT" | python3 -c "import sys,json; i=json.load(sys.stdin).get('tool_input',{}); print(i.get('file_path',''))" 2>/dev/null || echo "")
OFFSET=$(echo "$INPUT" | python3 -c "import sys,json; i=json.load(sys.stdin).get('tool_input',{}); print(i.get('offset',0))" 2>/dev/null || echo "0")
LIMIT=$(echo "$INPUT" | python3 -c "import sys,json; i=json.load(sys.stdin).get('tool_input',{}); print(i.get('limit',0))" 2>/dev/null || echo "0")

if [ -z "$FILE_PATH" ]; then
    exit 0
fi

# Check if already read (uses SQLite for cross-process persistence)
RESULT=$(cd "$TOKENPILOT_DIR" && python3 server.py check_file "$FILE_PATH" "$OFFSET" "$LIMIT" 2>/dev/null || echo '{"action":"allow"}')

ACTION=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('action','allow'))" 2>/dev/null || echo "allow")
MESSAGE=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('message',''))" 2>/dev/null || echo "")

if [ "$ACTION" = "warn" ] && [ -n "$MESSAGE" ]; then
    echo "[TokenPilot] $MESSAGE"
elif [ "$ACTION" = "block" ] && [ -n "$MESSAGE" ]; then
    echo "[TokenPilot] BLOCKED: $MESSAGE"
fi

# Record the read
cd "$TOKENPILOT_DIR" && python3 server.py record_read "$FILE_PATH" "$OFFSET" "$LIMIT" 2>/dev/null || true
