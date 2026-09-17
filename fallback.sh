#!/bin/bash
# ==============================================================================
# 🚀 OPENROUTER FALLBACK AGENT
# APPROVE/REJECT + Reason + Full Debug
# 1 PRIMARY TRY + 20 FALLBACK RETRIES + STRICT PARSER
# ==============================================================================

export TZ='Asia/Kolkata'
if ! date '+%Z' 2>/dev/null | grep -qi 'IST'; then
    export TZ='IST-5:30'
fi

GRID_PATH="${GRID_PATH:-temp_frames/merged_60_grid_screenshot.jpg}"
SOURCE_DURATION="${SOURCE_DURATION:-60}"
STYLE_PROMPT="${STYLE_PROMPT:-}"

PRIMARY_MODEL="${OPENROUTER_MODEL:-dots-studio/dots-3-note-preview:free}"
FALLBACK_MODEL="openrouter/free"

DEBUG="${DEBUG:-1}"

# 🔑 API keys collect
declare -a KEYS=()
[ -n "$OPENROUTER_API_KEY" ]   && KEYS+=("$OPENROUTER_API_KEY")
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

# ══════════════════════════════════════════════════════════════
# 🚀 PROMPT with APPROVE/REJECT + Reason
# ══════════════════════════════════════════════════════════════
PROMPT_TEXT="Analyze the provided 9:16 gaming screenshot grid. Total video source duration is ${SOURCE_DURATION} seconds.
Style Directive: ${STYLE_PROMPT}

YOUR TASK: Decide APPROVE or REJECT for this video.

REJECT IF:
- Grid shows ONLY menus, login screens, or loading screens
- No actual gameplay visible in ANY frame
- All frames look identical (frozen/paused)
- Crash screen, error, or black frames dominate
- Absolutely no exciting/engaging moment

APPROVE IF:
- Real gameplay is visible (even if not super exciting)
- Any action, movement, or engaging moment exists
- High-tension, emotional, or thrilling segments present

TITLE RULES (only for APPROVE):
- Create a short, viral title under 6 words with 1-3 emojis
- DO NOT use generic boring words like 'Epic', 'Insane', 'Crazy', 'Best', 'Gameplay'
- Make it unique based strictly on what's visible in the grid

STRICT JSON OUTPUT (no markdown, no extra text):

