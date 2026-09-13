#!/bin/bash
# ==============================================================================
# 🚀 OPENROUTER BASH AGENT (WITH RAW AI RESPONSE LOGGING)
# ==============================================================================

GRID_PATH="${GRID_PATH:-temp_frames/merged_60_grid_screenshot.jpg}"
SOURCE_DURATION="${SOURCE_DURATION:-60}"
INSIGHTS_SUMMARY="${INSIGHTS_SUMMARY:-}"
STYLE_PROMPT="${STYLE_PROMPT:-}"

PRIMARY_MODEL="${OPENROUTER_MODEL:-nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free}"
FALLBACK_MODEL="openrouter/free"

# 1. 🔑 Collect OpenRouter Keys Safely
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
1. 'title' (string: ONLY THE SINGLE VIRAL TITLE under 6 words based on visuals with 1-3 emojis creating curiosity and engagement strictly NO generic words like Epic Insane Crazy Best or Gameplay)
2. 'start_time' (string format HH:MM:SS indicating exact peak action start time based on grid timestamps)
3. 'clip_duration' (integer: length between 12 and 45 seconds meeting monetization rules)
Return ONLY valid JSON format, no markdown wrapping."

RAW_RESPONSE=""
SUCCESS_REQUESTED_MODEL=""
SUCCESS_ROUTED_MODEL=""
MAX_RETRIES=4

# 2. 🔄 Attempt Loop with 45s Timeout & Key Rotation
for ((attempt=1; attempt<=MAX_RETRIES; attempt++)); do
    CURRENT_KEY=$(get_random_openrouter_key)
    KEY_DISPLAY="${CURRENT_KEY:0:8}..."
    
    CURRENT_MODEL="$PRIMARY_MODEL"
    [ $attempt -gt 1 ] && CURRENT_MODEL="$FALLBACK_MODEL"
    
    echo "🤖 [$(date +%H:%M:%S)] OpenRouter Bash Attempt $attempt/$MAX_RETRIES | Model: $CURRENT_MODEL | Key: $KEY_DISPLAY" >&2
    
    PAYLOAD_FILE="temp_frames/or_payload.json"
    mkdir -p temp_frames
    
    export GRID_PATH CURRENT_MODEL PROMPT_TEXT PAYLOAD_FILE
    python3 - << 'EOF'
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
    'max_tokens': 1024,
    'temperature': 0.4
}

with open(payload_file, 'w') as f:
    json.dump(payload, f)
EOF

    RESP=$(curl -s --connect-timeout 10 -m 45 -X POST "https://openrouter.ai/api/v1/chat/completions" \
        -H "Authorization: Bearer $CURRENT_KEY" \
        -H "Content-Type: application/json" \
        -d @"$PAYLOAD_FILE")

    rm -f "$PAYLOAD_FILE"

    CONTENT=$(echo "$RESP" | python3 -c "import sys, json; res=json.load(sys.stdin); print(res.get('choices', [{}])[0].get('message', {}).get('content', '') or res.get('choices', [{}])[0].get('message', {}).get('reasoning', ''))" 2>/dev/null)
    ROUTED=$(echo "$RESP" | python3 -c "import sys, json; print(json.load(sys.stdin).get('model', ''))" 2>/dev/null)

    # 🔍 PRINT CHATBOARD RESPONSE TO TERMINAL FOR DEBUGGING
    if [ -n "$CONTENT" ] && [ "$CONTENT" != "None" ]; then
        echo "--------------------------------------------------" >&2
        echo "🔍 [AI RAW RESPONSE / CHATBOARD OUTPUT]:" >&2
        echo "$CONTENT" >&2
        echo "--------------------------------------------------" >&2
        
        RAW_RESPONSE="$CONTENT"
        SUCCESS_REQUESTED_MODEL="$CURRENT_MODEL"
        SUCCESS_ROUTED_MODEL="${ROUTED:-$CURRENT_MODEL}"
        echo "✅ [$(date +%H:%M:%S)] Success on Attempt $attempt! Routed Model: $SUCCESS_ROUTED_MODEL" >&2
        break
    else
        echo "⚠️ [$(date +%H:%M:%S)] Attempt $attempt failed or returned empty text. Output was:" >&2
        echo "$RESP" >&2
        sleep 1
    fi
