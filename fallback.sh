#!/bin/bash
# ==============================================================================
# 🚀 OPENROUTER BASH AGENT — NO DEFAULT, RETRY UNTIL REAL RESULT
# ==============================================================================

GRID_PATH="${GRID_PATH:-temp_frames/merged_60_grid_screenshot.jpg}"
SOURCE_DURATION="${SOURCE_DURATION:-60}"
INSIGHTS_SUMMARY="${INSIGHTS_SUMMARY:-}"
STYLE_PROMPT="${STYLE_PROMPT:-}"

# Multiple models — ek se na mile to doosre pe jao
MODELS=(
    "${OPENROUTER_MODEL:-nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free}"
    "openrouter/free"
)

KEYS=()
[ -n "$OPENROUTER_API_KEY" ]   && KEYS+=("$OPENROUTER_API_KEY")
[ -n "$OPENROUTER_API_KEY_2" ] && KEYS+=("$OPENROUTER_API_KEY_2")
[ -n "$OPENROUTER_API_KEY_3" ] && KEYS+=("$OPENROUTER_API_KEY_3")
[ -n "$OPENROUTER_API_KEY_4" ] && KEYS+=("$OPENROUTER_API_KEY_4")
[ -n "$OPENROUTER_API_KEY_5" ] && KEYS+=("$OPENROUTER_API_KEY_5")

if [ ${#KEYS[@]} -eq 0 ]; then
    echo '{"status": "failed", "error": "No API keys"}'
    exit 1
fi

if [ ! -f "$GRID_PATH" ]; then
    echo "{\"status\": \"failed\", \"error\": \"Grid not found: $GRID_PATH\"}"
    exit 1
fi

get_random_key() {
    echo "${KEYS[$((RANDOM % ${#KEYS[@]}))]}"
}

PROMPT_TEXT="Analyze the provided 9:16 gaming screenshot grid. Video duration is ${SOURCE_DURATION}s.
Context: ${INSIGHTS_SUMMARY}
Style: ${STYLE_PROMPT}

Reply ONLY with a JSON object having EXACTLY these keys:
{"title": "viral title with 1-3 emojis", "start_time": "HH:MM:SS", "clip_duration": 15}
Start with { and end with }. No markdown. No explanation. No extra text."

MAX_ATTEMPTS=15   # badha diya — zyada retries
RAW_RESPONSE=""

for ((attempt=1; attempt<=MAX_ATTEMPTS; attempt++)); do
    CURRENT_KEY=$(get_random_key)
    MODEL_IDX=$(( (attempt - 1) % ${#MODELS[@]} ))
    CURRENT_MODEL="${MODELS[$MODEL_IDX]}"

    echo "🤖 [$attempt/$MAX_ATTEMPTS] Model: $CURRENT_MODEL | Key: ${CURRENT_KEY:0:8}..." >&2

    PAYLOAD_FILE="temp_frames/or_payload.json"
    mkdir -p temp_frames

    export GRID_PATH CURRENT_MODEL PROMPT_TEXT PAYLOAD_FILE
    python3 - << 'PYEOF'
import os, json, base64
with open(os.environ['GRID_PATH'], 'rb') as f:
    b64 = base64.b64encode(f.read()).decode()
payload = {
    'model': os.environ['CURRENT_MODEL'],
    'messages': [{'role': 'user', 'content': [
        {'type': 'text', 'text': os.environ['PROMPT_TEXT']},
        {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + b64}}
    ]}],
    'max_tokens': 512,
    'temperature': 0.3,
    'response_format': {'type': 'json_object'}
}
with open(os.environ['PAYLOAD_FILE'], 'w') as f:
    json.dump(payload, f)
PYEOF

    RESP=$(curl -s --connect-timeout 6 -m 20 -X POST "https://openrouter.ai/api/v1/chat/completions" \
        -H "Authorization: Bearer $CURRENT_KEY" \
        -H "Content-Type: application/json" \
        -d @"$PAYLOAD_FILE")
    rm -f "$PAYLOAD_FILE"

    CONTENT=$(echo "$RESP" | python3 -c "import sys,json
try:
    r=json.load(sys.stdin); ch=r.get('choices') or [{}]; m=ch[0].get('message') or {}
    print(m.get('content') or m.get('reasoning') or '')
except: print('')" 2>/dev/null)

    ROUTED=$(echo "$RESP" | python3 -c "import sys,json
try: print(json.load(sys.stdin).get('model',''))
except: print('')" 2>/dev/null)

    # ---------- STRICT VALIDATION — default nahi, sirf real chahiye ----------
    export RAW_RESPONSE="$CONTENT" ROUTED="$ROUTED" CURRENT_MODEL="$CURRENT_MODEL"

    VALID=$(python3 - << 'PYEOF'
import os, json, re, ast
raw = os.environ.get('RAW_RESPONSE','') or ''
cleaned = re.sub(r'```[a-zA-Z]*', '', raw).strip()

def try_parse(s):
    try: return json.loads(s)
    except: pass
    try: return ast.literal_eval(s)
    except: pass
    return None

data = try_parse(cleaned)
if not isinstance(data, dict):
    m = re.search(r'\{.*\}', cleaned, re.DOTALL)
    if m: data = try_parse(m.group(0))

if not isinstance(data, dict):
    print("INVALID"); raise SystemExit(0)

title = data.get('title')
start = data.get('start_time')
dur = data.get('clip_duration') or data.get('duration')

# Strict: teeno keys hone chahiye, khaali nahi hone chahiye
if not title or not str(title).strip():
    print("INVALID"); raise SystemExit(0)
if not start or not re.match(r'^\d{1,2}:\d{2}(:\d{2})?$', str(start).strip()):
    print("INVALID"); raise SystemExit(0)
try:
    dur_i = int(float(dur))
    if dur_i < 5 or dur_i > 120:
        print("INVALID"); raise SystemExit(0)
except:
    print("INVALID"); raise SystemExit(0)

# Normalize start to HH:MM:SS
s = str(start).strip()
if re.match(r'^\d{1,2}:\d{2}$', s):
    h,m = s.split(':'); s = f"00:{int(h):02d}:{int(m):02d}"
elif re.match(r'^\d{1,2}:\d{2}:\d{2}$', s):
    h,m,sec = s.split(':'); s = f"{int(h):02d}:{int(m):02d}:{int(sec):02d}"

print(json.dumps({
    "status": "success",
    "requested_model": os.environ.get('CURRENT_MODEL'),
    "routed_model": os.environ.get('ROUTED','') or os.environ.get('CURRENT_MODEL'),
    "title": str(title).strip()[:100],
    "start_time": s,
    "duration": dur_i
}))
PYEOF
)

    if [ "$VALID" != "INVALID" ] && [ -n "$VALID" ]; then
        echo "$VALID"
        echo "✅ Valid real result on attempt $attempt" >&2
        exit 0
    else
        echo "⚠️ Attempt $attempt: invalid/garbage. Retrying..." >&2
        sleep 1
    fi
done

# Sirf tab fail jab 15 attempts me bhi kuch valid na mile
echo '{"status": "failed", "error": "All 15 attempts returned invalid results from every model"}'
exit 1
