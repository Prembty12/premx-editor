#!/bin/bash
# ==============================================================================
# 🚀 OPENROUTER BASH AGENT - FIXED V6 (FINAL)
# Fallback: openrouter/free (UNCHANGED - tensenmat)
# Fixes: max_tokens 4096, reasoning.exclude, regex fallback, smart reject, exit 0
# ==============================================================================

GRID_PATH="${GRID_PATH:-temp_frames/merged_60_grid_screenshot.jpg}"
SOURCE_DURATION="${SOURCE_DURATION:-60}"
INSIGHTS_SUMMARY="${INSIGHTS_SUMMARY:-}"
STYLE_PROMPT="${STYLE_PROMPT:-}"

PRIMARY_MODEL="${OPENROUTER_MODEL:-nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free}"
FALLBACK_MODEL="openrouter/free"   # ✅ UNCHANGED — tensenmat

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

CRITICAL INSTRUCTION: Respond with the JSON object IMMEDIATELY. Do NOT write any thinking, reasoning, analysis, or explanation. Do NOT describe what you see. Your FIRST character must be '{' and your LAST character must be '}'. No exceptions.

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
MAX_RETRIES=6

dbg ""
dbg "════════════════════════════════════════════════════════"
dbg "🚀 OPENROUTER AGENT START — $(date '+%Y-%m-%d %H:%M:%S')"
dbg "════════════════════════════════════════════════════════"
dbg "📁 Grid Path       : $GRID_PATH"
dbg "⏱️  Source Duration : ${SOURCE_DURATION}s"
dbg "🔑 Keys Loaded     : ${#KEYS[@]}"
dbg "🎯 Primary Model   : $PRIMARY_MODEL"
dbg "🔄 Fallback Model  : $FALLBACK_MODEL  (tensenmat, unchanged)"
dbg "📊 Max Retries     : $MAX_RETRIES"
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
    dbg "    Model     : $CURRENT_MODEL"
    dbg "    API Key   : $KEY_DISPLAY"
    dbg "    Time      : $(date +%H:%M:%S)"

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

print(f"    📸 Image Size : {len(img_bytes)} bytes (b64: {len(b64_img)} chars)", flush=True)

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
    'max_tokens': 4096,                 # ✅ FIX #1: reasoning buffer
    'temperature': 0.2,
    'reasoning': {                     # ✅ FIX #2: reasoning hide
        'exclude': True
    },
    'response_format': {
        'type': 'json_schema',
        'json_schema': {
            'name': 'video_edit_params',
            'strict': True,
            'schema': schema
        }
    },
    'provider': {
        'require_parameters': True,    # ✅ text-only models blocked
        'ignore': ['nvidia/nemotron-3.5-content-safety:free'],
        'allow_fallbacks': True
    }
}

with open(payload_file, 'w') as f:
    json.dump(payload, f)

