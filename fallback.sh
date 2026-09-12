#!/bin/bash
# ==============================================================================
# 🚀 OPENROUTER BASH AGENT (PURE AI RESPONSE - STRICT FAIL-SAFE)
# ==============================================================================
set -eo pipefail

GRID_PATH="${GRID_PATH:-temp_frames/merged_60_grid_screenshot.jpg}"
SOURCE_DURATION="${SOURCE_DURATION:-60}"
INSIGHTS_SUMMARY="${INSIGHTS_SUMMARY:-}"
STYLE_PROMPT="${STYLE_PROMPT:-}"
PRIMARY_MODEL="${OPENROUTER_MODEL:-nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free}"
FALLBACK_MODEL="openrouter/free"

# Unique run identifier to avoid race conditions
RUN_ID="$$_${RANDOM}"
PAYLOAD_FILE="temp_frames/or_payload_${RUN_ID}.json"
RESPONSE_FILE="temp_frames/or_response_${RUN_ID}.txt"

cleanup() {
    rm -f "$PAYLOAD_FILE" "$RESPONSE_FILE"
}
trap cleanup EXIT

# 1. 🔑 Collect OpenRouter Keys
declare -a KEYS=()
[ -n "$OPENROUTER_API_KEY" ] && KEYS+=("$OPENROUTER_API_KEY")
[ -n "$OPENROUTER_API_KEY_2" ] && KEYS+=("$OPENROUTER_API_KEY_2")
[ -n "$OPENROUTER_API_KEY_3" ] && KEYS+=("$OPENROUTER_API_KEY_3")
[ -n "$OPENROUTER_API_KEY_4" ] && KEYS+=("$OPENROUTER_API_KEY_4")
[ -n "$OPENROUTER_API_KEY_5" ] && KEYS+=("$OPENROUTER_API_KEY_5")

