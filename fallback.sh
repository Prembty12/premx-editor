#!/bin/bash
# ==============================================================================
# 🚀 OPENROUTER BASH AGENT (1 PRIMARY TRY + 20 FALLBACK RETRIES + BULLETPROOF PARSER)
# ==============================================================================

GRID_PATH="${GRID_PATH:-temp_frames/merged_60_grid_screenshot.jpg}"
SOURCE_DURATION="${SOURCE_DURATION:-60}"
INSIGHTS_SUMMARY="${INSIGHTS_SUMMARY:-}"
STYLE_PROMPT="${STYLE_PROMPT:-}"

# 🧠 Round-Robin Friendly Memory Loader: Sirf title styles aur winning context jayega (Game scores removed)
if [ -z "$INSIGHTS_SUMMARY" ] && [ -f "logs/agent_memory.json" ]; then
    INSIGHTS_SUMMARY=$(python3 -c "
import json
try:
    with open('logs/agent_memory.json', 'r') as f:
        data = json.load(f)
        styles = data.get('title_styles', {})
        winning_context = data.get('winning_title_context', 'No prior context')
        print(f'Title Styles Performance: {styles} | Past Winning Context: {winning_context}. STRICT INSTRUCTION: Since this runs on a round-robin game rotation, use these styles to understand what viewers like, but DO NOT copy past game names or scores. Write a brand-new, unique title strictly based on the current video grid image.')
except:
    print('')
")
fi

PRIMARY_MODEL="${OPENROUTER_MODEL:-dots-studio/dots-3-note-preview:free}"
FALLBACK_MODEL="openrouter/free"

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
Return JSON with exactly three keys as specified in the schema."

RAW_RESPONSE=""
SUCCESS_REQUESTED_MODEL=""
SUCCESS_ROUTED_MODEL=""

# 1 Primary Try + 20 Fallback Retries = Total 21 Attempts max
MAX_RETRIES=21

dbg ""
dbg "════════════════════════════════════════════════════════"
dbg "🚀 OPENROUTER AGENT START — $(date '+%Y-%m-%d %H:%M:%S')"
dbg "📁 Grid Path       : $GRID_PATH"
dbg "⏱️  Source Duration : ${SOURCE_DURATION}s"
dbg "🔑 Keys Loaded     : ${#KEYS[@]}"
dbg "🎯 Primary Model   : $PRIMARY_MODEL (Max 1 Try)"
dbg "🔄 Fallback Model  : $FALLBACK_MODEL (Max 20 Tries)"
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
    dbg "    Time       : $(date +%H:%M:%S)"
    
    # 🔍 Live Terminal Display of what is being sent to AI
    dbg "--------------------------------------------------------"
    dbg "📤 AI KO KYA-KYA BHEJ RAHA HAI (PAYLOAD DETAILS):"
    dbg "--------------------------------------------------------"
    dbg "  📁 Grid Image Path        : $GRID_PATH"
    dbg "  ⏱️ Source Duration        : ${SOURCE_DURATION}s"
    dbg "  💡 Insights / Memory Sent : ${INSIGHTS_SUMMARY:-[Khaali / Kuch nahi]}"
    dbg "  🎨 Style Directive        : ${STYLE_PROMPT:-[Khaali / Kuch nahi]}"
    dbg "  🤖 Target Model           : $CURRENT_MODEL"
    dbg "--------------------------------------------------------"
    
    PAYLOAD_FILE="temp_frames/or_payload.json"
    mkdir -p temp_frames
    
    export GRID_PATH CURRENT_MODEL PROMPT_TEXT PAYLOAD_FILE INSIGHTS_SUMMARY STYLE_PROMPT
    python3 - << 'PYEOF'
import os, json, base64

grid_path = os.environ.get('GRID_PATH')
model = os.environ.get('CURRENT_MODEL')
prompt = os.environ.get('PROMPT_TEXT')
payload_file = os.environ.get('PAYLOAD_FILE')

with open(grid_path, 'rb') as f:
    img_bytes = f.read()
    b64_img = base64.b64encode(img_bytes).decode('utf-8')

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
        'require_parameters': False if is_reasoning else True,
        'ignore': ['nvidia/nemotron-3.5-content-safety:free']
    }
}

with open(payload_file, 'w') as f:
    json.dump(payload, f)

import sys