If REJECT:
{\"status\": \"REJECT\", \"reason\": \"<1-line explanation why rejected>\"}

If APPROVE:
{\"status\": \"APPROVE\", \"title\": \"<viral title 6 words max with 1-3 emojis>\", \"start_time\": <integer seconds 0 to $((SOURCE_DURATION - 15))>, \"clip_duration\": <integer 15-${SOURCE_DURATION}>, \"reason\": \"<1-line explanation why approved>\"}

Return ONLY the JSON object."

RAW_RESPONSE=""
SUCCESS_REQUESTED_MODEL=""
SUCCESS_ROUTED_MODEL=""

MAX_RETRIES=21

dbg ""
dbg "════════════════════════════════════════════════════════"
dbg "🚀 OPENROUTER FALLBACK AGENT START — $(date '+%Y-%m-%d %H:%M:%S IST')"
dbg "📁 Grid Path       : $GRID_PATH"
dbg "🎞️  Source Duration : ${SOURCE_DURATION}s"
dbg "🔑 Keys Loaded     : ${#KEYS[@]}"
dbg "🎯 Primary Model   : $PRIMARY_MODEL (Max 1 Try)"
dbg "🔄 Fallback Model  : $FALLBACK_MODEL (Max 20 Tries)"
dbg "🎨 Style Prompt    : ${STYLE_PROMPT:-[empty]}"
dbg "════════════════════════════════════════════════════════"
dbg ""

# 🔄 Retry loop
for ((attempt=1; attempt<=MAX_RETRIES; attempt++)); do
    CURRENT_KEY=$(get_random_openrouter_key)
    KEY_DISPLAY="${CURRENT_KEY:0:12}...${CURRENT_KEY: -4}"
    
    if [ $attempt -eq 1 ]; then
        CURRENT_MODEL="$PRIMARY_MODEL"
    else
        CURRENT_MODEL="$FALLBACK_MODEL"
    fi
    
    dbg ""
    dbg "────────────────────────────────────────────────────────"
    dbg "🤖 ATTEMPT $attempt / $MAX_RETRIES"
    dbg "────────────────────────────────────────────────────────"
    dbg "    Model      : $CURRENT_MODEL"
    dbg "    API Key    : $KEY_DISPLAY"
    dbg "    Time       : $(date '+%H:%M:%S IST')"
    dbg "--------------------------------------------------------"
    dbg "📤 AI KO KYA-KYA BHEJ RAHA HAI (PAYLOAD DETAILS):"
    dbg "--------------------------------------------------------"
    dbg "  📁 Grid Image Path        : $GRID_PATH"
    dbg "  🎞️  Source Duration        : ${SOURCE_DURATION}s"
    dbg "  🎨 Style Directive        : ${STYLE_PROMPT:-[Khaali / Kuch nahi]}"
    dbg "  🤖 Target Model           : $CURRENT_MODEL"
    dbg "  📝 Prompt Text            :"
    echo "$PROMPT_TEXT" | sed 's/^/      /' >&2
    dbg "--------------------------------------------------------"
    
    PAYLOAD_FILE="temp_frames/or_payload.json"
    mkdir -p temp_frames
    
    export GRID_PATH CURRENT_MODEL PROMPT_TEXT PAYLOAD_FILE STYLE_PROMPT SOURCE_DURATION
    python3 - << 'PYEOF'
import os, json, base64

grid_path = os.environ.get('GRID_PATH')
model = os.environ.get('CURRENT_MODEL')
prompt = os.environ.get('PROMPT_TEXT')
payload_file = os.environ.get('PAYLOAD_FILE')
source_duration = int(os.environ.get('SOURCE_DURATION', 60))

with open(grid_path, 'rb') as f:
    img_bytes = f.read()
    b64_img = base64.b64encode(img_bytes).decode('utf-8')

schema = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["APPROVE", "REJECT"]},
        "title": {"type": "string"},
        "start_time": {"type": "integer", "minimum": 0, "maximum": max(0, source_duration - 15)},
        "clip_duration": {"type": "integer", "minimum": 15, "maximum": source_duration},
        "reason": {"type": "string"}
    },
    "required": ["status"],
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
    'max_tokens': 4096,
    'temperature': 0.3,
    'response_format': {
        'type': 'json_schema',
        'json_schema': {
            'name': 'video_edit_params',
            'strict': False,
            'schema': schema
        }
    },
    'provider': {
        'require_parameters': False if is_reasoning else True,
        'ignore': ['nvidia/nemotron-3.5-content-safety:free']
    }
}

with open(payload_file, 'w') as f:
    json.dump(payload, f)

