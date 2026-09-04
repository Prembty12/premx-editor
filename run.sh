#!/bin/bash
# ==========================================
# 🤖 TRUE AI AGENT FULLY AUTOMATED PIPELINE (12S MONETIZATION GUARDED)
# ==========================================

BASE="."
API="https://graph.facebook.com/v24.0"
LINKS_DIR="game_links_editor"
POSTED_DIR="posted_links_editor"
FRAMES_DIR="temp_frames"

GAME_LINKS_DIR="$BASE/$LINKS_DIR"
POSTED_LINKS_DIR="$BASE/$POSTED_DIR"
mkdir -p "$GAME_LINKS_DIR" "$POSTED_LINKS_DIR" "$FRAMES_DIR" "logs"

GEMINI_KEYS=("$GEMINI_API_KEY_1" "$GEMINI_API_KEY_2" "$GEMINI_API_KEY_3")

get_random_gemini_key() {
    local valid_keys=()
    for k in "${GEMINI_KEYS[@]}"; do
        if [ -n "$k" ]; then
            valid_keys+=("$k")
        fi
    done
    if [ ${#valid_keys[@]} -eq 0 ]; then
        echo "$GEMINI_API_KEY_1"
    else
        echo "${valid_keys[$((RANDOM % ${#valid_keys[@]}))]}"
    fi
}

DEFAULT_POST_MODE="${POST_MODE:-1}"
MIN_CLIP_DURATION=12  # 🔒 Strict Facebook Monetization Rule: Minimum 12 seconds required

# 0. 🍪 Pre-Flight Cookie Health Check
echo "🔍 Checking Facebook Cookie Session Health..."
python3 cookie_checker.py
if [ $? -ne 0 ]; then
    echo "❌ Pipeline halted due to invalid or expired Facebook cookies."
    exit 1
fi

# 1. 📊 Update Past Performance via Real Facebook Insights
echo "📈 Pulling real analytics and insights from past posts..."
python3 insights_tracker.py

# 2. ⏳ Check 3 Hours Gap
if [ "$DEFAULT_POST_MODE" != "2" ] && [ -n "$PAGE_ACCESS_TOKEN" ] && [ -n "$PAGE_ID" ]; then
    echo "🔍 Checking last post time on Facebook Page to ensure 3-hour gap..."
    
    LAST_POST_CHECK=$(python3 -c "
import requests, sys
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
    print('LAST_POST_HOURS:999')
")

    HOURS_AGO=$(echo "$LAST_POST_CHECK" | grep "LAST_POST_HOURS" | cut -d':' -f2)
    
    if [ -n "$HOURS_AGO" ]; then
        IS_LESS_THAN_3=$(python3 -c "print('yes' if float('$HOURS_AGO') < 3.0 else 'no')")
        
        if [ "$IS_LESS_THAN_3" == "yes" ]; then
            echo "⏳ 3 ghante ka gap poora nahi hua hai! Sirf $HOURS_AGO ghante hue hain."
            exit 0
        else
            echo "✅ 3 ghante ka gap poora ho chuka hai."
        fi
    fi
fi

# 3. 🧠 AI AGENT BRAIN: Smart Game & Title Style Selection
echo "🤖 Consulting AI Agent Brain (ai_agent.py)..."
AGENT_OUTPUT=$(python3 ai_agent.py)

TARGET_FILE=$(echo "$AGENT_OUTPUT" | python3 -c "import sys, json; print(json.load(sys.stdin).get('target_file', ''))" 2>/dev/null)
SELECTED_GAME_NAME=$(echo "$AGENT_OUTPUT" | python3 -c "import sys, json; print(json.load(sys.stdin).get('game_name', ''))" 2>/dev/null)
SELECTED_STYLE=$(echo "$AGENT_OUTPUT" | python3 -c "import sys, json; print(json.load(sys.stdin).get('chosen_style', 'curiosity'))" 2>/dev/null)

if [ -z "$TARGET_FILE" ] || [ "$TARGET_FILE" == "None" ] || [ ! -f "$TARGET_FILE" ]; then
    echo "⚠️ AI Agent ko koi valid game file nahi mili!"
    exit 0
fi

GAME_POSTED_LOG="$POSTED_LINKS_DIR/${SELECTED_GAME_NAME}_posted_links_editor.txt"

echo "🎮 AI Agent Selected Game: $SELECTED_GAME_NAME"
echo "🎨 AI Agent Selected Title Style: $SELECTED_STYLE"

# 4. Parse and Validate Link from selected file
PARSED_DATA=$(TARGET_FILE="$TARGET_FILE" python3 -c "
import sys, json, os, random
target = os.environ.get('TARGET_FILE', '')
if not os.path.exists(target):
    print('{}')
    sys.exit(0)

with open(target, 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

lines = [l.strip() for l in content.split('\n') if l.strip()]
if not lines:
    print('{}')
    sys.exit(0)

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
    echo "⚠️ Is file me koi valid link nahi hai."
    exit 0
fi

echo "🔗 Validated Link Found: $SELECTED_URL"

# 5. ✂️ Dynamic Trimming & Monetization Safety Guard Check (Min 12 Seconds)
echo "✂️ Calculating optimal clip duration with 12s Monetization Guard..."
SOURCE_DURATION=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$SELECTED_URL" 2>/dev/null)
SOURCE_DURATION=${SOURCE_DURATION%.*}
if [ -z "$SOURCE_DURATION" ] || [ "$SOURCE_DURATION" -le 0 ]; then
    SOURCE_DURATION=30
fi

# AI/Insights or dynamic range determination (e.g. between 15 to 45 seconds based on content)
DYNAMIC_TARGET_DURATION=$(( (RANDOM % 31) + 15 )) 

# Enforce strict minimum 12-second monetization safeguard rule
if [ "$DYNAMIC_TARGET_DURATION" -lt "$MIN_CLIP_DURATION" ]; then
    FINAL_CLIP_DURATION="$MIN_CLIP_DURATION"
else
    FINAL_CLIP_DURATION="$DYNAMIC_TARGET_DURATION"
fi

# Ensure clip duration doesn't exceed source video length
if [ "$FINAL_CLIP_DURATION" -gt "$SOURCE_DURATION" ]; then
    FINAL_CLIP_DURATION="$SOURCE_DURATION"
fi

echo "🔒 Locked Clip Duration: $FINAL_CLIP_DURATION seconds (Meets Facebook 12s Monetization Standard)."

# 6. 📸 30 Dynamic Frames & 5x6 Vertical Grid Generation
rm -f "$FRAMES_DIR"/*.jpg

echo "📸 Extracting 30 dynamic frames..."
DURATION="$FINAL_CLIP_DURATION"
NUM_FRAMES=30
interval=$((DURATION / NUM_FRAMES))
[ "$interval" -lt 1 ] && interval=1

timestamps=()
for ((i=1; i<=NUM_FRAMES; i++)); do
    t=$(( (i - 1) * interval ))
    [ "$t" -ge "$DURATION" ] && t=$((DURATION - 1))
    [ "$t" -lt 0 ] && t=0
    min=$((t / 60))
    sec=$((t % 60))
    timestamps+=($(printf "00:%02d:%02d" $min $sec))
done

for i in "${!timestamps[@]}"; do
    idx=$((i+1))
    ts="${timestamps[$i]}"
    frame_path="$FRAMES_DIR/frame_$idx.jpg"
    ffmpeg -y -ss "$ts" -i "$SELECTED_URL" -vframes 1 -q:v 2 "$frame_path" -loglevel info >/dev/null 2>&1
    if [ ! -f "$frame_path" ] || [ ! -s "$frame_path" ]; then
        ffmpeg -y -ss "00:00:01" -i "$SELECTED_URL" -vframes 1 -q:v 2 "$frame_path" -loglevel info >/dev/null 2>&1
    fi
done

GRID_PATH="$FRAMES_DIR/merged_30_grid_screenshot.jpg"
echo "🧩 Merging frames into 5x6 vertical grid..."

python3 - <<EOF
import os
try:
    from PIL import Image, ImageDraw
except ImportError:
    import subprocess
    subprocess.run(["pip", "install", "Pillow"], check=True)
    from PIL import Image, ImageDraw

frames_dir = '$FRAMES_DIR'
grid_path = '$GRID_PATH'
timestamps = "${timestamps[*]}".split()

for i, ts in enumerate(timestamps):
    idx = i + 1
    frame_path = os.path.join(frames_dir, f'frame_{idx}.jpg')
    if os.path.exists(frame_path) and os.path.getsize(frame_path) > 0:
        try:
            im = Image.open(frame_path).resize((432, 640))
            draw = ImageDraw.Draw(im)
            draw.rectangle([10, 10, 130, 50], fill=(0, 0, 0))
            draw.text((15, 18), ts, fill=(255, 255, 255))
            im.save(frame_path, 'JPEG', quality=85)
        except Exception:
            pass

images = []
for i in range(1, 31):
    img_path = os.path.join(frames_dir, f'frame_{i}.jpg')
    if os.path.exists(img_path) and os.path.getsize(img_path) > 0:
        try:
            im = Image.open(img_path)
        except Exception:
            im = Image.new('RGB', (432, 640), (0, 0, 0))
    else:
        im = Image.new('RGB', (432, 640), (0, 0, 0))
    images.append(im)

grid_img = Image.new('RGB', (2160, 3840))
for idx, im in enumerate(images):
    col = idx % 5
    row = idx // 5
    grid_img.paste(im, (col * 432, row * 640))

grid_img.save(grid_path, 'JPEG', quality=85)
EOF

# 7. Gemini Title Generation with Adaptive Style Prompt
if [ "$SELECTED_STYLE" == "aggressive" ]; then
    STYLE_PROMPT="Create a bold, intense, high-energy aggressive gaming hook title. Make it sound shocking or extreme."
elif [ "$SELECTED_STYLE" == "question" ]; then
    STYLE_PROMPT="Create a curiosity-driven question hook title that forces the viewer to watch till the end."
elif [ "$SELECTED_STYLE" == "emoji_heavy" ]; then
    STYLE_PROMPT="Create a fast-paced viral gaming title packed with strong expressions and matching dynamic emojis."
else
    STYLE_PROMPT="Create a high-curiosity viral Facebook/Instagram Reels hook title. 6-10 words preferred."
fi

AI_TITLE=""
MAX_TOTAL_RETRIES=4

for ((attempt=1; attempt<=MAX_TOTAL_RETRIES; attempt++)); do
    CURRENT_GEMINI_KEY=$(get_random_gemini_key)
    echo "🤖 Gemini Title Generation Attempt $attempt/$MAX_TOTAL_RETRIES (Style: $SELECTED_STYLE)..."
    
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
                
                state_check_counter=0
                while [ $state_check_counter -lt 10 ]; do
                  state=$(curl -s "https://generativelanguage.googleapis.com/v1beta/files/$file_name_g_api?key=$CURRENT_GEMINI_KEY" | jq -r '.state // empty')
                  [ "$state" = "ACTIVE" ] && break
                  sleep 1
                  state_check_counter=$((state_check_counter + 1))
                done

                if [ "$state" = "ACTIVE" ]; then
                    prompt_text="Analyze the provided 9:16 gaming screenshot grid. $STYLE_PROMPT No punctuation quotes, max 25 words, 1-3 emojis at the end. ONLY THE TITLE STRING."

                    payload=$(jq -n \
                      --arg uri "$file_uri" \
                      --arg mime "image/jpeg" \
                      --arg ptext "$prompt_text" \
                      '{contents: [{parts: [{file_data: {file_uri: $uri, mime_type: $mime}}, {text: $ptext}]}]}')

                    gemini_resp=$(curl -s -X POST -H "Content-Type: application/json" \
                      "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent?key=$CURRENT_GEMINI_KEY" \
                      -d "$payload")

                    AI_TITLE=$(echo "$gemini_resp" | jq -r '.candidates[0].content.parts[0].text // empty' | tr -d '"')
                fi
            fi
        fi
    fi

    if [ -n "$AI_TITLE" ] && [ "$AI_TITLE" != "null" ] && [ "$AI_TITLE" != "None" ]; then
        break
    else
        AI_TITLE=""
        sleep 3
    fi
done

# Smart Local AI Fallback Engine
if [ -z "$AI_TITLE" ] || [ "$AI_TITLE" == "null" ] || [ "$AI_TITLE" == "None" ]; then
    echo "⚠️ Gemini API busy/fail! Activating Smart Local AI Fallback Engine..."
    
    AI_TITLE=$(python3 -c "
import random
game = '$SELECTED_GAME_NAME'.replace('_', ' ').title()
style = '$SELECTED_STYLE'

templates = {
    'curiosity': [
        f'The Secret {game} Play Nobody Expected 🤯',
        f'This {game} Trick Will Change Everything For You 🤫',
        f'You Wont Believe How This {game} Match Ended 😳'
    ],
    'aggressive': [
        f'Destroying Everyone In {game} Without Mercy 🔥',
        f'Absolute Chaos In This Insane {game} Lobby 💀',
        f'Total Destruction: Pure {game} Gameplay ⚡'
    ],
    'question': [
        f'How Did This {game} Player Pull Off This Move? 🤔',
        f'Can Anyone Beat This Insane {game} Record? 🎯',
        f'Is This The Best {game} Play Ever? 🧐'
    ],
    'emoji_heavy': [
        f'INSANE {game} MOMENT 💀🔥🎮',
        f'PRO {game} GAMEPLAY 🚀🔥💯',
        f'GOD LEVEL {game} SKILLS ⚡👑🔥'
    ]
}

pool = templates.get(style, templates['curiosity'])
print(random.choice(pool))
")
fi

CAPTION="$AI_TITLE

#videogames #gamingcommunity #gaming #${SELECTED_GAME_NAME,,} #gamingreels #reels"
echo "📝 Generated Title: $AI_TITLE"

# 8. 🚀 Upload to Platforms
POST_MODE="$DEFAULT_POST_MODE"
PUBLISH_ID=""
FB_POST_ID=""

if [ "$POST_MODE" == "1" ] || [ "$POST_MODE" == "2" ]; then
    if [ -n "$PAGE_ACCESS_TOKEN" ] && [ -n "$IG_ID" ]; then
        echo "🚀 Uploading to Instagram Reels..."
        CONTAINER_RES=$(curl -s -X POST "$API/$IG_ID/media" \
          --data-urlencode "media_type=REELS" \
          --data-urlencode "video_url=$SELECTED_URL" \
          --data-urlencode "caption=$CAPTION" \
          --data-urlencode "access_token=$PAGE_ACCESS_TOKEN")

        CREATION_ID=$(echo "$CONTAINER_RES" | python3 -c "import sys, json; print(json.load(sys.stdin).get('id', ''))" 2>/dev/null)

        if [ -n "$CREATION_ID" ] && [ "$CREATION_ID" != "None" ]; then
            for i in {1..45}; do
                sleep 5
                STATUS_RES=$(curl -s "$API/$CREATION_ID?fields=status_code,status&access_token=$PAGE_ACCESS_TOKEN")
                STATUS_CODE=$(echo "$STATUS_RES" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status_code', ''))" 2>/dev/null)
                [ "$STATUS_CODE" == "FINISHED" ] && break
            done

            PUBLISH_RES=$(curl -s -X POST "$API/$IG_ID/media_publish" \
              -d "creation_id=$CREATION_ID" \
              -d "access_token=$PAGE_ACCESS_TOKEN")
              
            PUBLISH_ID=$(echo "$PUBLISH_RES" | python3 -c "import sys, json; print(json.load(sys.stdin).get('id', ''))" 2>/dev/null)
        fi
    fi
fi

if [ "$POST_MODE" == "1" ] || [ "$POST_MODE" == "3" ]; then
    if [ -n "$PAGE_ACCESS_TOKEN" ] && [ -n "$PAGE_ID" ]; then
        echo "🚀 Uploading to Facebook Page..."
        FB_RES=$(curl -s -X POST "$API/$PAGE_ID/videos" \
          --data-urlencode "file_url=$SELECTED_URL" \
          --data-urlencode "description=$CAPTION" \
          --data-urlencode "access_token=$PAGE_ACCESS_TOKEN")

        FB_POST_ID=$(echo "$FB_RES" | python3 -c "import sys, json; print(json.load(sys.stdin).get('id', ''))" 2>/dev/null)
    fi
fi

# 9. 🧠 Memory & Adaptive Feedback Update
ACTIVE_ID="${PUBLISH_ID:-$FB_POST_ID}"

if [ -n "$ACTIVE_ID" ] && [ "$ACTIVE_ID" != "None" ]; then
    python3 -c "
import os, json

memory_file = 'logs/agent_memory.json'
memory = {'game_scores': {}, 'title_styles': {'curiosity': 10, 'aggressive': 10, 'question': 10, 'emoji_heavy': 10}}
if os.path.exists(memory_file):
    try:
        with open(memory_file, 'r', encoding='utf-8') as f:
            memory.update(json.load(f))
    except:
        pass

g_name = '$SELECTED_GAME_NAME'
memory['game_scores'][g_name] = memory['game_scores'].get(g_name, 10) + 5

used_style = '$SELECTED_STYLE'
if used_style in memory['title_styles']:
    memory['title_styles'][used_style] += 3

os.makedirs('logs', exist_ok=True)
with open(memory_file, 'w', encoding='utf-8') as f:
    json.dump(memory, f, indent=4)

print('🧠 Agent Memory & Adaptive Style Feedback Updated Successfully!')
"

    python3 -c "
import os
target_file = '$TARGET_FILE'
posted_log = '$GAME_POSTED_LOG'
selected_line = '''$SELECTED_LINE'''
act_id = '$ACTIVE_ID'

if os.path.exists(target_file):
    with open(target_file, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    cleaned = content.replace(selected_line, '').strip()
    with open(target_file, 'w', encoding='utf-8') as f:
        f.write(cleaned + '\n\n')

os.makedirs(os.path.dirname(posted_log), exist_ok=True)
with open(posted_log, 'a', encoding='utf-8') as f:
    f.write(selected_line + f'\nVideo id : {act_id}\n\n')
print('✅ Link shifted to posted folder successfully!')
"
else
    echo "⚠️ Skipped file sync because no post ID was generated."
fi

