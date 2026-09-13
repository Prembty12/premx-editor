#!/bin/bash
# ==============================================================================
# 🚀 OPENROUTER BASH AGENT - FINAL (FULL max_tokens, WAIT FOR COMPLETE)
# Fallback: openrouter/free (NO CHANGE)
# max_tokens: 4096 (full response)
# ==============================================================================

GRID_PATH="${GRID_PATH:-temp_frames/merged_60_grid_screenshot.jpg}"
SOURCE_DURATION="${SOURCE_DURATION:-60}"
INSIGHTS_SUMMARY="${INSIGHTS_SUMMARY:-}"
STYLE_PROMPT="${STYLE_PROMPT:-}"

PRIMARY_MODEL="${OPENROUTER_MODEL:-nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free}"
FALLBACK_MODEL="openrouter/free"

DEBUG="${DEBUG:-1}"

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

dbg() {
    [ "$DEBUG" = "1" ] && echo "$@" >&2
}

PROMPT_TEXT="Analyze the provided 9:16 gaming screenshot grid. Total video source duration is ${SOURCE_DURATION} seconds.
Insights Context: ${INSIGHTS_SUMMARY}
Style Directive: ${STYLE_PROMPT}

Find the most thrilling, high-action segment, skipping dull introductions.

STRICT OUTPUT RULES:
1. Return ONLY ONE JSON object.
2. Do NOT list multiple titles.
3. Do NOT use markdown code blocks.
4. Output must start with { and end with }.

JSON format:
{\"title\": \"Single Best Title\", \"start_time\": \"HH:MM:SS\", \"clip_duration\": 30}"

RAW_RESPONSE=""
SUCCESS_REQUESTED_MODEL=""
SUCCESS_ROUTED_MODEL=""
MAX_RETRIES=4

dbg ""
dbg "════════════════════════════════════════════════════════"
dbg "🚀 OPENROUTER AGENT START — $(date '+%Y-%m-%d %H:%M:%S')"
dbg "════════════════════════════════════════════════════════"
dbg "📁 Grid Path       : $GRID_PATH"
dbg "⏱️  Source Duration : ${SOURCE_DURATION}s"
dbg "🔑 Keys Loaded     : ${#KEYS[@]}"
dbg "🎯 Primary Model   : $PRIMARY_MODEL"
dbg "🔄 Fallback Model  : $FALLBACK_MODEL"
dbg "════════════════════════════════════════════════════════"
dbg ""

for ((attempt=1; attempt<=MAX_RETRIES; attempt++)); do
    CURRENT_KEY=$(get_random_openrouter_key)
    KEY_DISPLAY="${CURRENT_KEY:0:12}...${CURRENT_KEY: -4}"
    
    CURRENT_MODEL="$PRIMARY_MODEL"
    [ $attempt -gt 1 ] && CURRENT_MODEL="$FALLBACK_MODEL"
    
    dbg ""
    dbg "────────────────────────────────────────────────────────"
    dbg "🤖 ATTEMPT $attempt / $MAX_RETRIES"
    dbg "────────────────────────────────────────────────────────"
    dbg "   Model     : $CURRENT_MODEL"
    dbg "   API Key   : $KEY_DISPLAY"
    dbg "   Time      : $(date +%H:%M:%S)"
    
    PAYLOAD_FILE="temp_frames/or_payload.json"
    mkdir -p temp_frames
    
    export GRID_PATH CURRENT_MODEL PROMPT_TEXT PAYLOAD_FILE
    python3 - << 'PYEOF'
import os, json, base64

grid_path = os.environ.get('GRID_PATH')
model = os.environ.get('CURRENT_MODEL')
prompt = os.environ.get('PROMPT_TEXT')
payload_file = os.environ.get('PAYLOAD_FILE')

with open(grid_path, 'rb') as f:
    img_bytes = f.read()
    b64_img = base64.b64encode(img_bytes).decode('utf-8')

print(f"   📸 Image Size : {len(img_bytes)} bytes", flush=True)

schema = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "start_time": {"type": "string"},
        "clip_duration": {"type": "integer", "minimum": 12, "maximum": 45}
    },
    "required": ["title", "start_time", "clip_duration"],
    "additionalProperties": False
}

