#!/bin/bash
# ==========================================
# FULLY AUTOMATED PIPELINE (WITH EXACT IST TIME & SMART COOLDOWN)
# ==========================================

BASE="/storage/emulated/0/GitHub"
API="https://graph.facebook.com/v24.0"
LINKS_DIR="$BASE/game_links_editor"
POSTED_DIR="$BASE/posted_links"
FRAMES_DIR="$BASE/temp_frames"
LOG_DIR="$BASE/logs"
COOLDOWN_TRACKER="$LOG_DIR/last_post_timestamp.txt"
LOG_FILE="$LOG_DIR/last_broadcast_log.txt"

mkdir -p "$LINKS_DIR" "$POSTED_DIR" "$FRAMES_DIR" "$LOG_DIR"

# ⏱️ Target Cooldown Minutes (Default 300 minutes / 5 hours)
TARGET_COOLDOWN_MINUTES="${COOLDOWN_MINUTES:-300}"

# 🔑 Token & Config Loading
if [ -f "$BASE/config.env" ]; then source "$BASE/config.env"; fi
if [ -f "$BASE/refresh_token.sh" ]; then bash "$BASE/refresh_token.sh" || true; fi
if [ -f "$BASE/page_token.env" ]; then source "$BASE/page_token.env"; fi

if [ -z "$PAGE_ACCESS_TOKEN" ]; then
    ERROR_MSG="❌ [$(date)] Page Access Token not found! Check config.env or page_token.env."
    echo "$ERROR_MSG" | tee -a "$LOG_FILE"
    exit 1
fi

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

# 🔍 Fetch FB Page Details
PAGE_INFO=$(curl -s "$API/$PAGE_ID?access_token=$PAGE_ACCESS_TOKEN&fields=name,id")
P_Name=$(echo "$PAGE_INFO" | python3 -c "import sys, json; print(json.load(sys.stdin).get('name', ''))" 2>/dev/null)

