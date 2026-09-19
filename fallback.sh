#!/bin/bash
# ==============================================================================
# 🚀 OPENROUTER FALLBACK AGENT (STRICT NO-DEFAULTS EDITION)
# Strict JSON Validation + No Defaults + Detailed Missing Field Debug
# ==============================================================================

export TZ='Asia/Kolkata'
if ! date '+%Z' 2>/dev/null | grep -qi 'IST'; then
    export TZ='IST-5:30'
fi

GRID_PATH="${GRID_PATH:-temp_frames/merged_90_grid_portrait.jpg}"
SOURCE_DURATION="${SOURCE_DURATION:-60}"
STYLE_PROMPT="${STYLE_PROMPT:-}"

PRIMARY_MODEL="${OPENROUTER_MODEL:-dots-studio/dots-3-note-preview:free}"
FALLBACK_MODEL="openrouter/free"
DEBUG="${DEBUG:-1}"
SAVE_DEBUG="${SAVE_DEBUG:-1}"
DEBUG_DIR="temp_frames/debug"
mkdir -p "$DEBUG_DIR"

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
    echo "{\"status\": \"failed\", \"error\": \"Grid not found at $GRID_PATH\"}"
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
# 🚀 STRICT PROMPT — ALL FIELDS MANDATORY + NO TRUNCATION
# ══════════════════════════════════════════════════════════════
PROMPT_TEXT="Analyze the provided 9:16 gaming screenshot grid. 

CRITICAL NOTICE: The total video source duration is EXACTLY ${SOURCE_DURATION} seconds. This duration is dynamic and changes for every video. You MUST use the exact number provided here: ${SOURCE_DURATION} seconds.

Style Directive: ${STYLE_PROMPT}

YOUR TASK: Decide APPROVE or REJECT for this video.

REJECT IF (Strictly reject if content is boring, empty, or lacks engagement):
- Grid shows ONLY menus, map screens, inventory checking, shopping, or loading screens
- No actual gameplay or action visible in ANY frame
- All frames look identical, frozen, or useless (boring walking/running without anything happening)
- Crash screen, error, black frames, or dead/idle moments dominate
- Absolutely NO exciting, thrilling, or engaging moment (agar video bekar ya faltu lage toh turant REJECT karo)

APPROVE IF:
- Real gameplay has a clear, powerful \"Engaging Highlight Window\" (combat, intense fights, epic boss battles, explosions, emotional cutscenes, hilarious fails, or high-stakes clutch moments).
- The moment has a clear start and end point in the timestamps.
- Absolute Cinematic & Engagement Mastery Rule: Prioritize pure hype, adrenaline, emotion, comedy, and entertainment above all else. Whether it's an epic fight, a deep emotional drama, a hilarious adventure, or a high-stakes moment that is genuinely gripping, commit to the *full sequence* from its absolute beginning to its natural end. Never force an artificial cut or clip truncation on a brilliant moment—allow the entire momentum, tension, comedy, and payoff of the gameplay to breathe and play out completely so the audience gets maximum satisfaction.
TITLE RULES (only for APPROVE):
- Create a short, viral title under 6 words with 1-3 emojis
- NO generic boring words like Epic, Insane, Crazy, Best, Gameplay

STRICT JSON OUTPUT — ALL FIELDS MANDATORY:

