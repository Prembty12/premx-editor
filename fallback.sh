#!/bin/bash
# ==============================================================================
# 🤖 OPENROUTER INTELLIGENT VIDEO AGENT — PRODUCTION READY (STRICT HYBRID v3)
# ==============================================================================
# Upgrades included:
# • Key pool rotation & PID handling from v2
# • Advanced Balanced-brace + Reasoning JSON Extraction Engine
# • Strict "is_invalid_title" filter (Blocks: safety errors, prompt text, single words)
# • High-engagement Curiosity Hook Prompt Directives with generic word bans
# ==============================================================================

set -o pipefail

# ─── Config ────────────────────────────────────────────────────────────────────
GRID_PATH="${GRID_PATH:-temp_frames/merged_60_grid_screenshot.jpg}"
SOURCE_DURATION="${SOURCE_DURATION:-60}"
INSIGHTS_SUMMARY="${INSIGHTS_SUMMARY:-}"
STYLE_PROMPT="${STYLE_PROMPT:-}"

PRIMARY_MODEL="${OPENROUTER_MODEL:-nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free}"
FALLBACK_MODEL_1="${OPENROUTER_FALLBACK_1:-google/gemma-4-26b-a4b-it:free}"
FALLBACK_MODEL_2="${OPENROUTER_FALLBACK_2:-openrouter/free}"
MODEL_CHAIN=("$PRIMARY_MODEL" "$FALLBACK_MODEL_1" "$FALLBACK_MODEL_2")