# 🧠 SMART HYBRID COOLDOWN & EXACT IST TIME CHECK
check_fb_cooldown() {
    CURRENT_EPOCH=$(date +%s)
    
    # STEP 1: Pehle Local File check karo (Zero API abuse)
    if [ -f "$COOLDOWN_TRACKER" ]; then
        LAST_POST_EPOCH=$(cat "$COOLDOWN_TRACKER" | tr -d '[:space:]' | head -n 1)
        
        if [[ "$LAST_POST_EPOCH" =~ ^[0-9]+$ ]]; then
            DIFF_SECONDS=$((CURRENT_EPOCH - LAST_POST_EPOCH))
            DIFF_MINS=$(python3 -c "print(round($DIFF_SECONDS / 60, 2))")
            
            IS_LESS_THAN_COOLDOWN=$(python3 -c "print('yes' if float('$DIFF_MINS') < float('$TARGET_COOLDOWN_MINUTES') else 'no')")
            
            if [ "$IS_LESS_THAN_COOLDOWN" == "yes" ]; then
                rem_time_mins=$(python3 -c "print(round(float('$TARGET_COOLDOWN_MINUTES') - float('$DIFF_MINS'), 2))")
                rem_hours=$(python3 -c "print(round(float('$rem_time_mins') / 60, 2))")
                echo "⏳ [Local Cache] Cooldown active hai! Aakhri post ko sirf $DIFF_MINS minutes hue hain."
                echo "🛑 Script chupchaap exit ho rahi hai. Lagbhag $rem_hours ghante baaki hain."
                exit 0
            else
                echo "✅ [Local Cache] Cooldown period poora ho chuka hai. Live API verification check kar rahe hain..."
            fi
        fi
    fi

    # STEP 2: Live Facebook Page Videos API Check with Exact IST Time Logic
    echo "🔍 Checking Last Facebook Video Time..." >&2
    FB_VIDEOS_RES=$(curl -s "$API/$PAGE_ID/videos?access_token=$PAGE_ACCESS_TOKEN&fields=id,created_time&limit=1")

    PYTHON_PARSED=$(echo "$FB_VIDEOS_RES" | python3 -c "
import sys, json
from datetime import datetime, timezone, timedelta

try:
    data = json.load(sys.stdin).get('data', [])
    if data:
        post_id = data[0].get('id')
        created_utc = data[0].get('created_time')
        
        # Convert UTC to IST (+5:30)
        dt_utc = datetime.strptime(created_utc, '%Y-%m-%dT%H:%M:%S+0000').replace(tzinfo=timezone.utc)
        dt_ist = dt_utc.astimezone(timezone(timedelta(hours=5, minutes=30)))
        formatted_ist = dt_ist.strftime('%d %B %Y, %I:%M:%S %p IST')
        epoch_time = int(dt_utc.timestamp())
        
        print(f'EPOCH:{epoch_time}')
        print(f'ID:{post_id}')
        print(f'TIME:{formatted_ist}')
    else:
        print('NO_VIDEOS')
except Exception as e:
    print('ERROR:', e)
")

    # Parse Python output
    LAST_POST_EPOCH=$(echo "$PYTHON_PARSED" | grep "EPOCH:" | cut -d':' -f2)
    LAST_POST_ID=$(echo "$PYTHON_PARSED" | grep "ID:" | cut -d':' -f2)
    LAST_POST_TIME_STR=$(echo "$PYTHON_PARSED" | grep "TIME:" | cut -d':' -f2-)

    # Log entry format
    LOG_ENTRY="========================================
📅 Checked At: $(date)
🚩 Page Name: $P_Name ($PAGE_ID)
Video ID: ${LAST_POST_ID:-N/A}
Last Post Time: ${LAST_POST_TIME_STR:-No videos found on the page.}
========================================"
    echo "$LOG_ENTRY" | tee -a "$LOG_FILE"

    if [ -n "$LAST_POST_EPOCH" ] && [[ "$LAST_POST_EPOCH" =~ ^[0-9]+$ ]]; then
        DIFF_SECONDS=$(( CURRENT_EPOCH - LAST_POST_EPOCH ))
        DIFF_MINUTES=$(( DIFF_SECONDS / 60 ))
        
        echo "⏱️ Live API ke mutabiq, aakhri post ko $DIFF_MINUTES minutes ho chuke hain."
        
        if [ $DIFF_MINUTES -lt $TARGET_COOLDOWN_MINUTES ]; then
            REMAINING=$(( TARGET_COOLDOWN_MINUTES - DIFF_MINUTES ))
            echo "⏳ Cooldown active hai! Abhi bhi $REMAINING minutes baaki hain."
            echo "$LAST_POST_EPOCH" > "$COOLDOWN_TRACKER"
            echo "🛑 Script exit ho rahi hai."
            exit 0
        else
            echo "✅ Live API Cooldown bhi poora ho chuka hai! Nayi post process ho rahi hai."
        fi
    fi
}

# 🚀 Run Cooldown Check
check_fb_cooldown

# 1. Randomly pick an unposted game file from the folder
shopt -s nullglob
GAME_FILES=("$LINKS_DIR"/*.txt)

if [ ${#GAME_FILES[@]} -eq 0 ]; then
    echo "⚠️ Koi unposted link file nahi mili!"
    exit 0
fi

RANDOM_INDEX=$((RANDOM % ${#GAME_FILES[@]}))
TARGET_FILE="${GAME_FILES[$RANDOM_INDEX]}"

RAW_GNAME=$(basename "$TARGET_FILE")
SELECTED_GAME_NAME="${RAW_GNAME%_uploaded_links.txt}"
SELECTED_GAME_NAME="${SELECTED_GAME_NAME%.txt}"
GAME_POSTED_LOG="$POSTED_DIR/${SELECTED_GAME_NAME}_posted_links.txt"

echo "🎮 Randomly Auto-Selected Game File: $RAW_GNAME"

# 2. Parse and Randomly pick a link from selected file
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

echo "🔗 Randomly Selected Link: $SELECTED_URL"

# 3. 📸 8 Screenshots & Grid Generation
CURRENT_GEMINI_KEY=$(get_random_gemini_key)
rm -f "$FRAMES_DIR"/*.jpg

timestamps=("00:00:02" "00:00:05" "00:00:08" "00:00:11" "00:00:14" "00:00:17" "00:00:20" "00:00:23")
for i in "${!timestamps[@]}"; do
    idx=$((i+1))
    ffmpeg -y -ss "${timestamps[$i]}" -i "$SELECTED_URL" -vframes 1 -q:v 2 "$FRAMES_DIR/frame_$idx.jpg" &>/dev/null
    if [ ! -f "$FRAMES_DIR/frame_$idx.jpg" ]; then
        ffmpeg -y -ss "00:00:02" -i "$SELECTED_URL" -vframes 1 -q:v 2 "$FRAMES_DIR/frame_$idx.jpg" &>/dev/null
    fi
done

GRID_PATH="$FRAMES_DIR/merged_8_grid.jpg"

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
EOF

# 4. Gemini se Viral Title Generation
AI_TITLE=""
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
            while true; do
             state=$(curl -s "https://generativelanguage.googleapis.com/v1beta/files/$file_name_g_api?key=$CURRENT_GEMINI_KEY" | jq -r '.state // empty')
             [ "$state" = "ACTIVE" ] && break
             [ "$state" = "FAILED" ] && break
             sleep 1
            done

            prompt_text="Based on this 8-photos 9:16 grid screenshot, choose and output ONLY ONE single best, highly viral catchy Hook title with emojis. Do not mention game names or file numbers. Just output the plain text title string."

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

if [ -z "$AI_TITLE" ] || [ "$AI_TITLE" == "null" ]; then
    AI_TITLE="🔥 Insane Pro Gaming Moments! 🎮🔥"
fi

CAPTION="$AI_TITLE

#videogames #gamingcommunity #gaming #${SELECTED_GAME_NAME,,} #gamingreels #reels"
echo "📝 Selected Title: $AI_TITLE"

# 5. 🚀 POSTING LOGIC (Instagram Reels)
PUBLISH_ID=""

if [ -n "$PAGE_ACCESS_TOKEN" ] && [ -n "$IG_ID" ]; then
    echo "🚀 Uploading to Instagram Reels..."
    CONTAINER_RES=$(curl -s -X POST "$API/$IG_ID/media" \
      --data-urlencode "media_type=REELS" \
      --data-urlencode "video_url=$SELECTED_URL" \
      --data-urlencode "caption=$CAPTION" \
      --data-urlencode "access_token=$PAGE_ACCESS_TOKEN")

    CREATION_ID=$(echo "$CONTAINER_RES" | python3 -c "import sys, json; print(json.load(sys.stdin).get('id', ''))" 2>/dev/null)

    if [ -n "$CREATION_ID" ] && [ "$CREATION_ID" != "None" ]; then
        echo "⏳ Container created (ID: $CREATION_ID). Checking video processing status..."
        
        for i in {1..10}; do
            sleep 15
            echo "🔍 Status check attempt $i/10..."
            STATUS_RES=$(curl -s "$API/$CREATION_ID?fields=status_code,status&access_token=$PAGE_ACCESS_TOKEN")
            STATUS_CODE=$(echo "$STATUS_RES" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status_code', ''))" 2>/dev/null)
            
            if [ "$STATUS_CODE" == "FINISHED" ]; then
                echo "✅ Video processing finished!"
                break
            fi
        done

        PUBLISH_RES=$(curl -s -X POST "$API/$IG_ID/media_publish" \
          -d "creation_id=$CREATION_ID" \
          -d "access_token=$PAGE_ACCESS_TOKEN")
          
        PUBLISH_ID=$(echo "$PUBLISH_RES" | python3 -c "import sys, json; print(json.load(sys.stdin).get('id', ''))" 2>/dev/null)
        
        if [ -n "$PUBLISH_ID" ] && [ "$PUBLISH_ID" != "None" ]; then
            echo "🎉 Instagram Post Published Successfully! ID: $PUBLISH_ID"
        fi
    fi
fi

# 6. 🕒 Save Current Timestamp to Local File for Cooldown
if [ -n "$PUBLISH_ID" ] && [ "$PUBLISH_ID" != "None" ]; then
    date +%s > "$COOLDOWN_TRACKER"
    echo "🕒 New post timestamp saved locally for cooldown tracking."
fi

# 7. Local Files Cleanup & Sync
if [ -n "$PUBLISH_ID" ] && [ "$PUBLISH_ID" != "None" ]; then
    python3 -c "
import os
target_file = '$TARGET_FILE'
posted_log = '$GAME_POSTED_LOG'
selected_line = '''$SELECTED_LINE'''
pub_id = '$PUBLISH_ID'

if os.path.exists(target_file):
    with open(target_file, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    cleaned = content.replace(selected_line, '').strip()
    with open(target_file, 'w', encoding='utf-8') as f:
        f.write(cleaned + '\n\n')

os.makedirs(os.path.dirname(posted_log), exist_ok=True)
with open(posted_log, 'a', encoding='utf-8') as f:
    f.write(selected_line + f'\nVideo id : {pub_id}\n\n')
print('✅ Link shifted to posted folder!')
"
else
    echo "⚠️ Skipped file sync because Publish ID was not generated."
fi
