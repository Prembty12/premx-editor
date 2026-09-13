#!/bin/bash
# ==============================================================================
# 🚀 OPENROUTER BASH AGENT (FULL TERMINAL DEBUG MODE) - FIXED
# ==============================================================================

GRID_PATH="${GRID_PATH:-temp_frames/merged_60_grid_screenshot.jpg}"
SOURCE_DURATION="${SOURCE_DURATION:-60}"
INSIGHTS_SUMMARY="${INSIGHTS_SUMMARY:-}"
STYLE_PROMPT="${STYLE_PROMPT:-}"

PRIMARY_MODEL="${OPENROUTER_MODEL:-nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free}"
FALLBACK_MODEL="meta-llama/llama-3.2-11b-vision-instruct:free"

# Debug flag (0 = silent, 1 = full debug)
DEBUG="${DEBUG:-1}"

# 🔑 API keys collect
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

# Debug helper
dbg() {
    [ "$DEBUG" = "1" ] && echo "$@" >&2
}

PROMPT_TEXT="Analyze the provided 9:16 gaming screenshot grid. Total video source duration is ${SOURCE_DURATION} seconds.
Insights Context: ${INSIGHTS_SUMMARY}
Style Directive: ${STYLE_PROMPT}

Find the most thrilling, high-action segment, skipping dull introductions.

IMPORTANT: Do all your analysis internally. Do NOT write out your thinking, reasoning, or thought process. Just give me the final answer directly.

STRICT OUTPUT RULES:
1. Return ONLY ONE JSON object.
2. Do NOT write thinking process, reasoning, or analysis in the output.
3. Do NOT list multiple titles.
4. Do NOT use markdown code blocks.
5. Output must start with { and end with }.

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

# 🔄 Retry loop
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

print(f"   📸 Image Size : {len(img_bytes)} bytes (b64: {len(b64_img)} chars)", flush=True)

schema = {
    "type": "object",
    "properties": {
        "title": {
            "type": "string",
            "description": "Viral title under 6 words with 1-3 emojis. NO generic words like Epic, Insane, Crazy, Best, Gameplay."
        },
        "start_time": {
            "type": "string",
            "description": "HH:MM:SS format indicating peak action start time"
        },
        "clip_duration": {
            "type": "integer",
            "minimum": 12,
            "maximum": 45
        }
    },
    "required": ["title", "start_time", "clip_duration"],
    "additionalProperties": False
}

is_reasoning = any(k in model.lower() for k in ['reasoning', 'nemotron', 'nano-omni'])

payload = {
    'model': model,
    'messages': [{
        'role': 'user',
        'content': [
            {'type': 'text', 'text': prompt},
            {'type': 'image_url', 'image_url': {'url': f'data:image/jpeg;base64,{b64_img}'}}
        ]
    }],
    'max_tokens': 150,
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
        'require_parameters': False if is_reasoning else True,
        'ignore': ['nvidia/nemotron-3.5-content-safety:free'],
        'allow_fallbacks': True
    }
}

with open(payload_file, 'w') as f:
    json.dump(payload, f)