if [ ${#KEYS[@]} -eq 0 ]; then
    echo '{"status": "failed", "error": "No OpenRouter API keys found"}'
    exit 1
fi

if [ ! -f "$GRID_PATH" ]; then
    echo "{\"status\": \"failed\", \"error\": \"Grid image not found at $GRID_PATH\"}"
    exit 1
fi

get_random_openrouter_key() {
    local idx=$((RANDOM % ${#KEYS[@]}))
    echo "${KEYS[$idx]}"
}

PROMPT_TEXT="Analyze the provided 9:16 gaming screenshot grid. Total video source duration is ${SOURCE_DURATION} seconds.
Insights Context: ${INSIGHTS_SUMMARY}
Style Directive: ${STYLE_PROMPT}

Your primary job as an expert video editor is to find the most thrilling, high-action segment, skipping dull introductions.
Return a JSON object with EXACTLY three keys:
1. 'title' (string: viral title with 1-3 emojis)
2. 'start_time' (string format HH:MM:SS indicating exact peak action start time based on grid timestamps)
3. 'clip_duration' (integer: length between 12 and 45 seconds meeting monetization rules)
Return ONLY valid JSON format, no markdown wrapping."

RAW_RESPONSE=""
SUCCESS_REQUESTED_MODEL=""
SUCCESS_ROUTED_MODEL=""
MAX_RETRIES=4

mkdir -p temp_frames

# 2. 🔄 Attempt Loop
for ((attempt=1; attempt<=MAX_RETRIES; attempt++)); do
    CURRENT_KEY=$(get_random_openrouter_key)
    KEY_DISPLAY="${CURRENT_KEY:0:8}..."
    
    CURRENT_MODEL="$PRIMARY_MODEL"
    [ $attempt -gt 2 ] && CURRENT_MODEL="$FALLBACK_MODEL"
    
    echo "🤖 [$(date +%H:%M:%S)] OpenRouter Bash Attempt $attempt/$MAX_RETRIES | Model: $CURRENT_MODEL | Key: $KEY_DISPLAY" >&2
    
    export GRID_PATH CURRENT_MODEL PROMPT_TEXT PAYLOAD_FILE
    python3 - << 'EOF'
import os, json, base64

grid_path = os.environ['GRID_PATH']
model = os.environ['CURRENT_MODEL']
prompt = os.environ['PROMPT_TEXT']
payload_file = os.environ['PAYLOAD_FILE']

with open(grid_path, 'rb') as f:
    b64_img = base64.b64encode(f.read()).decode('utf-8')

payload = {
    'model': model,
    'messages': [{
        'role': 'user',
        'content': [
            {'type': 'text', 'text': prompt},
            {'type': 'image_url', 'image_url': {'url': f'data:image/jpeg;base64,{b64_img}'}}
        ]
    }],
    'max_tokens': 1024,
    'temperature': 0.4
}

with open(payload_file, 'w') as f:
    json.dump(payload, f)
EOF

    RESP=$(curl -s --connect-timeout 5 -m 45 -X POST "https://openrouter.ai/api/v1/chat/completions" \
        -H "Authorization: Bearer $CURRENT_KEY" \
        -H "Content-Type: application/json" \
        -d @"$PAYLOAD_FILE" || true)

    rm -f "$PAYLOAD_FILE"

    export RESP
    PARSED_OUT=$(python3 - << 'EOF'
import os, json

resp_raw = os.environ.get('RESP', '')
try:
    data = json.loads(resp_raw)
    choices = data.get('choices', [{}])[0]
    msg = choices.get('message', {})
    content = msg.get('content', '') or msg.get('reasoning', '')
    routed = data.get('model', '')
    print(json.dumps({'content': content, 'routed': routed}))
except Exception:
    print(json.dumps({'content': '', 'routed': ''}))
EOF
    )

    CONTENT=$(echo "$PARSED_OUT" | python3 -c "import sys, json; print(json.load(sys.stdin).get('content', ''))")
    ROUTED=$(echo "$PARSED_OUT" | python3 -c "import sys, json; print(json.load(sys.stdin).get('routed', ''))")

    if [ -n "$CONTENT" ] && [ "$CONTENT" != "None" ]; then
        RAW_RESPONSE="$CONTENT"
        SUCCESS_REQUESTED_MODEL="$CURRENT_MODEL"
        SUCCESS_ROUTED_MODEL="${ROUTED:-$CURRENT_MODEL}"
        echo "✅ [$(date +%H:%M:%S)] Success on Attempt $attempt! Routed Model: $SUCCESS_ROUTED_MODEL" >&2
        break
    else
        echo "⚠️ [$(date +%H:%M:%S)] Attempt $attempt failed or timed out. Rotating key instantly..." >&2
        sleep 1
    fi
done

if [ -z "$RAW_RESPONSE" ]; then
    echo '{"status": "failed", "error": "All OpenRouter attempts failed"}'
    exit 1
fi

# 3. 🧹 Pure AI Extraction with Strict Validation (Zero Defaults / Strict Fail)
printf "%s" "$RAW_RESPONSE" > "$RESPONSE_FILE"

export REQUESTED_MODEL="$SUCCESS_REQUESTED_MODEL" ROUTED_MODEL="$SUCCESS_ROUTED_MODEL" RESPONSE_FILE
python3 - << 'EOF'
import os, json, re, sys

response_file = os.environ.get('RESPONSE_FILE')
req_m = os.environ.get('REQUESTED_MODEL', '')
rout_m = os.environ.get('ROUTED_MODEL', '')

raw = ""
if response_file and os.path.exists(response_file):
    with open(response_file, 'r', encoding='utf-8') as f:
        raw = f.read()

title = None
start_time = None
duration = None

cleaned = re.sub(r'```json|```', '', raw).strip()

# 1. Direct JSON Extraction from AI Output
match = re.search(r'\{.*?\}', cleaned, re.DOTALL)
if match:
    try:
        data = json.loads(match.group(0))
        title = data.get('title')
        start_time = data.get('start_time')
        duration = data.get('clip_duration', data.get('duration'))
    except Exception:
        pass

# 2. Strict Fallback Regex (Only target explicit key-value strings from AI response)
if not title:
    title_match = re.search(r'["\']title["\']\s*:\s*["\']([^"\']+)["\']', cleaned)
    if title_match:
        title = title_match.group(1)

if not start_time:
    time_match = re.search(r'["\']start_time["\']\s*:\s*["\']([^"\']+)["\']', cleaned)
    if not time_match:
        time_match = re.search(r'\b(?:\d{2}:)?\d{2}:\d{2}\b', cleaned)
    if time_match:
        ts = time_match.group(1) if time_match.groups() else time_match.group(0)
        start_time = ts if ts.count(':') == 2 else f"00:{ts}"

if duration is None:
    dur_match = re.search(r'["\']clip_duration["\']\s*:\s*(\d+)', cleaned)
    if dur_match:
        duration = int(dur_match.group(1))

# 3. 🛑 STRICT GUARD: Agar Title, Start Time ya Duration missing / empty hain toh HARD FAIL
if not title or not str(title).strip() or not start_time or duration is None:
    error_data = {
        "status": "failed",
        "error": f"Incomplete AI response. Title={title}, StartTime={start_time}, Duration={duration}"
    }
    print(json.dumps(error_data))
    sys.exit(1)

try:
    dur_int = max(12, min(45, int(duration)))
except Exception:
    print(json.dumps({"status": "failed", "error": "Invalid clip_duration format"}))
    sys.exit(1)

print(json.dumps({
    "status": "success",
    "requested_model": req_m,
    "routed_model": rout_m,
    "title": str(title).strip(),
    "start_time": str(start_time).strip(),
    "duration": dur_int
}))
EOF