DEBUG="${DEBUG:-1}"
MAX_RETRIES=${#MODEL_CHAIN[@]}

# ─── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'

# ─── Helpers ───────────────────────────────────────────────────────────────────
log() { [ "$DEBUG" = "1" ] && echo -e "${BLUE}[$(date +%H:%M:%S)]${NC} $*" >&2; }
ok() { echo -e "${GREEN}✅ $*${NC}" >&2; }
warn() { echo -e "${YELLOW}⚠️ $*${NC}" >&2; }
err() { echo -e "${RED}❌ $*${NC}" >&2; }
info() { echo -e "${CYAN}ℹ️ $*${NC}" >&2; }

# ─── API Key Pool ──────────────────────────────────────────────────────────────
declare -a KEYS=()
[ -n "$OPENROUTER_API_KEY" ] && KEYS+=("$OPENROUTER_API_KEY")
[ -n "$OPENROUTER_API_KEY_2" ] && KEYS+=("$OPENROUTER_API_KEY_2")
[ -n "$OPENROUTER_API_KEY_3" ] && KEYS+=("$OPENROUTER_API_KEY_3")
[ -n "$OPENROUTER_API_KEY_4" ] && KEYS+=("$OPENROUTER_API_KEY_4")
[ -n "$OPENROUTER_API_KEY_5" ] && KEYS+=("$OPENROUTER_API_KEY_5")

declare -a FAILED_KEY_IDXS=()

get_next_key() {
    local candidates=()
    for i in "${!KEYS[@]}"; do
        local already_failed=0
        for f in "${FAILED_KEY_IDXS[@]}"; do
            [ "$f" = "$i" ] && already_failed=1 && break
        done
        [ "$already_failed" = "0" ] && candidates+=("$i")
    done

    if [ ${#candidates[@]} -eq 0 ]; then
        candidates=("${!KEYS[@]}")
    fi

    local pick=${candidates[$((RANDOM % ${#candidates[@]}))]}
    echo "$pick"
}

# ─── Pre-flight Checks ─────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════════════"
echo "🤖 OPENROUTER INTELLIGENT VIDEO AGENT"
echo "════════════════════════════════════════════════════════════════"
echo ""

if [ ${#KEYS[@]} -eq 0 ]; then
    err "No OpenRouter API keys found"
    echo '{"status": "failed", "error": "No API keys"}'
    exit 1
fi

if [ ! -f "$GRID_PATH" ]; then
    err "Grid image not found: $GRID_PATH"
    echo "{\"status\": \"failed\", \"error\": \"Grid not found\"}"
    exit 1
fi

ok "Grid image found: $GRID_PATH"
ok "API keys loaded: ${#KEYS[@]}"
info "Model chain: ${MODEL_CHAIN[*]}"
echo ""

# ─── Prompt Directives ─────────────────────────────────────────────────────────
PROMPT_TEXT="Analyze the provided 9:16 gaming screenshot grid. Total video source duration is ${SOURCE_DURATION} seconds.
Insights Context: ${INSIGHTS_SUMMARY}
Style Directive: ${STYLE_PROMPT}

Your primary job as an expert video editor is to find the most thrilling, high-action segment, skipping dull introductions.
Return a JSON object with EXACTLY three keys:
1. 'title' (string: ONLY THE SINGLE VIRAL TITLE under 6 words based on visuals with 1-3 emojis creating curiosity and engagement strictly NO generic words like Epic Insane Crazy Best or Gameplay)
2. 'start_time' (string format HH:MM:SS indicating exact peak action start time based on grid timestamps)
3. 'clip_duration' (integer: length between 12 and 45 seconds meeting monetization rules)
Return ONLY valid JSON format, no markdown wrapping."

# ─── Main Loop ─────────────────────────────────────────────────────────────────
RAW_RESPONSE=""
SUCCESS_MODEL=""
SUCCESS_ROUTED=""

mkdir -p temp_frames

for ((attempt=1; attempt<=MAX_RETRIES; attempt++)); do
    KEY_IDX=$(get_next_key)
    CURRENT_KEY="${KEYS[$KEY_IDX]}"
    KEY_DISPLAY="${CURRENT_KEY:0:10}...${CURRENT_KEY: -4}"
    CURRENT_MODEL="${MODEL_CHAIN[$((attempt-1))]}"

    echo ""
    echo "────────────────────────────────────────────────────────"
    echo "🤖 ATTEMPT $attempt / $MAX_RETRIES"
    echo "────────────────────────────────────────────────────────"
    info "Model: $CURRENT_MODEL"
    info "Key: $KEY_DISPLAY"

    PAYLOAD_FILE="temp_frames/or_payload_${attempt}.json"

    GRID_PATH="$GRID_PATH" CURRENT_MODEL="$CURRENT_MODEL" PROMPT_TEXT="$PROMPT_TEXT" PAYLOAD_FILE="$PAYLOAD_FILE" \
    python3 -c "
import os, json, base64

grid_path = os.environ['GRID_PATH']
model = os.environ['CURRENT_MODEL']
prompt = os.environ['PROMPT_TEXT']
out_file = os.environ['PAYLOAD_FILE']

with open(grid_path, 'rb') as f:
    b64 = base64.b64encode(f.read()).decode()

payload = {
    'model': model,
    'messages': [{
        'role': 'user',
        'content': [
            {'type': 'text', 'text': prompt},
            {'type': 'image_url', 'image_url': {'url': f'data:image/jpeg;base64,{b64}'}}
        ]
    }],
    'max_tokens': 1024,
    'temperature': 0.3,
    'provider': {
        'ignore': ['nvidia/nemotron-3.5-content-safety:free']
    }
}

STRUCTURED_OUTPUT_MODELS = ('openai/', 'google/gemini', 'anthropic/')
if model.startswith(STRUCTURED_OUTPUT_MODELS):
    payload['response_format'] = {'type': 'json_object'}

with open(out_file, 'w') as f:
    json.dump(payload, f)

print(f' 📤 Payload created: {os.path.getsize(out_file)} bytes', flush=True)
" || { err "Payload build failed"; continue; }

    # ─── API Call ──────────────────────────────────────────────────────────────
    info "Sending request to OpenRouter..."
    RESP_FILE="/tmp/or_resp_$$_${attempt}.json"

    HTTP_CODE=$(curl -s -o "$RESP_FILE" -w "%{http_code}" \
        --connect-timeout 20 -m 180 \
        -X POST "https://openrouter.ai/api/v1/chat/completions" \
        -H "Authorization: Bearer $CURRENT_KEY" \
        -H "Content-Type: application/json" \
        -d @"$PAYLOAD_FILE")

    RESP=$(cat "$RESP_FILE" 2>/dev/null)
    rm -f "$RESP_FILE" "$PAYLOAD_FILE"

    log "HTTP Status: $HTTP_CODE"

    # ─── Surface API-level errors early ───────────────────────────────────────
    if [ "$HTTP_CODE" != "200" ]; then
        ERR_MSG=$(echo "$RESP" | python3 -c "
import sys, json
try:
    r = json.load(sys.stdin)
    print(r.get('error', {}).get('message', 'unknown error'))
except Exception:
    print('unparseable error body')
" 2>/dev/null)
        warn "HTTP $HTTP_CODE from OpenRouter: $ERR_MSG"

        if [ "$HTTP_CODE" = "401" ] || [ "$HTTP_CODE" = "429" ]; then
            FAILED_KEY_IDXS+=("$KEY_IDX")
        fi
        sleep $((attempt * 3))
        continue
    fi

    # ─── Extract Content ───────────────────────────────────────────────────────
    CONTENT=$(echo "$RESP" | python3 -c "
import sys, json
try:
    r = json.load(sys.stdin)
    c = r.get('choices', [])
    if c:
        m = c[0].get('message', {})
        res = m.get('content') or m.get('reasoning') or ''
        print(res.strip())
except Exception:
    pass
" 2>/dev/null)

    ROUTED=$(echo "$RESP" | python3 -c "
import sys, json
try:
    print(json.load(sys.stdin).get('model',''))
except Exception:
    pass
" 2>/dev/null)

    if [ -n "$CONTENT" ] && [ "$CONTENT" != "None" ]; then
        echo "--------------------------------------------------" >&2
        echo "🔍 [AI RAW RESPONSE / CHATBOARD OUTPUT]:" >&2
        echo "$CONTENT" >&2
        echo "--------------------------------------------------" >&2

        RAW_RESPONSE="$CONTENT"
        SUCCESS_MODEL="$CURRENT_MODEL"
        SUCCESS_ROUTED="$ROUTED"
        ok "Model responded successfully"
        break
    else
        warn "Empty response body, retrying after backoff..."
        sleep $((attempt * 3))
    fi
done

# ─── Fail Check ────────────────────────────────────────────────────────────────
if [ -z "$RAW_RESPONSE" ]; then
    err "All attempts failed"
    echo '{"status": "failed", "error": "All attempts failed"}'
    exit 1
fi

# ─── Save Response ─────────────────────────────────────────────────────────────
RESP_FILE="temp_frames/or_response.txt"
printf "%s" "$RAW_RESPONSE" > "$RESP_FILE"

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "🧹 PARSING PHASE"
echo "════════════════════════════════════════════════════════════════"

REQUESTED_MODEL="$SUCCESS_MODEL" ROUTED_MODEL="$SUCCESS_ROUTED" RESPONSE_FILE="$RESP_FILE" DEBUG="$DEBUG" \
python3 -c '
import os, json, re, sys

def dbg(m):
    if os.environ.get("DEBUG")=="1":
        print(m, file=sys.stderr)

resp_file = os.environ["RESPONSE_FILE"]
req_m = os.environ.get("REQUESTED_MODEL", "")
rout_m = os.environ.get("ROUTED_MODEL", "")

with open(resp_file, "r", encoding="utf-8") as f:
    raw = f.read()

if os.path.exists(resp_file):
    os.remove(resp_file)

dbg(f"📄 Raw length: {len(raw)}")

def is_invalid_title(t):
    if not t: return True
    t_lower = str(t).lower().strip()
    bad_phrases = [
        "analyze", "thinking", "thought", "reasoning", "step", "here is", 
        "json", "output", "note", "need answer", "exact keys", "screenshot", 
        "video editor", "viral title", "format", "grid frames", "the grid", 
        "inspect grid", "timestamps", "prompt", "user safety", "safety safe", 
        "content-safety", "safety"
    ]
    if any(bp in t_lower for bp in bad_phrases):
        return True
    if len(t_lower.split()) < 2:
        return True
    return False

title = None
start_time = None
duration = 20

# Strategy 1: Direct JSON parse
cleaned = re.sub(r"```json\s*|\s*```", "", raw, flags=re.I).strip()
try:
    data = json.loads(cleaned)
    t_cand = data.get("title")
    if not is_invalid_title(t_cand):
        title = t_cand
        start_time = data.get("start_time")
        duration = data.get("clip_duration", data.get("duration", 20))
    dbg("✅ Strategy 1: Direct parse succeeded")
except Exception:
    pass

# Strategy 2: Balanced-brace scan (handles embedded JSON)
if not title:
    start_idxs = [i for i, ch in enumerate(raw) if ch == "{"]
    for start in start_idxs:
        depth = 0
        for end in range(start, len(raw)):
            if raw[end] == "{":
                depth += 1
            elif raw[end] == "}":
                depth -= 1
            if depth == 0:
                candidate = raw[start:end+1]
                if "\"title\"" in candidate:
                    try:
                        data = json.loads(candidate)
                        t_cand = data.get("title")
                        if not is_invalid_title(t_cand):
                            title = t_cand
                            start_time = data.get("start_time")
                            duration = data.get("clip_duration", data.get("duration", 20))
                            dbg("✅ Strategy 2: Balanced-brace scan succeeded")
                            break
                    except Exception:
                        pass
                break
        if title: break

# Strategy 3: Rescue Title from AI Reasoning Quotes
if not title:
    quoted_candidates = re.findall(r'["\']([A-Z][^"\'\n]{3,50}?[⚔️🔥💥🎯⚡🏹💥🐾🐆💣⚔️].*?)["\']', raw)
    for cand in quoted_candidates:
        if not is_invalid_title(cand):
            title = cand
            dbg("✅ Strategy 3: Reasoning quote rescue succeeded")
            break

# Strategy 4: Fallback Line Search
if not title:
    lines = [line.strip() for line in raw.split("\n") if line.strip()]
    for line in reversed(lines):
        clean_line = re.sub(r"^[\*\-\d\.\s#]+", "", line).strip()
        if not is_invalid_title(clean_line) and len(clean_line) > 5:
            title = clean_line[:60]
            dbg("✅ Strategy 4: Line fallback succeeded")
            break

if not title or is_invalid_title(title):
    dbg("❌ All parsing strategies failed to yield a valid title")
    print(json.dumps({"status": "failed", "error": "Invalid title generated"}))
    sys.exit(1)

# Clean title for FFmpeg safety
title = str(title).split("\n")[0].strip()
title = re.sub(r"[,\x27\"\x22\-:\n\r\t]+", " ", title)
title = re.sub(r"\s+", " ", title).strip()

if not start_time:
    time_match = re.search(r"\b\d{2}:\d{2}:\d{2}\b", raw)
    if time_match:
        start_time = time_match.group(0)
    else:
        time_short = re.search(r"\b(\d{2}:\d{2})\b", raw)
        start_time = f"00:{time_short.group(1)}" if time_short else "00:00:10"

try:
    dur_int = max(12, min(45, int(duration)))
except Exception:
    dur_int = 20

print(json.dumps({
    "status": "success",
    "requested_model": req_m,
    "routed_model": rout_m,
    "title": str(title),
    "start_time": str(start_time),
    "duration": dur_int
}, ensure_ascii=False))
'

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "✅ PIPELINE COMPLETE"
echo "════════════════════════════════════════════════════════════════"
