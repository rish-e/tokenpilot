#!/bin/bash
# TokenPilot: UserPromptSubmit hook — classifies prompt, detects rapid-fire,
# warns on peak hours, and suggests /compact when session is long.

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

# Run all checks in one Python call for speed
cd "$TOKENPILOT_DIR" && python3 -c "
import sys, json, time, db
from classifier import classify_task
from config import get_level_config

prompt = '''$PROMPT'''
result = classify_task(prompt)
db.record_classification(result['category'])
level = db.get_level()
cfg = get_level_config(level)

messages = []

# 1. Effort suggestion
should_suggest = False
if cfg.effort_suggest == 'trivial_only' and result['category'] == 'trivial':
    should_suggest = True
elif cfg.effort_suggest in ('all', 'strong', 'enforce'):
    should_suggest = True

if should_suggest:
    messages.append(f'Task: {result[\"category\"]} | Suggested effort: {result[\"effort\"]} | Model hint: {result[\"model_hint\"]}')

# 2. Rapid-fire detection (3+ short prompts in a row)
prompt_len = len(prompt.strip())
if prompt_len < 40:
    db.record_prompt_timestamp()
    count = db.get_rapid_fire_count()
    if count >= 3:
        messages.append('Multiple short prompts detected. Consider batching questions into one message to save tokens.')
        db.reset_rapid_fire()
else:
    db.reset_rapid_fire()

# 3. Session age warning (every 15 prompts)
total = db.get_prompt_count()
if total > 0 and total % 15 == 0:
    messages.append(f'{total} prompts this session. Consider /compact or starting a new session to reduce context cost.')

# 4. Peak hours warning (5-11am PT weekdays = 12:00-18:00 UTC)
import datetime
now_utc = datetime.datetime.now(datetime.timezone.utc)
weekday = now_utc.weekday()  # 0=Mon, 6=Sun
hour_utc = now_utc.hour
if weekday < 5 and 12 <= hour_utc < 18:
    # Only warn once per session
    from db import _connect
    conn = _connect()
    warned = conn.execute(\"SELECT value FROM session WHERE key='peak_warned'\").fetchone()
    conn.close()
    if not warned:
        messages.append('Peak hours active (limits burn faster). Consider deferring heavy work to off-peak.')
        conn = _connect()
        conn.execute(\"INSERT OR REPLACE INTO session VALUES ('peak_warned', '1')\")
        conn.commit()
        conn.close()

# Output all messages
for m in messages:
    print(f'[TokenPilot] {m}')
" 2>/dev/null || true
