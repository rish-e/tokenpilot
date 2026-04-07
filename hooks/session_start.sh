#!/bin/bash
# TokenPilot: SessionStart hook — initializes session tracking, injects optimization hints,
# and loads Project Brain context if available.

set -e

TOKENPILOT_DIR="$(dirname "$(dirname "$0")")"

# Initialize session with default level
RESULT=$(cd "$TOKENPILOT_DIR" && python3 server.py init 2>/dev/null || echo '{"level":4}')

LEVEL=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('level',4))" 2>/dev/null || echo "4")

echo "TokenPilot active (level $LEVEL/10). Optimizing token usage."
echo "Use jCodeMunch for code lookups. Use Context7 for docs. Use set_level() to adjust."

# Load Project Brain if it exists
BRAIN=$(cd "$TOKENPILOT_DIR" && python3 -c "
from brain import load_brain
content = load_brain()
if content:
    # Truncate to ~2000 chars to keep context lean
    if len(content) > 2000:
        content = content[:2000] + '\n... (truncated, use /tp brain to see full)'
    print(content)
" 2>/dev/null || true)

if [ -n "$BRAIN" ]; then
    echo ""
    echo "Project Brain loaded:"
    echo "$BRAIN"
fi