import sys
print(f"    📸 Image Size : {len(img_bytes)} bytes (b64: {len(b64_img)} chars)", file=sys.stderr, flush=True)
print(f"    🧠 Is Reasoning: {is_reasoning}", file=sys.stderr, flush=True)
print(f"    📤 Payload ready: {os.path.getsize(payload_file)} bytes", file=sys.stderr, flush=True)
PYEOF

    dbg ""
    dbg "    📡 Sending request to OpenRouter..."
    
    HTTP_CODE=$(curl -s -o /tmp/or_response_$$.json -w "%{http_code}" \
        --connect-timeout 15 -m 90 \
        -X POST "https://openrouter.ai/api/v1/chat/completions" \
        -H "Authorization: Bearer $CURRENT_KEY" \
        -H "Content-Type: application/json" \
        -d @"$PAYLOAD_FILE")
    
    RESP=$(cat /tmp/or_response_$$.json 2>/dev/null)
    rm -f /tmp/or_response_$$.json
    rm -f "$PAYLOAD_FILE"

    dbg "    📥 HTTP Status  : $HTTP_CODE"
    
    if [ "$DEBUG" = "1" ]; then
        dbg "    📥 Raw Response (first 1000 chars) :"
        echo "$RESP" | head -c 1000 | sed 's/^/     /' >&2
        echo "" >&2
    fi

    ROUTED=$(echo "$RESP" | python3 -c "
import sys, json
try:
    print(json.load(sys.stdin).get('model', ''))
except: print('')
" 2>/dev/null)

    dbg "    🎯 Routed Model : ${ROUTED:-unknown}"

    export ROUTED_CHECK="$ROUTED"
    IS_TEXT_AI=$(python3 -c "
import os
m = os.environ.get('ROUTED_CHECK', '').lower()
text_indicators = ['r1-distill', 'llama-3-8b', 'qwen-2.5-7b', 'gemma-2-9b', 'deepseek-chat', 'mistral-7b', 'text-only']
print('yes' if any(t in m for t in text_indicators) else 'no')
")

    if [ "$IS_TEXT_AI" = "yes" ]; then
        dbg "    ❌ OpenRouter routed a text-only model ($ROUTED). Retrying..."
        sleep 1
        continue
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
except Exception as e:
    print('')
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
        dbg "    ❌ API Error    : $ERROR_MSG"
    fi

    if [ -n "$CONTENT" ] && [ "$CONTENT" != "None" ]; then
        dbg "    📝 Content (first 300 chars): ${CONTENT:0:300}"
        
        IS_VALID_JSON=$(python3 -c '
import json, sys, re
raw_output = sys.argv[1]
try:
    clean_output = re.sub(r"```json\s*|\s*```", "", raw_output, flags=re.IGNORECASE).strip()
    clean_output = re.sub(r"<think>.*?</think>", "", clean_output, flags=re.DOTALL).strip()
    
    data = json.loads(clean_output)
    if not isinstance(data, dict):
        print("invalid")
        sys.exit(0)
    status = str(data.get("status", "")).upper()
    if status == "REJECT":
        print("valid")
        sys.exit(0)
    if status == "APPROVE" and all(k in data for k in ("title", "start_time", "clip_duration")):
        print("valid")
        sys.exit(0)
    if all(k in data for k in ("title", "start_time", "clip_duration")):
        print("valid")
        sys.exit(0)
    print("invalid")
except Exception:
    print("invalid")
' "$CONTENT")

        if [ "$IS_VALID_JSON" = "valid" ]; then
            dbg ""
            dbg "    ✅ SUCCESS — Model responded with valid JSON!"
            dbg "    🎯 Routed Model : ${ROUTED:-unknown}"
            
            RAW_RESPONSE="$CONTENT"
            SUCCESS_REQUESTED_MODEL="$CURRENT_MODEL"
            SUCCESS_ROUTED_MODEL="${ROUTED:-$CURRENT_MODEL}"
            break
        else
            dbg "    ⚠️  Model ($CURRENT_MODEL) returned invalid JSON or missing keys. Retrying..."
            sleep 1.5
            continue
        fi
    else
        dbg "    ⚠️  Empty content in response. Retrying..."
        sleep 1.5
    fi
done

if [ -z "$RAW_RESPONSE" ]; then
    dbg ""
    dbg "════════════════════════════════════════════════════════"
    dbg "❌ ALL ATTEMPTS FAILED"
    dbg "════════════════════════════════════════════════════════"
    echo '{"status": "failed", "error": "All 21 OpenRouter attempts failed"}'
    exit 1
fi

RESPONSE_FILE="temp_frames/or_response.txt"
printf "%s" "$RAW_RESPONSE" > "$RESPONSE_FILE"

dbg ""
dbg "════════════════════════════════════════════════════════"
dbg "🧹 STRICT PARSING PHASE"
dbg "════════════════════════════════════════════════════════"

export REQUESTED_MODEL="$SUCCESS_REQUESTED_MODEL" ROUTED_MODEL="$SUCCESS_ROUTED_MODEL" RESPONSE_FILE DEBUG SOURCE_DURATION
python3 - << 'PYEOF'
import os, json, re, sys

response_file = os.environ.get('RESPONSE_FILE')
req_m = os.environ.get('REQUESTED_MODEL', '')
rout_m = os.environ.get('ROUTED_MODEL', '')
debug = os.environ.get('DEBUG', '0') == '1'
source_duration = int(os.environ.get('SOURCE_DURATION', 60))

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

cleaned = re.sub(r'```json\s*|\s*```', '', raw, flags=re.IGNORECASE).strip()
cleaned = re.sub(r'<think>.*?</think>', '', cleaned, flags=re.DOTALL).strip()

data = None
try:
    data = json.loads(cleaned)
except Exception:
    match = re.search(r'\{.*\}', cleaned, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
        except Exception:
            pass

if not data or not isinstance(data, dict):
    dbg("❌ Strict JSON parsing failed completely.")
    print(json.dumps({"status": "failed", "error": "Strict JSON parse failed"}))
    sys.exit(1)

status_field = str(data.get('status', '')).strip().upper()
reason_text = str(data.get('reason', '')).strip() or "(no reason provided)"

# ══════════════════════════════════════════════════════════════
# 🚫 REJECT CASE
# ══════════════════════════════════════════════════════════════
if status_field == 'REJECT':
    dbg("")
    dbg("╔══════════════════════════════════════════════════════╗")
    dbg("║  🚫 AI NE REJECT KIYA                                ║")
    dbg("╚══════════════════════════════════════════════════════╝")
    dbg(f"  💬 Reason     : {reason_text}")
    dbg(f"  🤖 Routed     : {rout_m}")
    dbg(f"  🎯 Requested  : {req_m}")
    dbg(f"  🕐 Time (IST) : $(date '+%Y-%m-%d %H:%M:%S IST')")
    dbg("")
    
    print(json.dumps({
        "status": "reject",
        "reason": reason_text,
        "requested_model": req_m,
        "routed_model": rout_m
    }))
    sys.exit(0)

# ══════════════════════════════════════════════════════════════
# ✅ APPROVE CASE
# ══════════════════════════════════════════════════════════════
if not all(k in data for k in ("title", "start_time", "clip_duration")):
    dbg("❌ APPROVE status par required keys missing")
    print(json.dumps({"status": "failed", "error": "Missing required keys"}))
    sys.exit(1)

raw_title = data.get('title', '')
if isinstance(raw_title, list):
    raw_title = raw_title[0] if len(raw_title) > 0 else ""
elif isinstance(raw_title, str):
    lines = [line.strip() for line in raw_title.split('\n') if line.strip()]
    raw_title = lines[0] if lines else ""

title = re.sub(r'^\d+[\.\)]\s*|^[\-\*]\s*|[\*\#\`\"]', '', str(raw_title)).strip()
title = title.strip("'\"")
title = re.sub(r'\s+', ' ', title)

try:
    start_time_val = int(data.get('start_time', 0))
    if start_time_val < 0:
        start_time_val = 0
except Exception:
    match_num = re.search(r'\d+', str(data.get('start_time', '0')))
    start_time_val = int(match_num.group(0)) if match_num else 0

duration = data.get('clip_duration', 15)

try:
    dur_int = int(duration)
    if dur_int < 15 or dur_int > source_duration:
        raise ValueError(f"Duration out of bounds (15 to {source_duration}s)")
except Exception as e:
    dbg(f"❌ Invalid duration value received: {duration} ({e})")
    print(json.dumps({"status": "failed", "error": f"Invalid clip duration: {duration}"}))
    sys.exit(1)

dbg("")
dbg("╔══════════════════════════════════════════════════════╗")
dbg("║  ✅ AI NE APPROVE KIYA                               ║")
dbg("╚══════════════════════════════════════════════════════╝")
dbg(f"  🎬 Title      : {title}")
dbg(f"  ⏱️  Start Time : {start_time_val}s")
dbg(f"  ⏳ Duration   : {dur_int}s")
dbg(f"  💬 Reason     : {reason_text}")
dbg(f"  🤖 Routed     : {rout_m}")
dbg(f"  🕐 Time (IST) : $(date '+%Y-%m-%d %H:%M:%S IST')")
dbg("")

print(json.dumps({
    "status": "success",
    "requested_model": req_m,
    "routed_model": rout_m,
    "title": title,
    "start_time": start_time_val,
    "duration": dur_int,
    "reason": reason_text
}))
PYEOF