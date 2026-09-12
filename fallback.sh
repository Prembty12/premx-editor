#!/bin/bash
# ==============================================================================
# 🚀 OPENROUTER PURE BASH AGENT (GEMINI ARCHITECTURE & NON-BLOCKING PIPELINE)
# ==============================================================================

GRID_PATH="${GRID_PATH:-temp_frames/merged_60_grid_screenshot.jpg}"
SOURCE_DURATION="${SOURCE_DURATION:-60}"
INSIGHTS_SUMMARY="${INSIGHTS_SUMMARY:-}"
STYLE_PROMPT="${STYLE_PROMPT:-}"
PRIMARY_MODEL="${OPENROUTER_MODEL:-nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free}"
FALLBACK_MODEL="openrouter/free"

# 1. 🔑 Collect All Available OpenRouter Keys Natively
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

# 2. 🎯 Gemini-Style Key Rotation Function
get_random_openrouter_key() {
    local idx=$((RANDOM % ${#KEYS[@]}))
    echo "${KEYS[$idx]}"
}

# 3. ⚡ Fast Pure-Memory Base64 Conversion (No Overhead)
BASE64_IMAGE=$(python3 -c "import base64; print(base64.b64encode(open('$GRID_PATH', 'rb').read()).decode('utf-8'))")

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

# 4. 🔄 Gemini-Style Instant Execution Loop with Strict Hard Limits
for ((attempt=1; attempt<=MAX_RETRIES; attempt++)); do
    CURRENT_KEY=$(get_random_openrouter_key)
    KEY_DISPLAY="${CURRENT_KEY:0:8}..."
    
    # Attempt 1-2: Primary Model | Attempt 3-4: Fallback Model
    CURRENT_MODEL="$PRIMARY_MODEL"
    [ $attempt -gt 2 ] && CURRENT_MODEL="$FALLBACK_MODEL"
    
    echo "🤖 [$(date +%H:%M:%S)] OpenRouter Bash Attempt $attempt/$MAX_RETRIES | Model: $CURRENT_MODEL | Key: $KEY_DISPLAY" >&2
    
    PAYLOAD=$(python3 -c "
import json
print(json.dumps({
    'model': '$CURRENT_MODEL',
    'messages': [{
        'role': 'user',
        'content': [
            {'type': 'text', 'text': '''$PROMPT_TEXT'''},
            {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,$BASE64_IMAGE'}}
        ]
    }],
    'max_tokens': 256,
    'temperature': 0.4
}))
")

    # --connect-timeout 4 (Fast Handshake) | -m 8 (Hard Stop) | --line-buffered (Zero Lock)
    RESP=$(curl -s --line-buffered --connect-timeout 4 -m 8 -X POST "https://openrouter.ai/api/v1/chat/completions" \
        -H "Authorization: Bearer $CURRENT_KEY" \
        -H "Content-Type: application/json" \
        -d "$PAYLOAD")

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

# 5. 🧹 Ultra-Safe JSON Parser
RAW_RESPONSE="$RAW_RESPONSE" REQUESTED_MODEL="$SUCCESS_REQUESTED_MODEL" ROUTED_MODEL="$SUCCESS_ROUTED_MODEL" python3 - << 'EOF'
import os, json, re, ast

raw = os.environ.get('RAW_RESPONSE', '')
req_m = os.environ.get('REQUESTED_MODEL', '')
rout_m = os.environ.get('ROUTED_MODEL', '')

cleaned = re.sub(r'```json', '', raw, flags=re.IGNORECASE)
cleaned = re.sub(r'```', '', cleaned).strip()

match = re.search(r'\{.*?\}', cleaned, re.DOTALL)
target = match.group(0) if match else cleaned

try:
    try:
        data = json.loads(target)
    except:
        data = ast.literal_eval(target)

    title = data.get('title')
    start_time = data.get('start_time')
    duration = data.get('clip_duration', data.get('duration', 15))

    if title and start_time:
        dur_int = max(12, min(45, int(duration)))
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
except Exception as e:
    print(json.dumps({"status": "failed", "error": f"Parse error: {str(e)}"}))
EOF