print(f"   🧠 Is Reasoning: {is_reasoning}", flush=True)
print(f"   🔧 require_parameters: {payload['provider']['require_parameters']}", flush=True)
print(f"   📤 Payload ready: {os.path.getsize(payload_file)} bytes", flush=True)
PYEOF

    dbg ""
    dbg "   📡 Sending request to OpenRouter..."
    
    HTTP_CODE=$(curl -s -o /tmp/or_response_$$.json -w "%{http_code}" \
        --connect-timeout 15 -m 90 \
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
        echo "$RESP" | head -c 2000 | sed 's/^/      /' >&2
        echo "" >&2
    fi

    # Extract fields
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
except Exception as e:
    print('')
" 2>/dev/null)
    
    ROUTED=$(echo "$RESP" | python3 -c "
import sys, json
try:
    print(json.load(sys.stdin).get('model', ''))
except: print('')
" 2>/dev/null)
    
    ERROR_MSG=$(echo "$RESP" | python3 -c "
import sys, json
try:
    res = json.load(sys.stdin)
    err = res.get('error', {})
    if err:
        print(f\"{err.get('code','')} - {err.get('message','')}\")
except: pass
" 2>/dev/null)

    if [ -n "$ERROR_MSG" ]; then
        dbg "   ❌ API Error    : $ERROR_MSG"
    fi

    if [ -n "$CONTENT" ] && [ "$CONTENT" != "None" ]; then
        dbg ""
        dbg "   ✅ SUCCESS — Model responded!"
        dbg "   🎯 Routed Model : ${ROUTED:-unknown}"
        dbg "   📝 Content Len  : ${#CONTENT} chars"
        dbg ""
        dbg "   ┌─────────────────────────────────────────────"
        dbg "   │ 🔍 AI RAW OUTPUT:"
        dbg "   └─────────────────────────────────────────────"
        echo "$CONTENT" | sed 's/^/   │ /' >&2
        dbg "   ─────────────────────────────────────────────"
        
        RAW_RESPONSE="$CONTENT"
        SUCCESS_REQUESTED_MODEL="$CURRENT_MODEL"
        SUCCESS_ROUTED_MODEL="${ROUTED:-$CURRENT_MODEL}"
        break
    else
        dbg "   ⚠️  Empty content in response. Retrying..."
        sleep 2
    fi
done

if [ -z "$RAW_RESPONSE" ]; then
    dbg ""
    dbg "════════════════════════════════════════════════════════"
    dbg "❌ ALL ATTEMPTS FAILED"
    dbg "════════════════════════════════════════════════════════"
    echo '{"status": "failed", "error": "All OpenRouter attempts failed"}'
    exit 1
fi

# 🧹 Parser with debug
RESPONSE_FILE="temp_frames/or_response.txt"
printf "%s" "$RAW_RESPONSE" > "$RESPONSE_FILE"

dbg ""
dbg "════════════════════════════════════════════════════════"
dbg "🧹 PARSING PHASE"
dbg "════════════════════════════════════════════════════════"

export REQUESTED_MODEL="$SUCCESS_REQUESTED_MODEL" ROUTED_MODEL="$SUCCESS_ROUTED_MODEL" RESPONSE_FILE DEBUG
python3 - << 'PYEOF'
import os, json, re, sys

response_file = os.environ.get('RESPONSE_FILE')
req_m = os.environ.get('REQUESTED_MODEL', '')
rout_m = os.environ.get('ROUTED_MODEL', '')
debug = os.environ.get('DEBUG', '0') == '1'

def dbg(msg):
    if debug:
        print(msg, file=sys.stderr)

try:
    with open(response_file, 'r', encoding='utf-8') as f:
        raw = f.read()
except:
    raw = ""

if os.path.exists(response_file):
    os.remove(response_file)

dbg(f"📄 Raw length: {len(raw)} chars")

# --- SMART PARSER: Last JSON block nikaalo ---
cleaned = re.sub(r'```json\s*|\s*```', '', raw, flags=re.IGNORECASE).strip()
dbg(f"🧽 After cleanup: {len(cleaned)} chars")

data = None

# Pehle direct parse try karo
try:
    data = json.loads(cleaned)
    dbg("✅ Direct JSON parse SUCCESS")
except json.JSONDecodeError:
    dbg("⚠️  Direct parse failed, trying last JSON block...")
    
    # Last '{' se last '}' tak nikaalo
    first_brace = cleaned.find('{')
    last_brace = cleaned.rfind('}')
    
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        json_candidate = cleaned[first_brace:last_brace+1]
        dbg(f"🔎 JSON candidate (first 300): {json_candidate[:300]}")
        try:
            data = json.loads(json_candidate)
            dbg("✅ Parsed JSON from last block SUCCESS")
        except Exception as e:
            dbg(f"❌ Last block parse failed: {e}")
    
    # Agar phir bhi fail, toh title-specific pattern try karo
    if data is None:
        match = re.search(r'\{[^{}]*"title"[^{}]*\}', raw, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
                dbg("✅ Parsed via title-specific regex")
            except Exception as e:
                dbg(f"❌ Title regex parse failed: {e}")
    
    if data is None:
        dbg("❌ All parse attempts failed")
        print(json.dumps({"status": "failed", "error": "No valid JSON found in response"}))
        sys.exit(1)

# --- Extract fields ---
dbg(f"📋 Parsed keys: {list(data.keys())}")
dbg(f"📋 Parsed data: {json.dumps(data, ensure_ascii=False)[:500]}")

title = data.get('title', '').strip()
start_time = data.get('start_time', '00:00:10')
duration = data.get('clip_duration', 15)

dbg(f"🎬 Extracted title: '{title}'")
dbg(f"⏰ Extracted start_time: '{start_time}'")
dbg(f"⏱️  Extracted duration: {duration}")

if not title or len(title.split()) < 2:
    dbg(f"❌ Title invalid: '{title}'")
    print(json.dumps({"status": "failed", "error": "Title too short"}))
    sys.exit(1)

title = re.sub(r'[,\'"\-:\n\r]+', ' ', title).strip()
title = re.sub(r'\s+', ' ', title)

try:
    dur_int = max(12, min(45, int(duration)))
except:
    dur_int = 15

dbg(f"✅ Final title: '{title}'")
dbg(f"✅ Final duration: {dur_int}")

print(json.dumps({
    "status": "success",
    "requested_model": req_m,
    "routed_model": rout_m,
    "title": str(title),
    "start_time": str(start_time),
    "duration": dur_int
}))
PYEOF