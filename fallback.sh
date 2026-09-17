#!/bin/bash
# ==============================================================================
# 🚀 OPENROUTER BASH AGENT
# 3 Attempts Loop + Har REJECT pe Shift + Fallback Support
# ==============================================================================

export TZ='Asia/Kolkata'
if ! date '+%Z' 2>/dev/null | grep -qi 'IST'; then
    export TZ='IST-5:30'
fi

GRID_PATH="${GRID_PATH:-temp_frames/merged_60_grid_screenshot.jpg}"
SOURCE_DURATION="${SOURCE_DURATION:-60}"
STYLE_PROMPT="${STYLE_PROMPT:-}"
EDITOR_FILE="${EDITOR_FILE:-game_links_editor/game.txt}"
GAME_NAME="${GAME_NAME:-game}"

SHIFT_DIR="game_links_shift"
mkdir -p "$SHIFT_DIR" "temp_frames" "logs"
SHIFT_LOG="$SHIFT_DIR/${GAME_NAME}_shift_links.txt"

PRIMARY_MODEL="${OPENROUTER_MODEL:-dots-studio/dots-3-note-preview:free}"
FALLBACK_MODEL="openrouter/free"

DEBUG="${DEBUG:-1}"

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
# PROMPT WITH APPROVE/REJECT
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

RESPONSE FORMAT (STRICT JSON, no markdown):

