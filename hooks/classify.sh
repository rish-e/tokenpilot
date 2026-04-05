#!/bin/bash
# TokenPilot: UserPromptSubmit hook — classifies the prompt and suggests effort level.
# Reads the hook input from stdin, extracts the prompt, runs classifier.

set -e

TOKENPILOT_DIR="$(dirname "$(dirname "$0")")"

# Check if TokenPilot is enabled
ENABLED=$(cd "$TOKENPILOT_DIR" && python3 -c "import db; print(db.is_enabled())" 2>/dev/null || echo "True")
[ "$ENABLED" = "False" ] && exit 0

INPUT=$(cat)

# Extract the user's prompt from hook input JSON
PROMPT=$(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('prompt',''))" 2>/dev/null || echo "")

if [ -z "$PROMPT" ]; then
    exit 0
fi

# Run classifier
RESULT=$(cd "$TOKENPILOT_DIR" && python3 server.py classify "$PROMPT" 2>/dev/null || echo '{}')

SUGGEST=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('suggest',False))" 2>/dev/null || echo "False")
CATEGORY=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('category','standard'))" 2>/dev/null || echo "standard")
EFFORT=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('effort','medium'))" 2>/dev/null || echo "medium")
MODEL=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('model_hint','sonnet'))" 2>/dev/null || echo "sonnet")

if [ "$SUGGEST" = "True" ]; then
    echo "[TokenPilot] Task: $CATEGORY | Suggested effort: $EFFORT | Model hint: $MODEL"
fi
