#!/bin/bash
# ==========================================
# 🤖 TRUE AI AGENT PIPELINE
# Gemini → OpenRouter → Shift → Retry (max 3 attempts)
# ==========================================

export TZ='Asia/Kolkata'
if ! date '+%Z' 2>/dev/null | grep -qi 'IST'; then
    export TZ='IST-5:30'
fi

BASE="."
API="https://graph.facebook.com/v24.0"
LINKS_DIR="game_links_editor"
POSTED_DIR="posted_links_editor"
SHIFT_DIR="game_links_shift"
FRAMES_DIR="temp_frames"

GAME_LINKS_DIR="$BASE/$LINKS_DIR"
POSTED_LINKS_DIR="$BASE/$POSTED_DIR"
GAME_SHIFT_DIR="$BASE/$SHIFT_DIR"
mkdir -p "$GAME_LINKS_DIR" "$POSTED_LINKS_DIR" "$GAME_SHIFT_DIR" "$FRAMES_DIR" "logs"

LOG_FILE="logs/pipeline_debug.log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "===================================================="
echo "🚀 Pipeline Started at: $(date '+%Y-%m-%d %H:%M:%S IST')"
echo "===================================================="

GEMINI_KEYS=("$GEMINI_API_KEY_1" "$GEMINI_API_KEY_2" "$GEMINI_API_KEY_3")