If REJECT:
{\"status\": \"REJECT\", \"reason\": \"<short reason max 10 words, e.g., No action or boring walking>\"}

If APPROVE, ALL 5 FIELDS ARE MANDATORY:
{
  \"status\": \"APPROVE\",
  \"title\": \"<viral title 6 words max with 1-3 emojis>\",
  \"start_time\": <integer seconds, exact second where the engaging moment starts>,
  \"clip_duration\": <integer seconds, minimum 12 seconds. Capture the FULL fight or highlight completely from start to finish, do not cut it short!>,
  \"reason\": \"<short explanation MAX 10 words>\"
}

CRITICAL - HOW TO CALCULATE START_TIME AND CLIP_DURATION (Total Video Length = ${SOURCE_DURATION} seconds):
1. The video starts at 0s and ends at EXACTLY ${SOURCE_DURATION}s.
2. Look at the timestamps on the grid carefully. Identify the exact second the ENGAGING MOMENT STARTS and the exact second it ENDS. 
3. Set 'start_time' to when this moment begins.
4. Calculate 'clip_duration' by subtracting start_time from end_time to cover the **entire** action sequence. Do not leave out the middle or end of a good fight.
5. STRICT MATH RULE: Your 'start_time' + 'clip_duration' MUST NOT exceed the total video length of ${SOURCE_DURATION} seconds.
6. MINIMUM DURATION: The clip must be at least 15 seconds. 

⚠️ CRITICAL — MISSING ANY FIELD = INVALID RESPONSE:
1. 'status' is MANDATORY (APPROVE or REJECT)
2. If APPROVE: title, start_time, clip_duration, reason ALL required
3. If REJECT: only status and reason required
4. NO markdown, NO extra text, NO escaped quotes, ONLY the JSON object
5. NO null values, NO empty values
6. STOP GENERATING immediately after the closing curly bracket 'J'. DO NOT TRUNCATE.
7. KEEP YOUR RESPONSE AS SHORT AS POSSIBLE. Do not write long explanations.

VALID EXAMPLE (REJECT):
{\"status\": \"REJECT\", \"reason\": \"Only menu navigation and boring running\"}

VALID EXAMPLE (APPROVE):
{\"status\": \"APPROVE\", \"title\": \"I Had One Chance 🚀\", \"start_time\": 5, \"clip_duration\": 25, \"reason\": \"Full combat sequence covered\"}

Return the JSON object now:"

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
dbg "⚙️  Defaults        : NONE (Strict No-Defaults Policy)"
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
    
    PAYLOAD_FILE="temp_frames/or_payload.json"
    mkdir -p temp_frames
    
    export GRID_PATH CURRENT_MODEL PROMPT_TEXT PAYLOAD_FILE SOURCE_DURATION
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
    "required": ["status", "reason", "title", "start_time", "clip_duration"],
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
    'max_tokens': 8192,       # Increased to prevent truncation
    'temperature': 0.1,       # Decreased for strict JSON adherence
    'response_format': {
        'type': 'json_schema',
        'json_schema': {
            'name': 'video_edit_params',
            'strict': True,   # Enforce strict schema at API level
            'schema': schema
        }
    },
    'provider': {
        'require_parameters': True, # Force model to respect schema
        'ignore': ['nvidia/nemotron-3.5-content-safety:free']
    }
}

with open(payload_file, 'w') as f:
    json.dump(payload, f)
PYEOF

    # 📤 Full payload debug
    IMG_SIZE_BYTES=$(wc -c < "$GRID_PATH" 2>/dev/null || echo "unknown")
    PAYLOAD_SIZE_BYTES=$(wc -c < "$PAYLOAD_FILE" 2>/dev/null || echo "unknown")
    
    dbg ""
    dbg "────────────────────────────────────────────────────────"
    dbg "📤 AI KO KYA BHEJ RAHA HAI:"
    dbg "────────────────────────────────────────────────────────"
    dbg "  📁 Grid       : $GRID_PATH (${IMG_SIZE_BYTES} bytes)"
    dbg "  🎞️  Duration   : ${SOURCE_DURATION}s"
    dbg "  🎨 Style      : ${STYLE_PROMPT:-[empty]}"
    dbg "  🤖 Model      : $CURRENT_MODEL"
    dbg "  📦 Payload    : ${PAYLOAD_SIZE_BYTES} bytes"
    dbg "--------------------------------------------------------"

    if [ "$SAVE_DEBUG" = "1" ]; then
        cp "$PAYLOAD_FILE" "$DEBUG_DIR/payload_attempt_${attempt}.json" 2>/dev/null
    fi

    dbg "    📡 Sending request to OpenRouter..."
    
    HTTP_CODE=$(curl -s -o /tmp/or_response_$$.json -w "%{http_code}" \
        --connect-timeout 15 -m 90 \
        -X POST "https://openrouter.ai/api/v1/chat/completions" \
        -H "Authorization: Bearer $CURRENT_KEY" \
        -H "Content-Type: application/json" \
        -d @"$PAYLOAD_FILE")
    
    RESP=$(cat /tmp/or_response_$$.json 2>/dev/null)
    rm -f /tmp/or_response_$$.json "$PAYLOAD_FILE"

    dbg "    📥 HTTP Status  : $HTTP_CODE"
    
    if [ "$SAVE_DEBUG" = "1" ]; then
        echo "$RESP" > "$DEBUG_DIR/response_attempt_${attempt}.json" 2>/dev/null
    fi

    ROUTED=$(echo "$RESP" | python3 -c "
import sys, json
try: print(json.load(sys.stdin).get('model', ''))
except: print('')
" 2>/dev/null)

    dbg "    🎯 Routed Model : ${ROUTED:-unknown}"

    export ROUTED_CHECK="$ROUTED"
    IS_TEXT_AI=$(python3 -c "
import os
m = os.environ.get('ROUTED_CHECK', '').lower()
ti = ['r1-distill', 'llama-3-8b', 'qwen-2.5-7b', 'gemma-2-9b', 'deepseek-chat', 'mistral-7b', 'text-only']
print('yes' if any(t in m for t in ti) else 'no')
")

    if [ "$IS_TEXT_AI" = "yes" ]; then
        dbg "    ❌ Text-only model. Retrying..."
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
    else: print('')
except: print('')
" 2>/dev/null)

    # 📥 Full AI Response debug
    if [ -n "$CONTENT" ] && [ "$CONTENT" != "None" ]; then
        dbg ""
        dbg "    📥 📥 📥 AI KA FULL RESPONSE:"
        dbg "    ┌────────────────────────────────────────────────────"
        echo "$CONTENT" | sed 's/^/    │ /' >&2
        dbg "    └────────────────────────────────────────────────────"
        dbg ""
        
        if [ "$SAVE_DEBUG" = "1" ]; then
            echo "$CONTENT" > "$DEBUG_DIR/content_attempt_${attempt}.txt" 2>/dev/null
        fi
        
        # ══════════════════════════════════════════════════════════
        # VALIDATION — NO DEFAULTS, EXACT MISSING FIELD TRACKING
        # ══════════════════════════════════════════════════════════
        IS_VALID_JSON=$(CONTENT="$CONTENT" python3 << 'PYEOF'
import os, json, re, sys

raw = os.environ.get('CONTENT', '')

def parse_json(raw_input):
    if not raw_input:
        return "invalid"
    
    clean = re.sub(r"```json\s*|\s*```", "", raw_input, flags=re.IGNORECASE).strip()
    clean = re.sub(r"<think>.*?</think>", "", clean, flags=re.DOTALL).strip()
    clean = clean.rstrip().rstrip(",")
    
    # Method 1: Direct parse
    try:
        d = json.loads(clean)
        if isinstance(d, dict): return d
    except: pass
    
    # Method 2: Regex extract
    match = re.search(r"\{.*\}", clean, re.DOTALL)
    if match:
        try:
            d = json.loads(match.group(0))
            if isinstance(d, dict): return d
        except: pass
    
    # Method 3: Fix escaped quotes
    fixed = clean.replace(chr(92) + chr(34), chr(34))
    try:
        d = json.loads(fixed)
        if isinstance(d, dict): return d
    except: pass
    
    # Method 4: Double-encoded
    if clean.startswith(chr(34)):
        try:
            inner = json.loads(clean)
            if isinstance(inner, str):
                inner_clean = re.sub(r"```json\s*|\s*```", "", inner.strip(), flags=re.IGNORECASE).strip()
                try:
                    d = json.loads(inner_clean)
                    if isinstance(d, dict): return d
                except: pass
                match = re.search(r"\{.*\}", inner_clean, re.DOTALL)
                if match:
                    try:
                        d = json.loads(match.group(0))
                        if isinstance(d, dict): return d
                    except: pass
        except: pass
    
    # Method 5: Manual regex — EXACT MISSING FIELDS LOGGING
    status_match = re.search(r'"status"\s*:\s*"([^"]+)"', clean)
    if status_match:
        status_val = status_match.group(1).upper()
        title_match = re.search(r'"title"\s*:\s*"([^"]*)"', clean)
        st_match = re.search(r'"start_time"\s*:\s*(\d+)', clean)
        dur_match = re.search(r'"clip_duration"\s*:\s*(\d+)', clean)
        reason_match = re.search(r'"reason"\s*:\s*"([^"]*)"', clean)
        
        # 🚫 REJECT
        if status_val == "REJECT":
            return {"status": "reject", "reason": reason_match.group(1) if reason_match else ""}
        
        # ✅ APPROVE — STRICT CHECK, NO DEFAULTS
        if status_val == "APPROVE":
            missing = []
            if not title_match: missing.append("title")
            if not st_match: missing.append("start_time")
            if not dur_match: missing.append("clip_duration")
            
            if missing:
                return f"invalid:missing:{','.join(missing)}"
            
            return {
                "status": "APPROVE",
                "title": title_match.group(1),
                "start_time": int(st_match.group(1)),
                "clip_duration": int(dur_match.group(1)),
                "reason": reason_match.group(1) if reason_match else ""
            }
    
    return "invalid"


data = parse_json(raw)

if data == "invalid" or not isinstance(data, dict):
    if isinstance(data, str) and data.startswith("invalid:"):
        print(data)
    else:
        print("invalid")
    sys.exit(0)

status = str(data.get("status", "")).upper()

# ✅ REJECT
if status == "REJECT":
    print("valid")
    sys.exit(0)

# ✅ APPROVE — all fields must be present
if status == "APPROVE" and all(k in data for k in ("title", "start_time", "clip_duration")):
    print("valid")
    sys.exit(0)

print("invalid")
PYEOF
)

        if [ "$IS_VALID_JSON" = "valid" ]; then
            dbg "    ✅ SUCCESS — Valid JSON detected!"
            RAW_RESPONSE="$CONTENT"
            SUCCESS_REQUESTED_MODEL="$CURRENT_MODEL"
            SUCCESS_ROUTED_MODEL="${ROUTED:-$CURRENT_MODEL}"
            break
        elif [[ "$IS_VALID_JSON" == invalid:missing:* ]]; then
            MISSING_FIELDS="${IS_VALID_JSON#invalid:missing:}"
            dbg "    ⚠️  Invalid JSON. Missing fields: $MISSING_FIELDS. Retrying..."
            sleep 1.5
            continue
        else
            dbg "    ⚠️  Invalid JSON (format issue). Retrying..."
            sleep 1.5
            continue
        fi
    else
        dbg "    ⚠️  Empty content. Retrying..."
        sleep 1.5
    fi
done

if [ -z "$RAW_RESPONSE" ]; then
    dbg "❌ ALL ATTEMPTS FAILED"
    echo '{"status": "failed", "error": "All 21 OpenRouter attempts failed"}'
    exit 1
fi

RESPONSE_FILE="temp_frames/or_response.txt"
printf "%s" "$RAW_RESPONSE" > "$RESPONSE_FILE"

dbg ""
dbg "════════════════════════════════════════════════════════"
dbg "🧹 FINAL PARSING PHASE"
dbg "════════════════════════════════════════════════════════"

export REQUESTED_MODEL="$SUCCESS_REQUESTED_MODEL" ROUTED_MODEL="$SUCCESS_ROUTED_MODEL" RESPONSE_FILE DEBUG SOURCE_DURATION
python3 - << 'PYEOF'
import os, json, re, sys
from datetime import datetime, timedelta, timezone

def get_ist_now():
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S IST")
    except: pass
    ist = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(ist).strftime("%Y-%m-%d %H:%M:%S IST")

ist_now = get_ist_now()
rf = os.environ.get('RESPONSE_FILE')
req_m = os.environ.get('REQUESTED_MODEL', '')
rout_m = os.environ.get('ROUTED_MODEL', '')
debug = os.environ.get('DEBUG', '0') == '1'
sd = int(os.environ.get('SOURCE_DURATION', 60))

def dbg(msg):
    if debug:
        print(msg, file=sys.stderr, flush=True)

try:
    with open(rf, 'r', encoding='utf-8') as f:
        raw = f.read()
except:
    raw = ""

if os.path.exists(rf):
    os.remove(rf)


def parse_json(raw_input):
    if not raw_input:
        return None
    
    clean = re.sub(r"```json\s*|\s*```", "", raw_input, flags=re.IGNORECASE).strip()
    clean = re.sub(r"<think>.*?</think>", "", clean, flags=re.DOTALL).strip()
    clean = clean.rstrip().rstrip(",")
    
    try:
        d = json.loads(clean)
        if isinstance(d, dict): return d
    except: pass
    
    match = re.search(r"\{.*\}", clean, re.DOTALL)
    if match:
        try:
            d = json.loads(match.group(0))
            if isinstance(d, dict): return d
        except: pass
    
    fixed = clean.replace(chr(92) + chr(34), chr(34))
    try:
        d = json.loads(fixed)
        if isinstance(d, dict): return d
    except: pass
    
    if clean.startswith(chr(34)):
        try:
            inner = json.loads(clean)
            if isinstance(inner, str):
                inner_clean = re.sub(r"```json\s*|\s*```", "", inner.strip(), flags=re.IGNORECASE).strip()
                try:
                    d = json.loads(inner_clean)
                    if isinstance(d, dict): return d
                except: pass
                match = re.search(r"\{.*\}", inner_clean, re.DOTALL)
                if match:
                    try:
                        d = json.loads(match.group(0))
                        if isinstance(d, dict): return d
                    except: pass
        except: pass
    
    # Method 5: Manual regex — NO DEFAULTS
    status_match = re.search(r'"status"\s*:\s*"([^"]+)"', clean)
    if status_match:
        status_val = status_match.group(1).upper()
        title_match = re.search(r'"title"\s*:\s*"([^"]*)"', clean)
        st_match = re.search(r'"start_time"\s*:\s*(\d+)', clean)
        dur_match = re.search(r'"clip_duration"\s*:\s*(\d+)', clean)
        reason_match = re.search(r'"reason"\s*:\s*"([^"]*)"', clean)
        
        if status_val == "REJECT":
            return {"status": "reject", "reason": reason_match.group(1) if reason_match else ""}
        
        if status_val == "APPROVE":
            if not title_match or not st_match or not dur_match:
                return None # Strictly return None if missing, NO DEFAULTS
            return {
                "status": "APPROVE",
                "title": title_match.group(1),
                "start_time": int(st_match.group(1)),
                "clip_duration": int(dur_match.group(1)),
                "reason": reason_match.group(1) if reason_match else ""
            }
    
    return None


data = parse_json(raw)

if not data or not isinstance(data, dict):
    dbg("❌ Parsing failed completely.")
    print(json.dumps({"status": "failed", "error": "Parse failed"}))
    sys.exit(1)

status_field = str(data.get('status', '')).strip().upper()
reason_text = str(data.get('reason', '')).strip() or "(no reason provided)"

# 🚫 REJECT
if status_field == 'REJECT':
    dbg("")
    dbg("════════════════════════════════════════════════════════")
    dbg("🚫 AI NE REJECT KIYA")
    dbg("════════════════════════════════════════════════════════")
    dbg(f"  💬 Reason     : {reason_text}")
    dbg(f"  🤖 Routed     : {rout_m}")
    dbg(f"  🕐 Time (IST) : {ist_now}")
    dbg("")
    
    print(json.dumps({
        "status": "reject",
        "reason": reason_text,
        "requested_model": req_m,
        "routed_model": rout_m,
        "timestamp_ist": ist_now
    }))
    sys.exit(0)

# ✅ APPROVE — STRICT CHECK, NO DEFAULTS
missing = [k for k in ("title", "start_time", "clip_duration") if k not in data]
if missing:
    dbg(f"❌ Missing fields at final validation: {missing}")
    print(json.dumps({"status": "failed", "error": f"Missing fields at final validation: {missing}"}))
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
    if dur_int < 15 or dur_int > sd:
        raise ValueError(f"Duration out of bounds")
except Exception as e:
    dbg(f"❌ Invalid duration: {duration} ({e})")
    print(json.dumps({"status": "failed", "error": f"Invalid duration: {duration}"}))
    sys.exit(1)

dbg("")
dbg("════════════════════════════════════════════════════════")
dbg("✅ AI NE APPROVE KIYA")
dbg("════════════════════════════════════════════════════════")
dbg(f"  🎬 Title      : {title}")
dbg(f"  ⏱️  Start Time : {start_time_val}s")
dbg(f"  ⏳ Duration   : {dur_int}s")
dbg(f"  💬 Reason     : {reason_text}")
dbg(f"  🤖 Routed     : {rout_m}")
dbg(f"  🕐 Time (IST) : {ist_now}")
dbg("")

print(json.dumps({
    "status": "success",
    "requested_model": req_m,
    "routed_model": rout_m,
    "title": title,
    "start_time": start_time_val,
    "duration": dur_int,
    "reason": reason_text,
    "timestamp_ist": ist_now
}))
PYEOF
