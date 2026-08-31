#!/bin/bash
# ==========================================
# FULLY AUTOMATED PIPELINE (CRON-SAFE & AUTO-RETRY)
# ==========================================

BASE="."
API="https://graph.facebook.com/v24.0"
LINKS_DIR="game_links_editor"
POSTED_DIR="posted_links_editor"
FRAMES_DIR="temp_frames"

GAME_LINKS_DIR="$BASE/$LINKS_DIR"
POSTED_LINKS_DIR="$BASE/$POSTED_DIR"
mkdir -p "$GAME_LINKS_DIR" "$POSTED_LINKS_DIR" "$FRAMES_DIR" "logs"

# 🔑 Gemini Keys Rotation System
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

# Default post mode (Cron ke liye agar variable na ho toh 1 maan lega)
DEFAULT_POST_MODE="${POST_MODE:-1}"

# 0. ⏳ Check 5 Hours Gap from Facebook Page Last Post
if [ -n "$PAGE_ACCESS_TOKEN" ] && [ -n "$PAGE_ID" ]; then
    echo "🔍 Checking last post time on Facebook Page to ensure 5-hour gap..."
    
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
    print(f'ERROR:{e}')
    print('LAST_POST_HOURS:999')
")

    HOURS_AGO=$(echo "$LAST_POST_CHECK" | grep "LAST_POST_HOURS" | cut -d':' -f2)
    
    if [ -n "$HOURS_AGO" ]; then
        IS_LESS_THAN_5=$(python3 -c "print('yes' if float('$HOURS_AGO') < 5.0 else 'no')")
        
        if [ "$IS_LESS_THAN_3" == "yes" ]; then
            rem_time=$(python3 -c "print(round(3.0 - float('$HOURS_AGO'), 2))")
            echo "⏳ 3 ghante ka gap poora nahi hua hai! Aakhri post sirf $HOURS_AGO ghante pehle ki gayi thi."
            echo "🛑 Script ko rok diya gaya hai. Kripya $rem_time ghante baad try karein."
            exit 0
        else
            echo "✅ 3 ghante ka gap poora ho chuka hai ($HOURS_AGO ghante pehle post hui thi). Nayi post ki ja sakti hai!"
        fi
    fi
fi