If REJECT:
{\"status\": \"REJECT\", \"reason\": \"<1-line explanation>\"}

If APPROVE:
{\"status\": \"APPROVE\", \"title\": \"<viral title under 6 words with 1-3 emojis>\", \"start_time\": <integer seconds, 0 to $((SOURCE_DURATION - 15))>, \"clip_duration\": <integer 15-${SOURCE_DURATION}>, \"reason\": \"<1-line reason>\"}

Return ONLY the JSON object."

# ══════════════════════════════════════════════════════════════
# MAIN LOOP — 3 Attempts
# ══════════════════════════════════════════════════════════════
MAX_ATTEMPTS=3
ATTEMPT_NUM=0
FINAL_STATUS=""
FINAL_RESULT=""
LAST_REASON=""

while [ $ATTEMPT_NUM -lt $MAX_ATTEMPTS ]; do
    ATTEMPT_NUM=$((ATTEMPT_NUM + 1))
    
    dbg ""
    dbg "════════════════════════════════════════════════════════"
    dbg "🔁 SCRIPT ATTEMPT $ATTEMPT_NUM / $MAX_ATTEMPTS"
    dbg "   🕐 $(date '+%Y-%m-%d %H:%M:%S IST')"
    dbg "════════════════════════════════════════════════════════"
    
    # ────────────────────────────────────────
    # Pick a new link from editor
    # ────────────────────────────────────────
    if [ ! -f "$EDITOR_FILE" ]; then
        echo "❌ Editor file nahi mili: $EDITOR_FILE"
        FINAL_STATUS="failed"
        break
    fi
    
    CURRENT_LINK=$(python3 -c "
import os, random, sys
ef = os.environ.get('EDITOR_FILE')
if not os.path.exists(ef):
    print(''); sys.exit(0)
with open(ef, 'r', encoding='utf-8', errors='ignore') as f:
    lines = [l.strip() for l in f if l.strip() and not l.strip().startswith('#')]
if not lines:
    print(''); sys.exit(0)
print(random.choice(lines))
")
    
    if [ -z "$CURRENT_LINK" ]; then
        echo "❌ Editor mein koi link nahi bacha"
        FINAL_STATUS="failed"
        break
    fi
    
    export CURRENT_LINK
    
    echo "🔗 Link      : $CURRENT_LINK"
    echo "   (Editor se naya link uthaya)"
    echo ""
    
    # ────────────────────────────────────────
    # OpenRouter AI Call
    # ────────────────────────────────────────
    RAW_RESPONSE=""
    SUCCESS_REQUESTED_MODEL=""
    SUCCESS_ROUTED_MODEL=""
    MAX_RETRIES=21
    
    for ((a=1; a<=MAX_RETRIES; a++)); do
        CURRENT_KEY=$(get_random_openrouter_key)
        KEY_DISPLAY="${CURRENT_KEY:0:12}...${CURRENT_KEY: -4}"
        
        if [ $a -eq 1 ]; then
            CURRENT_MODEL="$PRIMARY_MODEL"
        else
            CURRENT_MODEL="$FALLBACK_MODEL"
        fi
        
        dbg ""
        dbg "────────────────────────────────────────────────────────"
        dbg "🤖 OpenRouter ATTEMPT $a / $MAX_RETRIES"
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
PYEOF

        dbg "    📡 Sending to OpenRouter..."
        
        HTTP_CODE=$(curl -s -o /tmp/or_resp_$$.json -w "%{http_code}" \
            --connect-timeout 15 -m 90 \
            -X POST "https://openrouter.ai/api/v1/chat/completions" \
            -H "Authorization: Bearer $CURRENT_KEY" \
            -H "Content-Type: application/json" \
            -d @"$PAYLOAD_FILE")
        
        RESP=$(cat /tmp/or_resp_$$.json 2>/dev/null)
        rm -f /tmp/or_resp_$$.json "$PAYLOAD_FILE"
        
        dbg "    📥 HTTP Status  : $HTTP_CODE"
        
        ROUTED=$(echo "$RESP" | python3 -c "
import sys, json
try: print(json.load(sys.stdin).get('model', ''))
except: print('')
" 2>/dev/null)
        
        export ROUTED_CHECK="$ROUTED"
        IS_TEXT_AI=$(python3 -c "
import os
m = os.environ.get('ROUTED_CHECK', '').lower()
ti = ['r1-distill', 'llama-3-8b', 'qwen-2.5-7b', 'gemma-2-9b', 'deepseek-chat', 'mistral-7b', 'text-only']
print('yes' if any(t in m for t in ti) else 'no')
")
        
        if [ "$IS_TEXT_AI" = "yes" ]; then
            dbg "    ❌ Text-only model ($ROUTED). Retrying..."
            sleep 1
            continue
        fi
        
        CONTENT=$(echo "$RESP" | python3 -c "
import sys, json
try:
    r = json.load(sys.stdin)
    ch = r.get('choices', [])
    if ch:
        m = ch[0].get('message', {})
        print(m.get('content', '') or m.get('reasoning', ''))
    else: print('')
except: print('')
" 2>/dev/null)
        
        if [ -n "$CONTENT" ] && [ "$CONTENT" != "None" ]; then
            IS_VALID=$(python3 -c '
import json, sys, re
raw = sys.argv[1]
try:
    c = re.sub(r"```json\s*|\s*```", "", raw, flags=re.IGNORECASE).strip()
    c = re.sub(r"<think>.*?</think>", "", c, flags=re.DOTALL).strip()
    d = json.loads(c)
    if not isinstance(d, dict): print("invalid"); sys.exit(0)
    s = str(d.get("status", "")).upper()
    if s == "REJECT": print("valid"); sys.exit(0)
    if s == "APPROVE" and all(k in d for k in ("title","start_time","clip_duration")):
        print("valid"); sys.exit(0)
    if all(k in d for k in ("title","start_time","clip_duration")):
        print("valid"); sys.exit(0)
    print("invalid")
except: print("invalid")
' "$CONTENT")
            
            if [ "$IS_VALID" = "valid" ]; then
                dbg "    ✅ SUCCESS — Valid JSON!"
                RAW_RESPONSE="$CONTENT"
                SUCCESS_REQUESTED_MODEL="$CURRENT_MODEL"
                SUCCESS_ROUTED_MODEL="${ROUTED:-$CURRENT_MODEL}"
                break
            else
                dbg "    ⚠️  Invalid JSON. Retrying..."
                sleep 1.5
                continue
            fi
        else
            dbg "    ⚠️  Empty content. Retrying..."
            sleep 1.5
        fi
    done
    
    # ────────────────────────────────────────
    # Parse Response
    # ────────────────────────────────────────
    if [ -z "$RAW_RESPONSE" ]; then
        PARSED_STATUS="failed"
        PARSED_REASON="All OpenRouter attempts failed"
    else
        RESPONSE_FILE="temp_frames/or_response.txt"
        printf "%s" "$RAW_RESPONSE" > "$RESPONSE_FILE"
        
        export REQUESTED_MODEL="$SUCCESS_REQUESTED_MODEL" ROUTED_MODEL="$SUCCESS_ROUTED_MODEL" RESPONSE_FILE DEBUG SOURCE_DURATION CURRENT_LINK
        PARSE_OUTPUT=$(python3 - << 'PYEOF'
import os, json, re, sys
rf = os.environ.get('RESPONSE_FILE')
req_m = os.environ.get('REQUESTED_MODEL', '')
rout_m = os.environ.get('ROUTED_MODEL', '')
sd = int(os.environ.get('SOURCE_DURATION', 60))

try:
    with open(rf) as f: raw = f.read()
except: raw = ""
if os.path.exists(rf): os.remove(rf)

clean = re.sub(r'```json\s*|\s*```', '', raw, flags=re.IGNORECASE).strip()
clean = re.sub(r'<think>.*?</think>', '', clean, flags=re.DOTALL).strip()

d = None
try: d = json.loads(clean)
except:
    m = re.search(r'\{.*\}', clean, re.DOTALL)
    if m:
        try: d = json.loads(m.group(0))
        except: pass

if not d or not isinstance(d, dict):
    print(json.dumps({"status": "failed", "error": "parse fail"}))
    sys.exit(0)

sf = str(d.get('status', '')).upper()
rn = str(d.get('reason', '')).strip() or "(no reason)"

if sf == 'REJECT':
    print(json.dumps({"status": "reject", "reason": rn, "requested_model": req_m, "routed_model": rout_m}))
    sys.exit(0)

if not all(k in d for k in ("title","start_time","clip_duration")):
    print(json.dumps({"status": "failed", "error": "missing keys"}))
    sys.exit(0)

rt = d.get('title', '')
if isinstance(rt, list): rt = rt[0] if rt else ""
elif isinstance(rt, str):
    ls = [l.strip() for l in rt.split('\n') if l.strip()]
    rt = ls[0] if ls else ""

title = re.sub(r'^\d+[\.\)]\s*|^[\-\*]\s*|[\*\#\`\"]', '', str(rt)).strip().strip("'\"")

try: st = int(d.get('start_time', 0))
except:
    m = re.search(r'\d+', str(d.get('start_time', '0')))
    st = int(m.group(0)) if m else 0
if st < 0: st = 0

try:
    dr = int(d.get('clip_duration', 15))
    if dr < 15 or dr > sd: raise ValueError()
except:
    print(json.dumps({"status": "failed", "error": "invalid duration"}))
    sys.exit(0)

print(json.dumps({
    "status": "success",
    "requested_model": req_m,
    "routed_model": rout_m,
    "title": title,
    "start_time": st,
    "duration": dr,
    "reason": rn
}))
PYEOF
)
        PARSED_STATUS=$(echo "$PARSE_OUTPUT" | python3 -c "import sys,json;print(json.load(sys.stdin).get('status','failed'))" 2>/dev/null)
        PARSED_REASON=$(echo "$PARSE_OUTPUT" | python3 -c "import sys,json;print(json.load(sys.stdin).get('reason',''))" 2>/dev/null)
        FINAL_RESULT="$PARSE_OUTPUT"
    fi
    
    # ────────────────────────────────────────
    # If OpenRouter FAILED → try fallback.sh
    # ────────────────────────────────────────
    if [ "$PARSED_STATUS" == "failed" ]; then
        if [ -f "fallback.sh" ]; then
            echo "⚠️  OpenRouter failed — Fallback AI try kar raha hoon..."
            export GRID_PATH SOURCE_DURATION STYLE_PROMPT CURRENT_LINK
            
            FB_OUTPUT=$(bash fallback.sh)
            FB_STATUS=$(echo "$FB_OUTPUT" | python3 -c "import sys,json;print(json.load(sys.stdin).get('status','failed'))" 2>/dev/null)
            FB_REASON=$(echo "$FB_OUTPUT" | python3 -c "import sys,json;print(json.load(sys.stdin).get('reason',''))" 2>/dev/null)
            
            echo "   🧠 Fallback status: $FB_STATUS"
            
            if [ "$FB_STATUS" == "success" ]; then
                PARSED_STATUS="success"
                PARSED_REASON="$FB_REASON"
                FINAL_RESULT="$FB_OUTPUT"
            elif [ "$FB_STATUS" == "reject" ]; then
                PARSED_STATUS="reject"
                PARSED_REASON="$FB_REASON (fallback)"
                FINAL_RESULT="$FB_OUTPUT"
            fi
        else
            echo "⚠️  fallback.sh not found — skipping fallback"
        fi
    fi
    
    # ════════════════════════════════════════════
    # DECIDE
    # ════════════════════════════════════════════
    
    # ✅ APPROVE → SCRIPT BAND
    if [ "$PARSED_STATUS" == "success" ]; then
        echo ""
        echo "✅ AI NE APPROVE KIYA (Attempt $ATTEMPT_NUM/$MAX_ATTEMPTS)"
        echo "🏁 Script band — kaam khatam!"
        FINAL_STATUS="approved"
        break
    fi
    
    # 🚫 REJECT → SHIFT LINK
    if [ "$PARSED_STATUS" == "reject" ]; then
        LAST_REASON="$PARSED_REASON"
        echo ""
        echo "🚫 AI NE REJECT KIYA (Attempt $ATTEMPT_NUM/$MAX_ATTEMPTS)"
        echo "   💬 Reason : $PARSED_REASON"
        echo "   🔗 Link   : $CURRENT_LINK"
        echo ""
        echo "📦 Link ko SHIFT kar raha hoon..."
        
        echo "$CURRENT_LINK | REJECT: $PARSED_REASON" >> "$SHIFT_LOG"
        echo "   ✅ Shift file: $SHIFT_LOG"
        
        if [ -f "$EDITOR_FILE" ]; then
            grep -vxF "$CURRENT_LINK" "$EDITOR_FILE" > "${EDITOR_FILE}.tmp"
            mv "${EDITOR_FILE}.tmp" "$EDITOR_FILE"
            echo "   🗑️  Editor se remove: $EDITOR_FILE"
        fi
        
        if [ $ATTEMPT_NUM -lt $MAX_ATTEMPTS ]; then
            echo ""
            echo "   🔁 Naya link try karega (attempt $((ATTEMPT_NUM+1))/$MAX_ATTEMPTS)..."
            sleep 3
            continue
        else
            echo ""
            echo "   ⚠️  3 attempts khatam — script band"
            FINAL_STATUS="exhausted"
            break
        fi
    fi
    
    # ❌ FAIL (both OpenRouter and fallback failed)
    if [ "$PARSED_STATUS" == "failed" ]; then
        echo ""
        echo "❌ AI FAILED (Attempt $ATTEMPT_NUM/$MAX_ATTEMPTS)"
        echo "   💬 Error: $PARSED_REASON"
        
        if [ $ATTEMPT_NUM -lt $MAX_ATTEMPTS ]; then
            echo "   🔁 Retry..."
            sleep 3
            continue
        else
            FINAL_STATUS="failed"
            break
        fi
    fi
done

# ══════════════════════════════════════════════════════════════
# FINAL RESULT
# ══════════════════════════════════════════════════════════════

if [ "$FINAL_STATUS" == "approved" ]; then
    echo "$FINAL_RESULT"
    exit 0
fi

if [ "$FINAL_STATUS" == "exhausted" ]; then
    echo ""
    echo "════════════════════════════════════════════════════════"
    echo "🚫 3 ATTEMPTS KHATAM — Sab REJECT"
    echo "   🕐 $(date '+%Y-%m-%d %H:%M:%S IST')"
    echo "════════════════════════════════════════════════════════"
    echo '{"status": "exhausted", "error": "3 attempts completed, all rejected"}'
    exit 0
fi

if [ "$FINAL_STATUS" == "failed" ]; then
    echo '{"status": "failed", "error": "All attempts failed"}'
    exit 1
fi