print(f"    🔧 require_parameters : {payload['provider']['require_parameters']}", flush=True)
print(f"    🧠 reasoning.exclude  : {payload['reasoning']['exclude']}", flush=True)
print(f"    📏 max_tokens         : {payload['max_tokens']}", flush=True)
print(f"    📤 Payload ready: {os.path.getsize(payload_file)} bytes", flush=True)
PYEOF

    dbg ""
    dbg "    📡 Sending request to OpenRouter..."

    HTTP_CODE=$(curl -s -o /tmp/or_response_$$.json -w "%{http_code}" \
        --connect-timeout 15 -m 120 \
        -X POST "https://openrouter.ai/api/v1/chat/completions" \
        -H "Authorization: Bearer $CURRENT_KEY" \
        -H "Content-Type: application/json" \
        -d @"$PAYLOAD_FILE")

    RESP=$(cat /tmp/or_response_$$.json 2>/dev/null)
    rm -f /tmp/or_response_$$.json
    rm -f "$PAYLOAD_FILE"

    dbg "    📥 HTTP Status  : $HTTP_CODE"

    # ✅ HTTP error handling
    case "$HTTP_CODE" in
        200) ;;
        429) dbg "    ⏳ Rate limit — waiting 20s..."; sleep 20 ;;
        402) dbg "    💰 Credit/payment issue"; sleep 5 ;;
        503) dbg "    🔧 Model overloaded"; sleep 5 ;;
        000) dbg "    🌐 Network timeout"; sleep 5 ;;
        *)   dbg "    ❌ HTTP $HTTP_CODE — retrying"; sleep 3 ;;
    esac

    if [ "$DEBUG" = "1" ]; then
        dbg "    📥 Raw Response (first 800 chars):"
        echo "$RESP" | head -c 800 | sed 's/^/     /' >&2
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

    ROUTED=$(echo "$RESP" | python3 -c "
import sys, json
try: print(json.load(sys.stdin).get('model', ''))
except: print('')
" 2>/dev/null)

    FINISH_REASON=$(echo "$RESP" | python3 -c "
import sys, json
try:
    c = json.load(sys.stdin).get('choices', [])
    print(c[0].get('finish_reason', '') if c else '')
except: print('')
" 2>/dev/null)

    ERROR_MSG=$(echo "$RESP" | python3 -c "
import sys, json
try:
    res = json.load(sys.stdin)
    err = res.get('error', {})
    if err: print(f\"{err.get('code','')} - {err.get('message','')}\")
except: pass
" 2>/dev/null)

    if [ -n "$ERROR_MSG" ]; then
        dbg "    ❌ API Error    : $ERROR_MSG"
    fi

    if [ "$FINISH_REASON" = "length" ]; then
        dbg "    ⚠️  finish_reason=length — response truncated!"
    fi

    # ── SMART VALIDATION ──
    if [ -n "$CONTENT" ] && [ "$CONTENT" != "None" ]; then
        REJECT=0
        REJECT_REASON=""

        # Check 1: Valid JSON with title field?
        if ! echo "$CONTENT" | grep -qE '\{[^{}]*"title"[^{}]*\}'; then
            REJECT=1
            REJECT_REASON="no title field in response"
        fi

        # Check 2: Response too short?
        if [ ${#CONTENT} -lt 40 ]; then
            REJECT=1
            REJECT_REASON="response too short (${#CONTENT} chars)"
        fi

        # Check 3: finish_reason length but no JSON?
        if [ "$FINISH_REASON" = "length" ] && ! echo "$CONTENT" | grep -qE '"title"'; then
            REJECT=1
            REJECT_REASON="truncated before JSON output"
        fi

        if [ "$REJECT" = "1" ]; then
            dbg ""
            dbg "    🚨 REJECTED — $REJECT_REASON"
            dbg "    🔄 Retrying with next attempt..."
            sleep 2
            continue
        fi

        # ── SUCCESS ──
        dbg ""
        dbg "    ✅ SUCCESS — Model responded!"
        dbg "    🎯 Routed Model : ${ROUTED:-unknown}"
        dbg "    📝 Content Len  : ${#CONTENT} chars"
        dbg "    🏁 Finish Reason: ${FINISH_REASON:-unknown}"
        dbg ""
        dbg "    ┌─────────────────────────────────────────────"
        dbg "    │ 🔍 AI RAW OUTPUT:"
        dbg "    └─────────────────────────────────────────────"
        echo "$CONTENT" | head -c 1500 | sed 's/^/    │ /' >&2
        dbg "    ─────────────────────────────────────────────"

        RAW_RESPONSE="$CONTENT"
        SUCCESS_REQUESTED_MODEL="$CURRENT_MODEL"
        SUCCESS_ROUTED_MODEL="${ROUTED:-$CURRENT_MODEL}"
        break
    else
        dbg "    ⚠️  Empty content. Retrying..."
        sleep 2
    fi
done

if [ -z "$RAW_RESPONSE" ]; then
    dbg ""
    dbg "════════════════════════════════════════════════════════"
    dbg "❌ ALL $MAX_RETRIES ATTEMPTS FAILED"
    dbg "════════════════════════════════════════════════════════"
    echo '{"status": "failed", "error": "All OpenRouter attempts failed"}'
    exit 1
fi

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
    if debug: print(msg, file=sys.stderr)

try:
    with open(response_file, 'r', encoding='utf-8') as f:
        raw = f.read()
except:
    raw = ""

if os.path.exists(response_file):
    os.remove(response_file)

dbg(f"📄 Raw length: {len(raw)} chars")
cleaned = re.sub(r'```json\s*|\s*```', '', raw, flags=re.IGNORECASE).strip()
dbg(f"🧽 After cleanup: {len(cleaned)} chars")

data = None

# Attempt 1: Direct JSON parse
try:
    data = json.loads(cleaned)
    dbg("✅ Direct JSON parse SUCCESS")
except json.JSONDecodeError:
    dbg("⚠️  Direct parse failed")

# Attempt 2: First { to last }
if data is None:
    first_brace = cleaned.find('{')
    last_brace = cleaned.rfind('}')
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        try:
            data = json.loads(cleaned[first_brace:last_brace+1])
            dbg("✅ Parsed from brace range")
        except Exception as e:
            dbg(f"❌ Brace range failed: {e}")

# Attempt 3: Title-specific regex
if data is None:
    match = re.search(r'\{[^{}]*"title"[^{}]*\}', raw, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            dbg("✅ Parsed via title regex")
        except Exception as e:
            dbg(f"❌ Title regex failed: {e}")

# ✅ FIX #3: Field-level regex extraction (last resort)
if data is None:
    title_match = re.search(r'"title"\s*:\s*"([^"]+)"', raw)
    time_match = re.search(r'"start_time"\s*:\s*"([^"]+)"', raw)
    dur_match = re.search(r'"clip_duration"\s*:\s*(\d+)', raw)

    if title_match:
        data = {
            'title': title_match.group(1),
            'start_time': time_match.group(1) if time_match else '00:00:10',
            'clip_duration': int(dur_match.group(1)) if dur_match else 30
        }
        dbg("✅ Recovered via field-level regex")

if data is None:
    dbg("❌ All parse attempts failed")
    print(json.dumps({"status": "failed", "error": "No valid JSON found"}))
    sys.exit(0)   # ⚠️ exit 0 — wrapper/main script handle karega

dbg(f"📋 Parsed keys: {list(data.keys())}")

title = data.get('title', '').strip()
start_time = data.get('start_time', '00:00:10')
duration = data.get('clip_duration', 30)

# ✅ FIX: Normalize start_time format if model returns "00:00" instead of "00:00:00" or similar
if start_time.count(':') == 1:
    start_time = "00:" + start_time
elif not start_time:
    start_time = "00:00:10"

dbg(f"🎬 Title: '{title}'")
dbg(f"⏰ Start: '{start_time}'")
dbg(f"⏱️  Duration: {duration}")

if not title or len(title.split()) < 1:
    dbg(f"❌ Title invalid: '{title}'")
    print(json.dumps({"status": "failed", "error": "Title too short"}))
    sys.exit(0)

title = re.sub(r'[,\'"\-:\n\r]+', ' ', title).strip()
title = re.sub(r'\s+', ' ', title)

try:
    dur_int = max(12, min(45, int(duration)))
except:
    dur_int = 30

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

# ============================================================
# ✅ EXPLICIT EXIT 0 — pipeline continue guarantee
# ============================================================
exit 0