print(f"    📸 Image Size : {len(img_bytes)} bytes (b64: {len(b64_img)} chars)", file=sys.stderr, flush=True)
print(f"    🧠 Is Reasoning: {is_reasoning}", file=sys.stderr, flush=True)
print(f"    🔧 require_parameters: {payload['provider']['require_parameters']}", file=sys.stderr, flush=True)
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
        dbg "    📥 Raw Response :"
        echo "$RESP" | head -c 2000 | sed 's/^/     /' >&2
        echo "" >&2
    fi

    ROUTED=$(echo "$RESP" | python3 -c "
import sys, json
try:
    print(json.load(sys.stdin).get('model', ''))
except: print('')
" 2>/dev/null)

    export ROUTED_CHECK="$ROUTED"
    IS_TEXT_AI=$(python3 -c "
import os
m = os.environ.get('ROUTED_CHECK', '').lower()
text_indicators = ['r1-distill', 'llama-3-8b', 'qwen-2.5-7b', 'gemma-2-9b', 'deepseek-chat', 'mistral-7b', 'text-only']
if any(t in m for t in text_indicators):
    print('yes')
else:
    print('no')
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
        IS_VALID_JSON=$(python3 -c '
import json, sys, re
raw_output = sys.argv[1]
try:
    clean_output = re.sub(r"```json\s*|\s*```", "", raw_output, flags=re.IGNORECASE).strip()
    clean_output = re.sub(r"<think>.*?</think>", "", clean_output, flags=re.DOTALL).strip()
    
    data = json.loads(clean_output)
    if not isinstance(data, dict) or not all(k in data for k in ("title", "start_time", "clip_duration")):
        print("invalid")
        sys.exit(0)
    
    print("valid")
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

cleaned = re.sub(r'```json\s*|\s*```', '', raw, flags=re.IGNORECASE).strip()
data = None

try:
    data = json.loads(cleaned)
    dbg("✅ Direct JSON parse SUCCESS")
except Exception:
    no_think = re.sub(r'<think>.*?</think>', '', cleaned, flags=re.DOTALL).strip()
    match = re.search(r'\{.*\}', no_think, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            dbg("✅ Regex JSON extract SUCCESS")
        except Exception:
            pass

if not data or not isinstance(data, dict):
    dbg("⚠️ JSON extraction completely failed. Running Bulletproof Text Scanner...")
    
    time_match = re.search(r'(\d{2}:\d{2}(?::\d{2})?)', raw)
    start_time = time_match.group(1) if time_match else "00:00:15"
    if len(start_time.split(':')) == 2:
        start_time = f"00:{start_time}"

    title = "Insane Tactical Play 🎯🔥"
    pure_text = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()
    lines = [l.strip() for l in pure_text.split('\n') if l.strip()]
    if not lines:
        lines = [l.strip() for l in raw.split('\n') if l.strip()]
        
    for line in lines:
        if any(skip in line.lower() for skip in ['parsing', 'scanning', 'analyze', 'schema', 'properties', 'json']):
            continue
        clean_l = re.sub(r'^\d+[\.\)]\s*|^[\-\*]\s*|[\*\#\`\"]', '', line).strip()
        if 10 <= len(clean_l) <= 50:
            title = clean_l
            break

    data = {
        "title": title,
        "start_time": start_time,
        "clip_duration": 20
    }

raw_title = data.get('title', 'Pro Gaming Moments 🎯🔥')

if isinstance(raw_title, list):
    raw_title = raw_title[0] if len(raw_title) > 0 else "Pro Gaming Moments 🎯🔥"
elif isinstance(raw_title, str):
    lines = [line.strip() for line in raw_title.split('\n') if line.strip()]
    raw_title = lines[0] if lines else "Pro Gaming Moments 🎯🔥"

title = re.sub(r'^\d+[\.\)]\s*|^[\-\*]\s*|[\*\#\`\"]', '', str(raw_title)).strip()
title = title.strip("'\"")
title = re.sub(r'\s+', ' ', title)

if not title:
    title = "Unstoppable Gaming Highlights 🎯🔥"

start_time = str(data.get('start_time', '00:00:15')).strip()
duration = data.get('clip_duration', 20)

try:
    dur_int = max(12, min(45, int(duration)))
except Exception:
    dur_int = 20

dbg(f"✅ Final Output Title: '{title}'")
dbg(f"✅ Final Start Time  : '{start_time}'")

print(json.dumps({
    "status": "success",
    "requested_model": req_m,
    "routed_model": rout_m,
    "title": title,
    "start_time": start_time,
    "duration": dur_int
}))
PYEOF
