#!/bin/bash
# TokenPilot: PostToolUse hook — tracks actual tool output size for real token measurement.

set -e

TOKENPILOT_DIR="$(dirname "$(dirname "$0")")"
INPUT=$(cat)

# Extract tool name and output size
TOOL_NAME=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_name',''))" 2>/dev/null || echo "")
OUTPUT_CHARS=$(echo "$INPUT" | python3 -c "
import sys, json
d = json.load(sys.stdin)
result = d.get('tool_result', '')
if isinstance(result, dict):
    result = json.dumps(result)
print(len(str(result)))
" 2>/dev/null || echo "0")

if [ -z "$TOOL_NAME" ] || [ "$OUTPUT_CHARS" = "0" ]; then
    exit 0
fi

# Record to SQLite (fire and forget — don't block Claude)
cd "$TOKENPILOT_DIR" && python3 -c "
import db
db.record_tool_use('$TOOL_NAME', $OUTPUT_CHARS)
" 2>/dev/null || true