payload = {
    'model': model,
    'messages': [{
        'role': 'user',
        'content': [
            {'type': 'text', 'text': prompt},
            {'type': 'image_url', 'image_url': {'url': f'data:image/jpeg;base64,{b64_img}'}}
        ]
    }],
    'max_tokens': 4096,
    'temperature': 0.2,
    'response_format': {
        'type': 'json_schema',
        'json_schema': {
            'name': 'video_edit_params',
            'strict': True,
            'schema': schema
        }
    },
    'provider': {
        'require_parameters': True,
        'ignore': ['nvidia/nemotron-3.5-content-safety:free'],
        'allow_fallbacks': True
    }
}

with open(payload_file, 'w') as f:
    json.dump(payload, f)

print(f"   🔧 require_parameters: True", flush=True)
print(f"   📤 Payload ready: {os.path.getsize(payload_file)} bytes", flush=True)
PYEOF

    dbg ""
    dbg "   📡 Sending request to OpenRouter... (waiting for FULL response)"
    
    HTTP_CODE=$(curl -s -o /tmp/or_response_$$.json -w "%{http_code}" \
        --connect-timeout 15 -m 180 \
        -X POST "https://openrouter.ai/api/v1/chat/completions" \
        -H "Authorization: Bearer $CURRENT_KEY" \
        -H "Content-Type: application/json" \
        -d @"$PAYLOAD_FILE")
    
    RESP=$(cat /tmp/or_response_$$.json 2>/dev/null)
    rm -f /tmp/or_response_$$.json
    rm -f "$PAYLOAD_FILE"

    dbg "   📥 HTTP Status  : $HTTP_CODE"
    
    if [ "$DEBUG" = "1" ]; then
        dbg "   📥 Raw Response :"
        echo "$RESP" | head -c 3000 | sed 's/^/      /' >&2
        echo "" >&2
    fi

    CONTENT=$(echo "$RESP" | python3 -c "
import sys, json
try:
    res = json.load(sys.stdin)
    choices = res.get('choices', [])
    if choices:
        msg = choices[0].get('message', {})
        content = msg.get('content', '') or msg.get('reasoning', '')
        print(content)
    else:
        print('')
except: print('')
" 2>/dev/null)
    
    FINISH_REASON=$(echo "$RESP" | python3 -c "
import sys, json
try:
    res = json.load(sys.stdin)
    choices = res.get('choices', [])
    if choices:
        print(choices[0].get('finish_reason', ''))
except: print('')
" 2>/dev/null)
    
    ROUTED=$(echo "$RESP" | python3 -c "
import sys, json
try: print(json.load(sys.stdin).get('model', ''))
except: print('')
" 2>/dev/null)

    dbg "   🏁 Finish Reason: $FINISH_REASON"
    dbg "   📝 Content Len  : ${#CONTENT} chars"

    if [ -n "$CONTENT" ] && [ "$CONTENT" != "None" ]; then
        dbg ""
        dbg "   ✅ SUCCESS — Model responded!"
        dbg "   🎯 Routed Model : ${ROUTED:-unknown}"
        dbg ""
        dbg "   ┌─────────────────────────────────────────────"
        dbg "   │ 🔍 AI RAW OUTPUT (last 1000 chars):"
        dbg "   └─────────────────────────────────────────────"
        echo "$CONTENT" | tail -c 1000 | sed 's/^/   │ /' >&2
        dbg "   ─────────────────────────────────────────────"
        
        RAW_RESPONSE="$CONTENT"
        SUCCESS_REQUESTED_MODEL="$CURRENT_MODEL"
        SUCCESS_ROUTED_MODEL="${ROUTED:-$CURRENT_MODEL}"
        break
    else
        dbg "   ⚠️  Empty content. Retrying..."
        sleep 2
    fi
done

if [ -z "$RAW_RESPONSE" ]; then
    echo '{"status": "failed", "error": "All OpenRouter attempts failed"}'
    exit 1
fi

RESPONSE_FILE="temp_frames/or_response.txt"
printf "%s" "$RAW_RESPONSE" > "$RESPONSE_FILE"

dbg ""
dbg "════════════════════════════════════════════════════════"
dbg "🧹 PARSING PHASE (Full response received)"
dbg "════════════════════════════════════════════════════════"

export REQUESTED_MODEL="$SUCCESS_REQUESTED_MODEL" ROUTED_MODEL="$SUCCESS_ROUTED_MODEL" RESPONSE_FILE DEBUG
python3 - << 'PYEOF'
import os, json, re, sys

response_file = os.environ.get('RESPONSE_FILE')
req_m = os.environ.get('REQUESTED_MODEL', '')
rout_m = os.environ.get('ROUTED_MODEL', '')
debug = os.environ.get('DEBUG', '0') == '1'

def dbg(msg):
    if debug: print(msg, file=sys.stderr)

with open(response_file, 'r', encoding='utf-8') as f:
    raw = f.read()

if os.path.exists(response_file):
    os.remove(response_file)

dbg(f"📄 Raw length: {len(raw)} chars")

cleaned = re.sub(r'```json\s*|\s*```', '', raw, flags=re.IGNORECASE).strip()
dbg(f"🧽 After cleanup: {len(cleaned)} chars")

data = None

# Strategy 1: Direct parse
try:
    data = json.loads(cleaned)
    dbg("✅ Direct JSON parse SUCCESS")
except json.JSONDecodeError:
    dbg("⚠️  Direct parse failed")

# Strategy 2: Strict title pattern
if data is None:
    match = re.search(
        r'\{\s*"title"\s*:\s*"[^"]+"\s*,\s*"start_time"\s*:\s*"[^"]+"\s*,\s*"clip_duration"\s*:\s*\d+\s*\}',
        raw, re.DOTALL
    )
    if match:
        try:
            data = json.loads(match.group(0))
            dbg("✅ Parsed via strict title pattern")
        except Exception as e:
            dbg(f"❌ Strict pattern failed: {e}")

# Strategy 3: Find any JSON with title + start_time
if data is None:
    for match in re.finditer(r'\{[^{}]*"title"[^{}]*\}', raw, re.DOTALL):
        try:
            candidate = json.loads(match.group(0))
            if 'title' in candidate and 'start_time' in candidate:
                data = candidate
                dbg("✅ Parsed via loose title pattern")
                break
        except:
            continue

# Strategy 4: Last resort - find any JSON object
if data is None:
    for match in re.finditer(r'\{[^{}]*\}', raw, re.DOTALL):
        try:
            candidate = json.loads(match.group(0))
            if 'title' in candidate:
                data = candidate
                dbg("✅ Parsed via last-resort pattern")
                break
        except:
            continue

if data is None:
    dbg("❌ All parse attempts failed")
    dbg(f"🔎 First 500 chars of raw: {raw[:500]}")
    print(json.dumps({"status": "failed", "error": "No valid JSON found"}))
    sys.exit(1)

title = data.get('title', '').strip()
start_time = data.get('start_time', '00:00:10')
duration = data.get('clip_duration', 15)

dbg(f"🎬 Title: '{title}'")
dbg(f"⏰ Start: '{start_time}'")
dbg(f"⏱️  Duration: {duration}")

if not title or len(title.split()) < 2:
    print(json.dumps({"status": "failed", "error": "Title too short"}))
    sys.exit(1)

title = re.sub(r'[,\'"\-:\n\r]+', ' ', title).strip()
title = re.sub(r'\s+', ' ', title)

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
PYEOF
