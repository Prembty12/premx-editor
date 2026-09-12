#!/bin/bash
# ==============================================================================
# 🚀 OPENROUTER BASH AGENT (BULLETPROOF PARSER & FAILSAFE REGEX)
# ==============================================================================

GRID_PATH="${GRID_PATH:-temp_frames/merged_60_grid_screenshot.jpg}"
SOURCE_DURATION="${SOURCE_DURATION:-60}"
INSIGHTS_SUMMARY="${INSIGHTS_SUMMARY:-}"
STYLE_PROMPT="${STYLE_PROMPT:-}"
PRIMARY_MODEL="${OPENROUTER_MODEL:-nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free}"
FALLBACK_MODEL="openrouter/free"

# 1. 🔑 Collect OpenRouter Keys
KEYS=()
[ -n "$OPENROUTER_API_KEY" ] && KEYS+=("$OPENROUTER_API_KEY")
[ -n "$OPENROUTER_API_KEY_2" ] && KEYS+=("$OPENROUTER_API_KEY_2")
[ -n "$OPENROUTER_API_KEY_3" ] && KEYS+=("$OPENROUTER_API_KEY_3")
[ -n "$OPENROUTER_API_KEY_4" ] && KEYS+=("$OPENROUTER_API_KEY_4")
[ -n "$OPENROUTER_API_KEY_5" ] && KEYS+=("$OPENROUTER_API_KEY_5")

if [ ${#KEYS[@]} -eq 0 ]; then
    echo "{\"status\": \"failed\", \"error\": \"No OpenRouter API keys found\"}"
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

# 2. 🔄 Execution Loop with Temp File Payload
for ((attempt=1; attempt<=MAX_RETRIES; attempt++)); do
    CURRENT_KEY=$(get_random_openrouter_key)
    KEY_DISPLAY="${CURRENT_KEY:0:8}..."
    
    CURRENT_MODEL="$PRIMARY_MODEL"
    [ $attempt -gt 2 ] && CURRENT_MODEL="$FALLBACK_MODEL"
    
    echo "🤖 [$(date +%H:%M:%S)] OpenRouter Bash Attempt $attempt/$MAX_RETRIES | Model: $CURRENT_MODEL | Key: $KEY_DISPLAY" >&2
    
    PAYLOAD_FILE="temp_frames/or_payload.json"
    
    # Safe Base64 Encoding via File Buffer
    GRID_PATH="$GRID_PATH" CURRENT_MODEL="$CURRENT_MODEL" PROMPT_TEXT="$PROMPT_TEXT" PAYLOAD_FILE="$PAYLOAD_FILE" python3 - << 'EOF'
import os, json, base64

grid_path = os.environ.get('GRID_PATH')
model = os.environ.get('CURRENT_MODEL')
prompt = os.environ.get('PROMPT_TEXT')
payload_file = os.environ.get('PAYLOAD_FILE')

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
    'max_tokens': 256,
    'temperature': 0.4
}

with open(payload_file, 'w') as f:
    json.dump(payload, f)
EOF

    # Strict non-blocking cURL command
    RESP=$(curl -s -N --connect-timeout 4 -m 10 -X POST "https://openrouter.ai/api/v1/chat/completions" \
        -H "Authorization: Bearer $CURRENT_KEY" \
        -H "Content-Type: application/json" \
        -d @"$PAYLOAD_FILE")

    rm -f "$PAYLOAD_FILE"

    CONTENT=$(echo "$RESP" | python3 -c "import sys, json; res=json.load(sys.stdin); print(res.get('choices', [{}])[0].get('message', {}).get('content', '') or res.get('choices', [{}])[0].get('message', {}).get('reasoning', ''))" 2>/dev/null)
    ROUTED=$(echo "$RESP" | python3 -c "import sys, json; print(json.load(sys.stdin).get('model', ''))" 2>/dev/null)

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
    echo "{\"status\": \"failed\", \"error\": \"All OpenRouter attempts failed\"}"
    exit 1
fi

# 3. 🧹 Robust JSON Parser (Fixes Unterminated String Literals & Broken JSON)
RAW_RESPONSE="$RAW_RESPONSE" REQUESTED_MODEL="$SUCCESS_REQUESTED_MODEL" ROUTED_MODEL="$SUCCESS_ROUTED_MODEL" python3 - << 'EOF'
import os, json, re, ast

raw = os.environ.get('RAW_RESPONSE', '')
req_m = os.environ.get('REQUESTED_MODEL', '')
rout_m = os.environ.get('ROUTED_MODEL', '')

# Remove markdown syntax
cleaned = re.sub(r'```json', '', raw, flags=re.IGNORECASE)
cleaned = re.sub(r'```', '', cleaned).strip()

# Extract JSON object ignoring any preamble/reasoning text
match = re.search(r'\{.*\}', cleaned, re.DOTALL)
target = match.group(0) if match else cleaned

# Fix unescaped newlines inside strings and trailing commas
target = re.sub(r'(?<!\\)\n', ' ', target)
target = re.sub(r',\s*([\}\]])', r'\1', target)

data = None
try:
    data = json.loads(target)
except Exception:
    try:
        data = ast.literal_eval(target)
    except Exception:
        # Emergency Regex Extraction if string syntax is broken
        title_m = re.search(r'"title"\s*:\s*"(.*?)"', target)
        start_m = re.search(r'"start_time"\s*:\s*"(.*?)"', target)
        dur_m = re.search(r'"clip_duration"\s*:\s*(\d+)', target) or re.search(r'"duration"\s*:\s*(\d+)', target)
        
        if title_m and start_m:
            data = {
                "title": title_m.group(1),
                "start_time": start_m.group(1),
                "clip_duration": int(dur_m.group(1)) if dur_m else 15
            }

if data and isinstance(data, dict):
    title = data.get('title')
    start_time = data.get('start_time')
    duration = data.get('clip_duration', data.get('duration', 15))

    if title and start_time:
        try:
            dur_int = max(12, min(45, int(duration)))
        except:
            dur_int = 15

        print(json.dumps({
            "status": "success",
            "requested_model": req_m,
            "routed_model": rout_m,
            "title": str(title),
            "start_time": str(start_time),
            "duration": dur_int
        }))
    else:
        print(json.dumps({"status": "failed", "error": "Missing JSON keys"}))
else:
    print(json.dumps({"status": "failed", "error": "Unrepairable JSON response"}))
EOF