done

if [ -z "$RAW_RESPONSE" ]; then
    echo '{"status": "failed", "error": "All OpenRouter attempts failed"}'
    exit 1
fi

# 3. 🧹 File Passing & Parsing
RESPONSE_FILE="temp_frames/or_response.txt"
printf "%s" "$RAW_RESPONSE" > "$RESPONSE_FILE"

export REQUESTED_MODEL="$SUCCESS_REQUESTED_MODEL" ROUTED_MODEL="$SUCCESS_ROUTED_MODEL" RESPONSE_FILE
python3 - << 'EOF'
import os, json, re, sys

response_file = os.environ.get('RESPONSE_FILE')
req_m = os.environ.get('REQUESTED_MODEL', '')
rout_m = os.environ.get('ROUTED_MODEL', '')

try:
    with open(response_file, 'r', encoding='utf-8') as f:
        raw = f.read()
except:
    raw = ""

if os.path.exists(response_file):
    os.remove(response_file)

title = None
start_time = None
duration = 15

cleaned = re.sub(r'```json\s*|\s*```', '', raw, flags=re.IGNORECASE).strip()

def is_invalid_title(t):
    if not t: return True
    t_lower = t.lower()
    bad_phrases = [
        "analyze", "thinking", "thought", "reasoning", "step", "here is", 
        "json", "output", "note", "need answer", "exact keys", "screenshot", 
        "video editor", "viral title", "format"
    ]
    if any(bp in t_lower for bp in bad_phrases):
        return True
    if re.match(r'^\d+\s*[\.\-:]+\s*\*\*', t):
        return True
    return False

# Layer 1: Direct JSON Parse
try:
    data = json.loads(cleaned)
    t_candidate = data.get('title')
    if not is_invalid_title(t_candidate):
        title = t_candidate
    start_time = data.get('start_time')
    duration = data.get('clip_duration', data.get('duration', 15))
except Exception:
    pass

# Layer 2: Extract nested JSON
if not title:
    match = re.search(r'\{.*\}', cleaned, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            t_candidate = data.get('title')
            if not is_invalid_title(t_candidate):
                title = t_candidate
            start_time = data.get('start_time')
            duration = data.get('clip_duration', data.get('duration', 15))
        except Exception:
            pass

# Layer 3: Regex Line Fallback
if not title:
    lines = [line.strip() for line in cleaned.split('\n') if line.strip()]
    for line in lines:
        clean_line = re.sub(r'^[\*\-\d\.\s#]+', '', line).strip()
        if not is_invalid_title(clean_line) and len(clean_line) > 5:
            title = clean_line[:60]
            break

# Strict Failure on Bad Title
if not title or is_invalid_title(title):
    print(json.dumps({
        "status": "failed",
        "error": "Strict Parse Failed: AI response contained reasoning text or invalid title format."
    }))
    sys.exit(1)

# Clean title for FFmpeg safety
title = str(title).split('\n')[0].strip()
title = re.sub(r'[,\'"\-:\n\r]+', ' ', title).strip()
title = re.sub(r'\s+', ' ', title)

# Extract Timestamp
if not start_time:
    time_match = re.search(r'\b\d{2}:\d{2}:\d{2}\b', cleaned)
    if time_match:
        start_time = time_match.group(0)
    else:
        start_time = "00:00:10"

try:
    dur_int = max(12, min(45, int(duration)))
except Exception:
    dur_int = 15

# Successful Output
print(json.dumps({
    "status": "success",
    "requested_model": req_m,
    "routed_model": rout_m,
    "title": str(title),
    "start_time": str(start_time),
    "duration": dur_int
}))
EOF
