#!/bin/bash
# TokenPilot: SessionStart hook — initializes session tracking and injects optimization hints.

set -e

TOKENPILOT_DIR="$(dirname "$(dirname "$0")")"

# Initialize session with default level
RESULT=$(cd "$TOKENPILOT_DIR" && python3 server.py init 2>/dev/null || echo '{"level":4}')

LEVEL=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('level',4))" 2>/dev/null || echo "4")

echo "TokenPilot active (level $LEVEL/10). Optimizing token usage."
echo "Use jCodeMunch for code lookups. Use Context7 for docs. Use set_level() to adjust."
