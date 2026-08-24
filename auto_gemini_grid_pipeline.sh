#!/bin/bash
# ==========================================
# FULLY AUTOMATED PIPELINE (INSTANT TEST MODE)
# ==========================================

BASE="."
API="https://graph.facebook.com/v24.0"
LINKS_DIR="game_links_editor"
POSTED_DIR="posted_links"
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

# 1. Unposted game file pick karega
shopt -s nullglob
GAME_FILES=("$GAME_LINKS_DIR"/*.txt)

if [ ${#GAME_FILES[@]} -eq 0 ]; then
    echo "⚠️ Koi unposted link file nahi mili!"
    exit 0
fi

TARGET_FILE="${GAME_FILES[0]}"
RAW_GNAME=$(basename "$TARGET_FILE")
SELECTED_GAME_NAME="${RAW_GNAME%_uploaded_links.txt}"
SELECTED_GAME_NAME="${SELECTED_GAME_NAME%.txt}"
GAME_POSTED_LOG="$POSTED_LINKS_DIR/${SELECTED_GAME_NAME}_posted_links.txt"

echo "🎮 Auto-Selected Game File: $RAW_GNAME"

# 2. File se link parse karega
PARSED_DATA=$(TARGET_FILE="$TARGET_FILE" python3 -c "
import sys, json, os
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

url = ''
title = ''
raw_lines = []
for idx, line in enumerate(lines):
    if line.startswith('http://') or line.startswith('https://'):
        url = line
        if idx > 0 and not lines[idx-1].startswith('http'):
            title = lines[idx-1]
            raw_lines = [lines[idx-1], line]
        else:
            title = os.path.basename(url).split('?')[0]
            raw_lines = [line]
        break

print(json.dumps({'title': title.replace('Original:', '').strip(), 'url': url, 'raw': '\n'.join(raw_lines)}))
")

SELECTED_URL=$(echo "$PARSED_DATA" | python3 -c "import sys, json; print(json.load(sys.stdin).get('url', ''))" 2>/dev/null)
FILE_NAME=$(echo "$PARSED_DATA" | python3 -c "import sys, json; print(json.load(sys.stdin).get('title', ''))" 2>/dev/null)
SELECTED_LINE=$(echo "$PARSED_DATA" | python3 -c "import sys, json; print(json.load(sys.stdin).get('raw', ''))" 2>/dev/null)

if [ -z "$SELECTED_URL" ]; then
    echo "⚠️ Is file me koi valid link nahi hai."
    exit 0
fi

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

# 5. 🚀 POSTING LOGIC (Instagram Only vs Both)
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
        sleep 12
        PUBLISH_RES=$(curl -s -X POST "$API/$IG_ID/media_publish" \
          -d "creation_id=$CREATION_ID" \
          -d "access_token=$PAGE_ACCESS_TOKEN")
        PUBLISH_ID=$(echo "$PUBLISH_RES" | python3 -c "import sys, json; print(json.load(sys.stdin).get('id', ''))" 2>/dev/null)
        echo "🎉 Instagram Post Published! ID: $PUBLISH_ID"
    fi
fi

echo "🎛️ Current Posting Mode: $POST_MODE"
if [ "$POST_MODE" == "both" ] && [ -n "$PAGE_ACCESS_TOKEN" ] && [ -n "$PAGE_ID" ]; then
    echo "🚀 'both' mode active hai, Facebook Page par bhi post ho rahi hai..."
    FB_POST_RES=$(curl -s -X POST "$API/$PAGE_ID/videos" \
      --data-urlencode "file_url=$SELECTED_URL" \
      --data-urlencode "description=$CAPTION" \
      --data-urlencode "access_token=$PAGE_ACCESS_TOKEN")
    echo "🎉 Facebook Post Result: $FB_POST_RES"
fi

# 6. 📊 Insights Check
if [ -n "$PUBLISH_ID" ] && [ "$PUBLISH_ID" != "None" ]; then
    echo "📊 Fetching Instagram insights..."
    INSIGHTS_RES=$(curl -s "$API/$PUBLISH_ID/insights?metric=clips_reels_play_count,clips_reels_total_interactions,likes,comments&access_token=$PAGE_ACCESS_TOKEN")
    echo "$INSIGHTS_RES" > "logs/insight_$PUBLISH_ID.json"
fi

# 7. Local Files Cleanup & Sync
if [ -n "$PUBLISH_ID" ]; then
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
fi