# 1. Randomly pick an unposted game file from the folder
shopt -s nullglob
GAME_FILES=("$GAME_LINKS_DIR"/*.txt)

if [ ${#GAME_FILES[@]} -eq 0 ]; then
    echo "⚠️ Koi unposted link file nahi mili!"
    exit 0
fi

RANDOM_INDEX=$((RANDOM % ${#GAME_FILES[@]}))
TARGET_FILE="${GAME_FILES[$RANDOM_INDEX]}"

RAW_GNAME=$(basename "$TARGET_FILE")
SELECTED_GAME_NAME="${RAW_GNAME%_uploaded_links.txt}"
SELECTED_GAME_NAME="${SELECTED_GAME_NAME%.txt}"
GAME_POSTED_LOG="$POSTED_LINKS_DIR/${SELECTED_GAME_NAME}_posted_links_editor.txt"

echo "🎮 Randomly Auto-Selected Game File: $RAW_GNAME"

# 2. Parse and Randomly pick a link from the selected file
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
FILE_NAME=$(echo "$PARSED_DATA" | python3 -c "import sys, json; print(json.load(sys.stdin).get('title', ''))" 2>/dev/null)
SELECTED_LINE=$(echo "$PARSED_DATA" | python3 -c "import sys, json; print(json.load(sys.stdin).get('raw', ''))" 2>/dev/null)

if [ -z "$SELECTED_URL" ]; then
    echo "⚠️ Is file me koi valid link nahi hai."
    exit 0
fi

echo "🔗 Randomly Selected Link: $SELECTED_URL"

# 3. 📸 8 Screenshots & Grid Generation
CURRENT_GEMINI_KEY=$(get_random_gemini_key)
rm -f "$FRAMES_DIR"/*.jpg

echo "📸 Taking 8 screenshots from video..."
timestamps=("00:00:02" "00:00:05" "00:00:08" "00:00:11" "00:00:14" "00:00:17" "00:00:20" "00:00:23")
for i in "${!timestamps[@]}"; do
    idx=$((i+1))
    echo "✂️ Cutting frame $idx at timestamp ${timestamps[$i]}..."
    ffmpeg -y -ss "${timestamps[$i]}" -i "$SELECTED_URL" -vframes 1 -q:v 2 "$FRAMES_DIR/frame_$idx.jpg"
    if [ ! -f "$FRAMES_DIR/frame_$idx.jpg" ]; then
        echo "⚠️ Fallback frame cut at 00:00:02..."
        ffmpeg -y -ss "00:00:02" -i "$SELECTED_URL" -vframes 1 -q:v 2 "$FRAMES_DIR/frame_$idx.jpg"
    fi
done

GRID_PATH="$FRAMES_DIR/merged_8_grid.jpg"
echo "🧩 Merging frames into grid image..."

python3 - <<EOF
import os
from PIL import Image
images = []
for i in range(1, 9):
    img_path = os.path.join('$FRAMES_DIR', f'frame_{i}.jpg')
    if os.path.exists(img_path) and os.path.getsize(img_path) > 0:
        im = Image.open(img_path).resize((540, 960))
    else:
        im = Image.new('RGB', (540, 960), (0, 0, 0))
    images.append(im)

grid_img = Image.new('RGB', (1080, 3840))
for idx, im in enumerate(images):
    col = idx % 2
    row = idx // 2
    grid_img.paste(im, (col * 540, row * 960))
grid_img.save('$GRID_PATH', 'JPEG', quality=85)
print("✅ Grid image created successfully!")
EOF

# 4. Gemini se Viral Title Generation (With Smart Auto-Retry & Key Rotation)
AI_TITLE=""
MAX_TOTAL_RETRIES=4

for ((attempt=1; attempt<=MAX_TOTAL_RETRIES; attempt++)); do
    CURRENT_GEMINI_KEY=$(get_random_gemini_key)
    
    echo "🤖 Gemini Title Generation Attempt $attempt/$MAX_TOTAL_RETRIES..."
    
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
                  [ "$state" = "FAILED" ] && break
                  sleep 1
                  state_check_counter=$((state_check_counter + 1))
                done

                if [ "$state" = "ACTIVE" ]; then
                    prompt_text="Analyze the provided 9:16 gaming screenshot/grid as a visual preview of the actual video.

Your task is to identify the MOST VIRAL, VIDEO-RELEVANT moment or story visible across the screenshot.

Do not simply describe what is happening. Understand the scene and turn the most interesting visual situation into a short, curiosity-driven Facebook/Instagram Reels hook.

VISUAL ANALYSIS:
Carefully examine:
- Main character and their action
- Enemy positions and movement
- Weapons and combat situation
- Character reactions and body language
- Location and environment
- Tactical positioning
- What appears to be happening BEFORE and AFTER the key moment
- Sudden changes between frames
- Suspense or confrontation
- Unexpected or unusual situations
- Potential payoff suggested by the sequence
- The single strongest moment that would make someone stop scrolling

VIDEO-RELATED HOOK:
The title must feel connected to what the viewer is about to see in the VIDEO, not just what one screenshot shows.

Create curiosity about the actual moment:
- What is about to happen?
- What did the character notice?
- What mistake did the enemy make?
- What unexpected move is coming?
- What makes this moment satisfying, surprising, tense, or interesting?

Use the strongest angle supported by the visuals:
curiosity, suspense, unexpected action, tactical play, perfect timing, enemy mistake, close call, sudden change, reaction, cinematic moment, or POV.

TITLE STYLE:
 - Short and punchy
- Short and punchy
- 6–10 words preferred
- 30 words maximum
- Natural English
- Strong Facebook/Instagram Reels style
- Make the viewer curious enough to watch
- Do NOT explain the whole scene
- Do NOT make it sound like a video description
- Do NOT invent an event that is not visually supported

AVOID GENERIC HOOKS:
"They Never Saw This Coming"
"Nobody Expected This"
"You Won't Believe What Happens Next"
"This Changed Everything"
"Wait For It"
"Insane Moment"
"Epic Moment"

AVOID BORING DESCRIPTIONS:
"Holding the sniper..."
"Walking toward..."
"Running through..."
"Looking at..."
"Moving into position..."

Instead, convert the situation into a compelling hook.

IMPORTANT:
If multiple frames show a sequence, understand the sequence as ONE video moment rather than treating each frame separately.

Generate several possible hooks internally, compare them for:
1. Viral potential
2. Curiosity
3. Video relevance
4. Visual accuracy
5. Emotional impact
6. Specificity
7. Shortness

Then select ONLY the strongest one.

STRICT OUTPUT:
- Output ONLY ONE title.
- No hashtags.
- No # symbol.
- No quotation marks.
- No numbering.
- No bullet points.
- No explanation.
- No extra text.
- Do not mention the game name.
- Do not mention file numbers.
- Do not mention screenshot, image, grid, or frames.
- Use 1–3 relevant emojis at the end.
- Never use danger emojis such as ☠️💀🔪🔫🩸.

FINAL RESPONSE:
ONLY THE SINGLE VIRAL TITLE STRING."

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
        echo "✅ Title generated successfully!"
        break
    else
        echo "⚠️ Attempt $attempt fail ho gaya. Doosri key ke sath try kar rahe hain..."
        AI_TITLE=""
        sleep 5
    fi
done

if [ -z "$AI_TITLE" ] || [ "$AI_TITLE" == "null" ] || [ "$AI_TITLE" == "None" ]; then
    AI_TITLE="🔥 Insane Pro Gaming Moments! 🎮🔥"
fi

CAPTION="$AI_TITLE

#videogames #gamingcommunity #gaming #${SELECTED_GAME_NAME,,} #gamingreels #reels"
echo "📝 Selected Title: $AI_TITLE"

# ================= 5. 🚀 CRON-SAFE PLATFORM CONTROLLER =================
POST_MODE="$DEFAULT_POST_MODE"
echo "🚀 Using Posting Mode: $POST_MODE (1: Both, 2: Insta Only, 3: FB Only)"

PUBLISH_ID=""
FB_POST_ID=""

# --- A. Instagram Reels Upload ---
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
            echo "⏳ Container created (ID: $CREATION_ID). Checking processing status..."
            
            for i in {1..45}; do
                sleep 5
                STATUS_RES=$(curl -s "$API/$CREATION_ID?fields=status_code,status&access_token=$PAGE_ACCESS_TOKEN")
                STATUS_CODE=$(echo "$STATUS_RES" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status_code', ''))" 2>/dev/null)
                
                if [ "$STATUS_CODE" == "FINISHED" ]; then
                    echo "✅ Video processing finished by Instagram!"
                    break
                else
                    echo "⏳ Video still processing (Status: $STATUS_CODE)..."
                fi
            done

            PUBLISH_RES=$(curl -s -X POST "$API/$IG_ID/media_publish" \
              -d "creation_id=$CREATION_ID" \
              -d "access_token=$PAGE_ACCESS_TOKEN")
              
            PUBLISH_ID=$(echo "$PUBLISH_RES" | python3 -c "import sys, json; print(json.load(sys.stdin).get('id', ''))" 2>/dev/null)
            
            if [ -n "$PUBLISH_ID" ] && [ "$PUBLISH_ID" != "None" ]; then
                echo "🎉 Instagram Post Published Successfully! ID: $PUBLISH_ID"
            else
                echo "❌ Error: Failed to publish container to Instagram!"
            fi
        fi
    fi
fi

# --- B. Facebook Page Video Upload ---
if [ "$POST_MODE" == "1" ] || [ "$POST_MODE" == "3" ]; then
    if [ -n "$PAGE_ACCESS_TOKEN" ] && [ -n "$PAGE_ID" ]; then
        echo "🚀 Uploading to Facebook Page..."
        FB_RES=$(curl -s -X POST "$API/$PAGE_ID/videos" \
          --data-urlencode "file_url=$SELECTED_URL" \
          --data-urlencode "description=$CAPTION" \
          --data-urlencode "access_token=$PAGE_ACCESS_TOKEN")

        FB_POST_ID=$(echo "$FB_RES" | python3 -c "import sys, json; print(json.load(sys.stdin).get('id', ''))" 2>/dev/null)

        if [ -n "$FB_POST_ID" ] && [ "$FB_POST_ID" != "None" ]; then
            echo "🎉 Successfully Published to Facebook Page! Video ID: $FB_POST_ID"
        else
            echo "❌ Error: Failed to publish video to Facebook Page!"
        fi
    fi
fi

# 6. 📊 Insights Check
if [ -n "$PUBLISH_ID" ] && [ "$PUBLISH_ID" != "None" ]; then
    echo "📊 Fetching Instagram insights..."
    INSIGHTS_RES=$(curl -s "$API/$PUBLISH_ID/insights?metric=clips_reels_play_count,clips_reels_total_interactions,likes,comments&access_token=$PAGE_ACCESS_TOKEN")
    echo "$INSIGHTS_RES" > "logs/insight_$PUBLISH_ID.json"
fi

# 7. Local Files Cleanup & Sync
ACTIVE_ID="${PUBLISH_ID:-$FB_POST_ID}"

if [ -n "$ACTIVE_ID" ] && [ "$ACTIVE_ID" != "None" ]; then
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
    echo "⚠️ Skipped file sync because no post ID was generated from platforms."
fi