get_random_gemini_key() {
    local valid_keys=()
    for k in "${GEMINI_KEYS[@]}"; do
        [ -n "$k" ] && valid_keys+=("$k")
    done
    if [ ${#valid_keys[@]} -eq 0 ]; then
        echo "$GEMINI_API_KEY_1"
    else
        local idx=$((RANDOM % ${#valid_keys[@]}))
        echo "${valid_keys[$idx]}"
    fi
}

DEFAULT_POST_MODE="${POST_MODE:-1}"
MIN_CLIP_DURATION=12

# ═════════════════════════════════════════════════════════════
# 0. Cookie Health Check
# ═════════════════════════════════════════════════════════════
echo "🔍 [STEP 0] Checking Facebook Cookie Session Health..."
python3 cookie_checker.py
if [ $? -ne 0 ]; then
    echo "❌ [ERROR] Pipeline halted due to invalid cookies."
    exit 1
fi

# ═════════════════════════════════════════════════════════════
# 1. Insights Update
# ═════════════════════════════════════════════════════════════
echo "📈 [STEP 1] Pulling analytics..."
python3 insights_tracker.py

# ═════════════════════════════════════════════════════════════
# 2. Check 3 Hours Gap
# ═════════════════════════════════════════════════════════════
if [ "$DEFAULT_POST_MODE" != "2" ] && [ -n "$PAGE_ACCESS_TOKEN" ] && [ -n "$PAGE_ID" ]; then
    echo "🔍 [STEP 2] Checking last post time..."
    
    LAST_POST_CHECK=$(python3 -c "
import requests
from datetime import datetime, timezone
page_id = '$PAGE_ID'
token = '$PAGE_ACCESS_TOKEN'
url = f'https://graph.facebook.com/v24.0/{page_id}/feed?access_token={token}&limit=1'
try:
    res = requests.get(url).json()
    if 'data' in res and len(res['data']) > 0:
        created_time_str = res['data'][0].get('created_time')
        last_time = datetime.strptime(created_time_str, '%Y-%m-%dT%H:%M:%S%z')
        now = datetime.now(timezone.utc)
        diff_hours = (now - last_time).total_seconds() / 3600
        print(f'LAST_POST_HOURS:{diff_hours}')
    else:
        print('LAST_POST_HOURS:999')
except Exception as e:
    print(f'LAST_POST_HOURS:999')
")

    HOURS_AGO=$(echo "$LAST_POST_CHECK" | grep "LAST_POST_HOURS" | cut -d':' -f2)
    echo "📊 Hours since last post: $HOURS_AGO"
    
    if [ -n "$HOURS_AGO" ]; then
        IS_LESS_THAN_3=$(python3 -c "print('yes' if float('$HOURS_AGO' or '0') < 3.0 else 'no')")
        if [ "$IS_LESS_THAN_3" == "yes" ]; then
            echo "⏳ 3 ghante gap poora nahi hua! Sirf $HOURS_AGO ghante."
            exit 0
        else
            echo "✅ 3 ghante gap poora."
        fi
    fi
fi

# ═════════════════════════════════════════════════════════════
# 3. AI Agent Brain
# ═════════════════════════════════════════════════════════════
echo "🤖 [STEP 3] Consulting AI Agent Brain..."
AGENT_OUTPUT=$(python3 ai_agent.py)
echo "🧠 AI Agent Raw Output: $AGENT_OUTPUT"

TARGET_FILE=$(echo "$AGENT_OUTPUT" | python3 -c "import sys, json; print(json.load(sys.stdin).get('target_file', ''))" 2>/dev/null)
SELECTED_GAME_NAME=$(echo "$AGENT_OUTPUT" | python3 -c "import sys, json; print(json.load(sys.stdin).get('game_name', ''))" 2>/dev/null)
SELECTED_STYLE=$(echo "$AGENT_OUTPUT" | python3 -c "import sys, json; print(json.load(sys.stdin).get('chosen_style', 'curiosity'))" 2>/dev/null)

if [ -z "$TARGET_FILE" ] || [ "$TARGET_FILE" == "None" ] || [ ! -f "$TARGET_FILE" ]; then
    echo "⚠️ [WARNING] No valid game file found. Target: $TARGET_FILE"
    exit 0
fi

GAME_POSTED_LOG="$POSTED_LINKS_DIR/${SELECTED_GAME_NAME}_posted_links_editor.txt"
GAME_SHIFT_LOG="$GAME_SHIFT_DIR/${SELECTED_GAME_NAME}_shift_links.txt"
echo "🎮 Selected Game: $SELECTED_GAME_NAME | File: $TARGET_FILE | Style: $SELECTED_STYLE"

# ═════════════════════════════════════════════════════════════
# 4-6. Setup: Link, Duration, Frames, Grid (ONLY ONCE)
# ═════════════════════════════════════════════════════════════
echo "🔗 [STEP 4] Parsing link from target file..."
PARSED_DATA=$(TARGET_FILE="$TARGET_FILE" python3 -c "
import sys, json, os, random
target = os.environ.get('TARGET_FILE', '')
if not os.path.exists(target):
    print('{}')
    sys.exit(0)
with open(target, 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()
lines = [l.strip() for l in content.split('\n') if l.strip()]
valid_pairs = []
for line in lines:
    if 'http://' in line or 'https://' in line:
        parts = line.split()
        url = ''
        for p in parts:
            if p.startswith('http://') or p.startswith('https://'):
                url = p
                break
        if url:
            title = line.replace(url, '').replace('| Link:', '').replace('|', '').strip()
            if not title:
                title = os.path.basename(url).split('?')[0]
            valid_pairs.append({'title': title, 'url': url, 'raw': line})
if not valid_pairs:
    print('{}')
    sys.exit(0)
chosen = random.choice(valid_pairs)
print(json.dumps({'title': chosen['title'], 'url': chosen['url'], 'raw': chosen['raw']}))
")

SELECTED_URL=$(echo "$PARSED_DATA" | python3 -c "import sys, json; print(json.load(sys.stdin).get('url', ''))" 2>/dev/null)
SELECTED_LINE=$(echo "$PARSED_DATA" | python3 -c "import sys, json; print(json.load(sys.stdin).get('raw', ''))" 2>/dev/null)

if [ -z "$SELECTED_URL" ]; then
    echo "⚠️ [WARNING] No valid link found."
    exit 0
fi

echo "🔗 Validated Link: $SELECTED_URL"

echo "✂️ [STEP 5] Checking source video duration..."
SOURCE_DURATION=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$SELECTED_URL" 2>/dev/null)
SOURCE_DURATION=${SOURCE_DURATION%.*}
if [ -z "$SOURCE_DURATION" ] || [ "$SOURCE_DURATION" -le 0 ] 2>/dev/null; then
    SOURCE_DURATION=60
fi
echo "⏱️ Source Duration: ${SOURCE_DURATION}s"

rm -f "$FRAMES_DIR"/*.jpg
echo "📸 [STEP 6] Extracting 60 frames..."

NUM_FRAMES=60
interval=$((SOURCE_DURATION / NUM_FRAMES))
[ "$interval" -lt 1 ] && interval=1

timestamps=()
for ((i=1; i<=NUM_FRAMES; i++)); do
    t=$(( (i - 1) * interval ))
    [ "$t" -ge "$SOURCE_DURATION" ] && t=$((SOURCE_DURATION - 1))
    [ "$t" -lt 0 ] && t=0
    min=$((t / 60))
    sec=$((t % 60))
    timestamps+=($(printf "00:%02d:%02d" $((10#$min)) $((10#$sec)) ))
done

for i in "${!timestamps[@]}"; do
    idx=$((i+1))
    ts="${timestamps[$i]}"
    frame_path="$FRAMES_DIR/frame_$idx.jpg"
    ffmpeg -y -ss "$ts" -i "$SELECTED_URL" -vframes 1 -q:v 2 "$frame_path" -loglevel error
    if [ ! -f "$frame_path" ] || [ ! -s "$frame_path" ]; then
        ffmpeg -y -ss "00:00:01" -i "$SELECTED_URL" -vframes 1 -q:v 2 "$frame_path" -loglevel error
    fi
done

GRID_PATH="$FRAMES_DIR/merged_60_grid_screenshot.jpg"
echo "🧩 Merging frames into 6x10 grid..."

TIMESTAMPS_STR="${timestamps[*]}" python3 - << 'EOF'
import os, subprocess
frames_dir = 'temp_frames'
grid_path = os.path.join(frames_dir, 'merged_60_grid_screenshot.jpg')
try:
    from PIL import Image, ImageDraw
except ImportError:
    subprocess.run(["pip", "install", "Pillow"], check=True)
    from PIL import Image, ImageDraw
timestamps_env = os.environ.get('TIMESTAMPS_STR', '')
timestamps = timestamps_env.split()
for i in range(1, 61):
    frame_path = os.path.join(frames_dir, f'frame_{i}.jpg')
    ts = timestamps[i-1] if (i-1) < len(timestamps) else "00:00:00"
    if os.path.exists(frame_path) and os.path.getsize(frame_path) > 0:
        try:
            im = Image.open(frame_path).resize((432, 384))
            draw = ImageDraw.Draw(im)
            draw.rectangle([10, 10, 120, 40], fill=(0, 0, 0))
            draw.text((13, 15), ts, fill=(255, 255, 255))
            im.save(frame_path, 'JPEG', quality=80)
        except: pass
images = []
for i in range(1, 61):
    img_path = os.path.join(frames_dir, f'frame_{i}.jpg')
    if os.path.exists(img_path) and os.path.getsize(img_path) > 0:
        try: im = Image.open(img_path)
        except: im = Image.new('RGB', (432, 384), (0, 0, 0))
    else:
        im = Image.new('RGB', (432, 384), (0, 0, 0))
    images.append(im)
grid_img = Image.new('RGB', (2592, 3840))
for idx, im in enumerate(images):
    col = idx % 6
    row = idx // 6
    grid_img.paste(im, (col * 432, row * 384))
grid_img.save(grid_path, 'JPEG', quality=85)
print("✅ Grid created.")
EOF

# ═════════════════════════════════════════════════════════════
# 🔄 MAIN LOOP — MAX 3 ATTEMPTS
# Har REJECT pe link shift → naya attempt
# ═════════════════════════════════════════════════════════════
MAX_ATTEMPTS=3
ATTEMPT_NUM=0
FINAL_STATUS=""
FINAL_JSON=""
LAST_REASON=""

while [ $ATTEMPT_NUM -lt $MAX_ATTEMPTS ]; do
    ATTEMPT_NUM=$((ATTEMPT_NUM + 1))
    
    echo ""
    echo "════════════════════════════════════════════════════"
    echo "🔁 ATTEMPT $ATTEMPT_NUM / $MAX_ATTEMPTS"
    echo "   🕐 $(date '+%Y-%m-%d %H:%M:%S IST')"
    echo "════════════════════════════════════════════════════"
    
    # ─────────────────────────────────────────
    # Har attempt mein NAYA link pick karo
    # ─────────────────────────────────────────
    if [ ! -f "$TARGET_FILE" ]; then
        echo "❌ Target file nahi mili: $TARGET_FILE"
        FINAL_STATUS="failed"
        break
    fi
    
    PARSED_DATA=$(TARGET_FILE="$TARGET_FILE" python3 -c "
import sys, json, os, random
target = os.environ.get('TARGET_FILE', '')
if not os.path.exists(target):
    print('{}')
    sys.exit(0)
with open(target, 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()
lines = [l.strip() for l in content.split('\n') if l.strip()]
valid_pairs = []
for line in lines:
    if 'http://' in line or 'https://' in line:
        parts = line.split()
        url = ''
        for p in parts:
            if p.startswith('http://') or p.startswith('https://'):
                url = p
                break
        if url:
            title = line.replace(url, '').replace('| Link:', '').replace('|', '').strip()
            if not title:
                title = os.path.basename(url).split('?')[0]
            valid_pairs.append({'title': title, 'url': url, 'raw': line})
if not valid_pairs:
    print('{}')
    sys.exit(0)
chosen = random.choice(valid_pairs)
print(json.dumps({'title': chosen['title'], 'url': chosen['url'], 'raw': chosen['raw']}))
")
    
    SELECTED_URL=$(echo "$PARSED_DATA" | python3 -c "import sys, json; print(json.load(sys.stdin).get('url', ''))" 2>/dev/null)
    SELECTED_LINE=$(echo "$PARSED_DATA" | python3 -c "import sys, json; print(json.load(sys.stdin).get('raw', ''))" 2>/dev/null)
    
    if [ -z "$SELECTED_URL" ]; then
        echo "❌ Editor mein koi link nahi bacha"
        FINAL_STATUS="exhausted"
        break
    fi
    
    echo "🔗 Link: $SELECTED_URL"
    echo ""
    
    # ─────────────────────────────────────────
    # STEP 7: Gemini Try
    # ─────────────────────────────────────────
    echo "🤖 [STEP 7] Asking Gemini..."
    
    INSIGHTS_SUMMARY=$(python3 -c "
import os, json
mf = 'logs/agent_memory.json'
if os.path.exists(mf):
    try:
        with open(mf) as f:
            d = json.load(f)
            print(f'Memory: {d.get(\"game_scores\", {})}')
    except: print('No memory.')
else: print('Fresh run.')
")

    if [ "$SELECTED_STYLE" == "aggressive" ]; then
        STYLE_PROMPT="Create a bold, intense, high-energy aggressive gaming hook title."
    elif [ "$SELECTED_STYLE" == "question" ]; then
        STYLE_PROMPT="Create a curiosity-driven question hook title."
    elif [ "$SELECTED_STYLE" == "emoji_heavy" ]; then
        STYLE_PROMPT="Create a fast-paced viral gaming title with strong emojis."
    else
        STYLE_PROMPT="Create a high-curiosity viral Reels hook title (6-10 words)."
    fi

    GEMINI_JSON_RESULT=""
    MAX_GEMINI_RETRIES=4

    for ((g=1; g<=MAX_GEMINI_RETRIES; g++)); do
        CURRENT_GEMINI_KEY=$(get_random_gemini_key)
        echo "   🤖 Gemini try $g/$MAX_GEMINI_RETRIES"
        
        if [ -f "$GRID_PATH" ]; then
            file_size=$(wc -c < "$GRID_PATH")
            upload_res=$(curl -s -D - -X POST "https://generativelanguage.googleapis.com/upload/v1beta/files?key=$CURRENT_GEMINI_KEY" \
              -H "X-Goog-Upload-Protocol: resumable" \
              -H "X-Goog-Upload-Command: start" \
              -H "X-Goog-Upload-Header-Content-Length: $file_size" \
              -H "X-Goog-Upload-Header-Content-Type: image/jpeg" \
              -H "Content-Type: application/json" \
              -d '{"file": {"display_name": "GridScreenshot"}}')

            gemini_upload_url=$(echo "$upload_res" | grep -i "x-goog-upload-url:" | tr -d '\r' | cut -d' ' -f2)

            if [ -n "$gemini_upload_url" ]; then
                finalize_res=$(curl -s -X POST "$gemini_upload_url" \
                  -H "X-Goog-Upload-Protocol: resumable" \
                  -H "X-Goog-Upload-Command: upload, finalize" \
                  -H "X-Goog-Upload-Offset: 0" \
                  -H "Content-Length: $file_size" \
                  --data-binary "@$GRID_PATH")

                file_uri=$(echo "$finalize_res" | jq -r '.file.uri // empty')
                
                if [ -n "$file_uri" ]; then
                    file_name_g_api=$(echo "$file_uri" | awk -F'/' '{print $NF}')
                    sc=0
                    while [ $sc -lt 10 ]; do
                        state=$(curl -s "https://generativelanguage.googleapis.com/v1beta/files/$file_name_g_api?key=$CURRENT_GEMINI_KEY" | jq -r '.state // empty')
                        [ "$state" = "ACTIVE" ] && break
                        sleep 1
                        sc=$((sc + 1))
                    done

                    if [ "$state" = "ACTIVE" ]; then
                        prompt_text="Analyze this 9:16 gaming grid. Video duration: ${SOURCE_DURATION}s.
Style: $STYLE_PROMPT

YOUR TASK: Decide APPROVE or REJECT.

REJECT IF:
- ONLY menus, login screens, or loading screens
- No actual gameplay visible in any frame
- All frames identical (frozen)
- Black frames / crash / error dominate
- No exciting moment

APPROVE IF:
- Any real gameplay visible
- Any action or engaging moment exists

STRICT JSON OUTPUT:

If REJECT: {\"status\": \"REJECT\", \"reason\": \"<1-line>\"}
If APPROVE: {\"status\": \"APPROVE\", \"title\": \"<viral title 6-10 words with 1-3 emojis>\", \"start_time\": \"<HH:MM:SS>\", \"clip_duration\": <integer 12-45>, \"reason\": \"<1-line>\"}

ONLY JSON, no markdown."

                        payload=$(jq -n \
                          --arg uri "$file_uri" \
                          --arg mime "image/jpeg" \
                          --arg ptext "$prompt_text" \
                          '{contents: [{parts: [{file_data: {file_uri: $uri, mime_type: $mime}}, {text: $ptext}]}]}')

                        gemini_resp=$(curl -s -X POST -H "Content-Type: application/json" \
                          "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=$CURRENT_GEMINI_KEY" \
                          -d "$payload")

                        GEMINI_JSON_RESULT=$(echo "$gemini_resp" | jq -r '.candidates[0].content.parts[0].text // empty')
                        echo "   📥 Gemini: ${GEMINI_JSON_RESULT:0:150}..."
                    fi
                fi
            fi
        fi

        if [ -n "$GEMINI_JSON_RESULT" ] && [ "$GEMINI_JSON_RESULT" != "null" ]; then
            break
        fi
        sleep 2
    done

    # ─────────────────────────────────────────
    # Parse Gemini
    # ─────────────────────────────────────────
    PARSED_JSON_DATA=$(GEMINI_RAW="$GEMINI_JSON_RESULT" python3 - << 'EOF'
import json, re, sys, os
raw = os.environ.get('GEMINI_RAW', '')
cleaned = re.sub(r'```json', '', raw, flags=re.IGNORECASE)
cleaned = re.sub(r'```', '', cleaned).strip()
cleaned = re.sub(r'<think>.*?</think>', '', cleaned, flags=re.DOTALL).strip()
data = {}
try:
    m = re.search(r'\{.*\}', cleaned, re.DOTALL)
    data = json.loads(m.group(0)) if m else json.loads(cleaned)
except:
    print(json.dumps({'status': 'failed', 'error': 'parse_error'}))
    sys.exit(0)
sf = str(data.get('status', '')).strip().upper()
reason = str(data.get('reason', '')).strip()
if sf == 'REJECT':
    print(json.dumps({'status': 'reject', 'reason': reason or 'AI rejected'}))
elif sf == 'APPROVE' and data.get('title') and data.get('start_time') and data.get('clip_duration'):
    try:
        d = int(data['clip_duration'])
        if d < 12: d = 12
        if d > 45: d = 45
        print(json.dumps({'status': 'success', 'title': data['title'], 'start_time': data['start_time'], 'duration': d, 'reason': reason}))
    except:
        print(json.dumps({'status': 'failed', 'error': 'invalid_duration'}))
else:
    print(json.dumps({'status': 'failed', 'error': 'missing_keys'}))
EOF
)

    PARSED_STATUS=$(echo "$PARSED_JSON_DATA" | python3 -c "import sys,json;print(json.load(sys.stdin).get('status','failed'))" 2>/dev/null)
    PARSED_REASON=$(echo "$PARSED_JSON_DATA" | python3 -c "import sys,json;print(json.load(sys.stdin).get('reason',''))" 2>/dev/null)

    # ─────────────────────────────────────────
    # ✅ Gemini APPROVE → Post (script band)
    # ─────────────────────────────────────────
    if [ "$PARSED_STATUS" == "success" ]; then
        echo "   ✅ GEMINI APPROVED"
        FINAL_STATUS="approved"
        FINAL_JSON="$PARSED_JSON_DATA"
        break
    fi

    # ─────────────────────────────────────────
    # 🚫 Gemini REJECT → Link SHIFT → OpenRouter try
    # ─────────────────────────────────────────
    if [ "$PARSED_STATUS" == "reject" ]; then
        LAST_REASON="$PARSED_REASON"
        echo "   🚫 GEMINI REJECTED: $PARSED_REASON"
        echo "   📦 Link ko SHIFT kar raha hoon..."
        
        echo "$SELECTED_LINE | REJECT (Gemini): $PARSED_REASON" >> "$GAME_SHIFT_LOG"
        echo "   ✅ Shift file: $GAME_SHIFT_LOG"
        
        python3 -c "
import os
tf = '$TARGET_FILE'
sl = '''$SELECTED_LINE'''
if os.path.exists(tf):
    with open(tf, 'r', encoding='utf-8', errors='ignore') as f:
        c = f.read()
    cl = c.replace(sl, '').strip()
    with open(tf, 'w', encoding='utf-8') as f:
        f.write(cl + '\n\n')
    print(f'   🗑️  Editor removed: {tf}')
"
        echo "   🔄 Trying OpenRouter fallback..."
    fi

    # ─────────────────────────────────────────
    # ❌ Gemini FAILED (parse/API error) → OpenRouter try (shift NAHI)
    # ─────────────────────────────────────────
    if [ "$PARSED_STATUS" == "failed" ]; then
        echo "   ⚠️  Gemini failed. Trying OpenRouter fallback..."
    fi

    # ─────────────────────────────────────────
    # STEP 7B: OpenRouter Fallback (fallback.sh)
    # ─────────────────────────────────────────
    if [ -f "fallback.sh" ]; then
        export GRID_PATH SOURCE_DURATION STYLE_PROMPT SELECTED_URL
        
        FB_RESULT=$(bash fallback.sh 2>/dev/null)
        FB_STATUS=$(echo "$FB_RESULT" | python3 -c "import sys,json;print(json.load(sys.stdin).get('status','failed'))" 2>/dev/null)
        FB_REASON=$(echo "$FB_RESULT" | python3 -c "import sys,json;print(json.load(sys.stdin).get('reason',''))" 2>/dev/null)
        
        echo "   🧠 OpenRouter status: $FB_STATUS"
        
        # ✅ OpenRouter APPROVE → Post (script band)
        if [ "$FB_STATUS" == "success" ]; then
            echo "   ✅ OPENROUTER APPROVED"
            FINAL_STATUS="approved"
            FINAL_JSON="$FB_RESULT"
            break
        fi
        
        # 🚫 OpenRouter REJECT → Link SHIFT → next attempt
        if [ "$FB_STATUS" == "reject" ]; then
            LAST_REASON="$FB_REASON"
            echo "   🚫 OPENROUTER REJECTED: $FB_REASON"
            
            # Agar Gemini ne pehle hi shift kar diya tha, to dobara mat karo
            # (yani Gemini REJECT wale case mein link already shift ho chuka hai)
            if [ "$PARSED_STATUS" != "reject" ]; then
                echo "   📦 Link ko SHIFT kar raha hoon..."
                echo "$SELECTED_LINE | REJECT (OpenRouter): $FB_REASON" >> "$GAME_SHIFT_LOG"
                
                python3 -c "
import os
tf = '$TARGET_FILE'
sl = '''$SELECTED_LINE'''
if os.path.exists(tf):
    with open(tf, 'r', encoding='utf-8', errors='ignore') as f:
        c = f.read()
    cl = c.replace(sl, '').strip()
    with open(tf, 'w', encoding='utf-8') as f:
        f.write(cl + '\n\n')
    print(f'   🗑️  Editor removed: {tf}')
"
            else
                echo "   ℹ️  Link pehle hi shift ho chuka hai (Gemini REJECT)"
            fi
            
            if [ $ATTEMPT_NUM -lt $MAX_ATTEMPTS ]; then
                echo "   🔁 REJECT #$ATTEMPT_NUM — Retrying (attempt $((ATTEMPT_NUM+1))/$MAX_ATTEMPTS)..."
                sleep 3
                continue
            else
                echo "   🚫 3 attempts khatam — script band"
                FINAL_STATUS="exhausted"
                break
            fi
        fi
        
        # ❌ OpenRouter FAIL → next attempt
        if [ "$FB_STATUS" == "failed" ]; then
            echo "   ❌ OpenRouter FAILED"
            
            if [ $ATTEMPT_NUM -lt $MAX_ATTEMPTS ]; then
                echo "   🔁 FAILED #$ATTEMPT_NUM — Retrying..."
                sleep 3
                continue
            else
                echo "   ❌ 3 attempts khatam — exit"
                FINAL_STATUS="failed"
                break
            fi
        fi
    else
        echo "   ⚠️  fallback.sh nahi mili"
        
        # Agar fallback nahi hai to Gemini REJECT pe hi shift ho gaya
        if [ "$PARSED_STATUS" == "reject" ]; then
            if [ $ATTEMPT_NUM -lt $MAX_ATTEMPTS ]; then
                echo "   🔁 Retrying (attempt $((ATTEMPT_NUM+1))/$MAX_ATTEMPTS)..."
                sleep 3
                continue
            else
                FINAL_STATUS="exhausted"
                break
            fi
        fi
        
        if [ $ATTEMPT_NUM -lt $MAX_ATTEMPTS ]; then
            echo "   🔁 Retrying..."
            sleep 3
            continue
        else
            FINAL_STATUS="failed"
            break
        fi
    fi
done

# ═════════════════════════════════════════════════════════════
# HANDLE FINAL STATUS
# ═════════════════════════════════════════════════════════════

# 🚫 EXHAUSTED — 3 attempts khatam
if [ "$FINAL_STATUS" == "exhausted" ]; then
    echo ""
    echo "════════════════════════════════════════════════════"
    echo "🚫 3 ATTEMPTS KHATAM — Sab REJECT"
    echo "   💬 Last Reason : $LAST_REASON"
    echo "   🎮 Game        : $SELECTED_GAME_NAME"
    echo "   🕐 Time (IST)  : $(date '+%Y-%m-%d %H:%M:%S IST')"
    echo "════════════════════════════════════════════════════"
    echo "🏁 Pipeline Finished at: $(date '+%Y-%m-%d %H:%M:%S IST')"
    echo "===================================================="
    exit 0
fi

# ❌ FAILED — 3 attempts fail
if [ "$FINAL_STATUS" == "failed" ]; then
    echo ""
    echo "❌ All attempts FAILED (not REJECT) — link stays, retry later"
    echo "🏁 Pipeline Finished at: $(date '+%Y-%m-%d %H:%M:%S IST')"
    echo "===================================================="
    exit 1
fi

# ✅ APPROVED — Continue to clip cutting & posting
AI_TITLE=$(echo "$FINAL_JSON" | python3 -c "import sys,json;print(json.load(sys.stdin).get('title',''))" 2>/dev/null)
FINAL_START_TIME=$(echo "$FINAL_JSON" | python3 -c "import sys,json;print(json.load(sys.stdin).get('start_time',''))" 2>/dev/null)
FINAL_CLIP_DURATION=$(echo "$FINAL_JSON" | python3 -c "import sys,json;print(json.load(sys.stdin).get('duration',15))" 2>/dev/null)
AI_REASON=$(echo "$FINAL_JSON" | python3 -c "import sys,json;print(json.load(sys.stdin).get('reason',''))" 2>/dev/null)

echo ""
echo "✅ FINAL: APPROVED (attempt $ATTEMPT_NUM/$MAX_ATTEMPTS)"
echo "   - Title        : $AI_TITLE"
echo "   - Start Time   : $FINAL_START_TIME"
echo "   - Clip Duration: $FINAL_CLIP_DURATION seconds"
echo "   - Reason       : $AI_REASON"
echo ""

CAPTION="$AI_TITLE

#videogames #gamingcommunity #gaming #${SELECTED_GAME_NAME,,} #gamingreels #reels"

# ═════════════════════════════════════════════════════════════
# 8. Clip Cutting
# ═════════════════════════════════════════════════════════════
FINAL_CLIP_PATH="$FRAMES_DIR/final_cut_clip.mp4"
echo "✂️ [STEP 8] Cutting clip..."
ffmpeg -y -ss "$FINAL_START_TIME" -i "$SELECTED_URL" -t "$FINAL_CLIP_DURATION" -c:v copy -c:a copy "$FINAL_CLIP_PATH" -loglevel error

if [ ! -f "$FINAL_CLIP_PATH" ] || [ ! -s "$FINAL_CLIP_PATH" ]; then
    echo "⚠️ Stream copy failed. Re-encoding..."
    ffmpeg -y -ss "$FINAL_START_TIME" -i "$SELECTED_URL" -t "$FINAL_CLIP_DURATION" -c:v libx264 -preset veryfast -c:a aac "$FINAL_CLIP_PATH" -loglevel error
fi

if [ ! -f "$FINAL_CLIP_PATH" ] || [ ! -s "$FINAL_CLIP_PATH" ]; then
    echo "❌ FFmpeg failed to cut clip!"
    exit 1
fi

echo "✅ Clip saved: $FINAL_CLIP_PATH"

# ═════════════════════════════════════════════════════════════
# 9. Post to Platforms
# ═════════════════════════════════════════════════════════════
POST_MODE="$DEFAULT_POST_MODE"
echo "🚀 [STEP 9] Posting (Mode: $POST_MODE)..."

PUBLISH_ID=""
FB_POST_ID=""

# Instagram Reels
if [ "$POST_MODE" == "1" ] || [ "$POST_MODE" == "2" ]; then
    if [ -n "$PAGE_ACCESS_TOKEN" ] && [ -n "$IG_ID" ]; then
        echo "🚀 Instagram Reels upload..."
        
        TAG_NAME="clip-release-$(date +%s)"
        REPO="${GITHUB_REPOSITORY}"
        TOKEN="${GITHUB_TOKEN:-$GH_PAT}"
        
        RELEASE_RES=$(curl -s -X POST "https://api.github.com/repos/$REPO/releases" \
          -H "Authorization: token $TOKEN" \
          -H "Content-Type: application/json" \
          -d "{\"tag_name\":\"$TAG_NAME\",\"name\":\"Temp Clip\",\"draft\":false,\"prerelease\":true}")
          
        RELEASE_ID=$(echo "$RELEASE_RES" | python3 -c "import sys,json;print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
        
        if [ -n "$RELEASE_ID" ] && [ "$RELEASE_ID" != "None" ]; then
            UPLOAD_URL="https://uploads.github.com/repos/$REPO/releases/$RELEASE_ID/assets?name=final_clip.mp4"
            ASSET_RES=$(curl -s -X POST "$UPLOAD_URL" \
              -H "Authorization: token $TOKEN" \
              -H "Content-Type: video/mp4" \
              --data-binary "@$FINAL_CLIP_PATH")
              
            PUBLIC_VIDEO_URL=$(echo "$ASSET_RES" | python3 -c "import sys,json;print(json.load(sys.stdin).get('browser_download_url',''))" 2>/dev/null)
            
            if [ -n "$PUBLIC_VIDEO_URL" ] && [ "$PUBLIC_VIDEO_URL" != "None" ]; then
                CONTAINER_RES=$(curl -s -X POST "$API/$IG_ID/media" \
                  --data-urlencode "media_type=REELS" \
                  --data-urlencode "video_url=$PUBLIC_VIDEO_URL" \
                  --data-urlencode "caption=$CAPTION" \
                  --data-urlencode "access_token=$PAGE_ACCESS_TOKEN")

                CREATION_ID=$(echo "$CONTAINER_RES" | python3 -c "import sys,json;print(json.load(sys.stdin).get('id',''))" 2>/dev/null)

                if [ -n "$CREATION_ID" ] && [ "$CREATION_ID" != "None" ]; then
                    for i in {1..45}; do
                        sleep 5
                        STATUS_RES=$(curl -s "$API/$CREATION_ID?fields=status_code&access_token=$PAGE_ACCESS_TOKEN")
                        STATUS_CODE=$(echo "$STATUS_RES" | python3 -c "import sys,json;print(json.load(sys.stdin).get('status_code',''))" 2>/dev/null)
                        [ "$STATUS_CODE" == "FINISHED" ] && break
                    done

                    PUBLISH_RES=$(curl -s -X POST "$API/$IG_ID/media_publish" \
                      -d "creation_id=$CREATION_ID" \
                      -d "access_token=$PAGE_ACCESS_TOKEN")
                    
                    PUBLISH_ID=$(echo "$PUBLISH_RES" | python3 -c "import sys,json;print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
                    [ -n "$PUBLISH_ID" ] && [ "$PUBLISH_ID" != "None" ] && echo "🎉 IG Published: $PUBLISH_ID"
                fi
            fi
            
            curl -s -X DELETE "https://api.github.com/repos/$REPO/releases/$RELEASE_ID" -H "Authorization: token $TOKEN" > /dev/null
            curl -s -X DELETE "https://api.github.com/repos/$REPO/git/refs/tags/$TAG_NAME" -H "Authorization: token $TOKEN" > /dev/null
        fi
    fi
fi

# Facebook Page
if [ "$POST_MODE" == "1" ] || [ "$POST_MODE" == "3" ]; then
    if [ -n "$PAGE_ACCESS_TOKEN" ] && [ -n "$PAGE_ID" ]; then
        echo "🚀 Facebook upload..."
        FB_RES=$(curl -s -X POST "$API/$PAGE_ID/videos" \
          --data-urlencode "source=@$FINAL_CLIP_PATH" \
          --data-urlencode "description=$CAPTION" \
          --data-urlencode "access_token=$PAGE_ACCESS_TOKEN")

        FB_POST_ID=$(echo "$FB_RES" | python3 -c "import sys,json;print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
        [ -n "$FB_POST_ID" ] && [ "$FB_POST_ID" != "None" ] && echo "🎉 FB Published: $FB_POST_ID"
    fi
fi

# ═════════════════════════════════════════════════════════════
# 10. Memory Update & File Sync
# ═════════════════════════════════════════════════════════════
ACTIVE_ID="${PUBLISH_ID:-$FB_POST_ID}"
echo "📝 [STEP 10] Updating memory. Active ID: $ACTIVE_ID"

if [ -n "$ACTIVE_ID" ] && [ "$ACTIVE_ID" != "None" ]; then
    python3 -c "
import os, json
mf = 'logs/agent_memory.json'
mem = {'game_scores': {}, 'title_styles': {'curiosity': 10, 'aggressive': 10, 'question': 10, 'emoji_heavy': 10}}
if os.path.exists(mf):
    try:
        with open(mf) as f: mem.update(json.load(f))
    except: pass
mem['game_scores']['$SELECTED_GAME_NAME'] = mem['game_scores'].get('$SELECTED_GAME_NAME', 10) + 5
if '$SELECTED_STYLE' in mem['title_styles']:
    mem['title_styles']['$SELECTED_STYLE'] += 3
os.makedirs('logs', exist_ok=True)
with open(mf, 'w') as f: json.dump(mem, f, indent=4)
print('🧠 Memory updated.')
"

    python3 -c "
import os
tf = '$TARGET_FILE'
pl = '$GAME_POSTED_LOG'
sl = '''$SELECTED_LINE'''
aid = '$ACTIVE_ID'
if os.path.exists(tf):
    with open(tf, 'r', encoding='utf-8', errors='ignore') as f:
        c = f.read()
    cl = c.replace(sl, '').strip()
    with open(tf, 'w', encoding='utf-8') as f:
        f.write(cl + '\n\n')
os.makedirs(os.path.dirname(pl), exist_ok=True)
with open(pl, 'a', encoding='utf-8') as f:
    f.write(sl + f'\nVideo id : {aid}\n\n')
print('✅ Link moved to posted folder.')
"
fi

echo ""
echo "===================================================="
echo "🏁 Pipeline Finished at: $(date '+%Y-%m-%d %H:%M:%S IST')"
echo "===================================================="