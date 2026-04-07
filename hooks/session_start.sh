#!/bin/bash
# TokenPilot: SessionStart hook — auto-saves previous session brain,
# bootstraps brain for new projects, loads brain into context.

set -e

TOKENPILOT_DIR="$(dirname "$(dirname "$0")")"

# Auto-save previous session brain BEFORE resetting
cd "$TOKENPILOT_DIR" && python3 -c "
from brain import auto_save
result = auto_save()
if result.get('status') == 'bootstrapped':
    print('[TokenPilot] Project Brain created from git history.')
elif result.get('status') == 'updated':
    print('[TokenPilot] Previous session saved to brain.')
" 2>/dev/null || true

# Initialize new session
RESULT=$(cd "$TOKENPILOT_DIR" && python3 server.py init 2>/dev/null || echo '{"level":4}')
LEVEL=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('level',4))" 2>/dev/null || echo "4")

echo "TokenPilot active (level $LEVEL/10)."

# Load brain into context
BRAIN=$(cd "$TOKENPILOT_DIR" && python3 -c "
from brain import load_brain
content = load_brain()
if content:
    if len(content) > 2000:
        content = content[:2000] + '\n...(truncated)'
    print(content)
" 2>/dev/null || true)

if [ -n "$BRAIN" ]; then
    echo ""
    echo "$BRAIN"
fi
