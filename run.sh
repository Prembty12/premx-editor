#!/bin/bash
# ==========================================
# 🤖 TRUE AI AGENT FULLY AUTOMATED PIPELINE (FIXED PARSING & MODEL)
# ==========================================

BASE="."
API="https://graph.facebook.com/v24.0"
LINKS_DIR="game_links_editor"
POSTED_DIR="posted_links_editor"
FRAMES_DIR="temp_frames"

GAME_LINKS_DIR="$BASE/$LINKS_DIR"
POSTED_LINKS_DIR="$BASE/$POSTED_DIR"
mkdir -p "$GAME_LINKS_DIR" "$POSTED_LINKS_DIR" "$FRAMES_DIR" "logs"

LOG_FILE="logs/pipeline_debug.log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "===================================================="
echo "🚀 Pipeline Started at: $(date)"
echo "===================================================="

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
        local idx=$((RANDOM % ${#valid_keys[@]}))
        echo "${valid_keys[$idx]}"
    fi
}

DEFAULT_POST_MODE="${POST_MODE:-1}"
MIN_CLIP_DURATION=12

# 0. 🍪 Pre-Flight Cookie Health Check
echo "🔍 [STEP 0] Checking Facebook Cookie Session Health..."
python3 cookie_checker.py
if [ $? -ne 0 ]; then
    echo "❌ [ERROR] Pipeline halted due to invalid or expired Facebook cookies."
    exit 1
fi

# 1. 📊 Update Past Performance & Insights
echo "📈 [STEP 1] Pulling real analytics and insights from past posts..."
python3 insights_tracker.py

# 2. ⏳ Check 3 Hours Gap
if [ "$DEFAULT_POST_MODE" != "2" ] && [ -n "$PAGE_ACCESS_TOKEN" ] && [ -n "$PAGE_ID" ]; then
    echo "🔍 [STEP 2] Checking last post time on Facebook Page..."
    
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
    print(f'LAST_POST_HOURS:999 (Error: {e})')
")

    HOURS_AGO=$(echo "$LAST_POST_CHECK" | grep "LAST_POST_HOURS" | cut -d':' -f2)
    echo "📊 Hours since last post: $HOURS_AGO"
    
    if [ -n "$HOURS_AGO" ]; then
        IS_LESS_THAN_3=$(python3 -c "print('yes' if float('$HOURS_AGO' or '0') < 3.0 else 'no')")
        if [ "$IS_LESS_THAN_3" == "yes" ]; then
            echo "⏳ 3 ghante ka gap poora nahi hua hai! Sirf $HOURS_AGO ghante hue hain."
            exit 0
        else
            echo "✅ 3 ghante ka gap poora ho chuka hai."
        fi
    fi
fi

# 3. 🧠 AI AGENT BRAIN
echo "🤖 [STEP 3] Consulting AI Agent Brain (ai_agent.py)..."
AGENT_OUTPUT=$(python3 ai_agent.py)
echo "🧠 AI Agent Raw Output: $AGENT_OUTPUT"

TARGET_FILE=$(echo "$AGENT_OUTPUT" | python3 -c "import sys, json; print(json.load(sys.stdin).get('target_file', ''))" 2>/dev/null)
SELECTED_GAME_NAME=$(echo "$AGENT_OUTPUT" | python3 -c "import sys, json; print(json.load(sys.stdin).get('game_name', ''))" 2>/dev/null)
SELECTED_STYLE=$(echo "$AGENT_OUTPUT" | python3 -c "import sys, json; print(json.load(sys.stdin).get('chosen_style', 'curiosity'))" 2>/dev/null)

if [ -z "$TARGET_FILE" ] || [ "$TARGET_FILE" == "None" ] || [ ! -f "$TARGET_FILE" ]; then
    echo "⚠️ [WARNING] AI Agent ko koi valid game file nahi mili! Target File: $TARGET_FILE"
    exit 0
fi

GAME_POSTED_LOG="$POSTED_LINKS_DIR/${SELECTED_GAME_NAME}_posted_links_editor.txt"
echo "🎮 Selected Game: $SELECTED_GAME_NAME | Target File: $TARGET_FILE | Style: $SELECTED_STYLE"

# 4. Parse and Validate Link
echo "🔗 [STEP 4] Parsing and validating link from target file..."
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
    echo "⚠️ [WARNING] Is file me koi valid link nahi mila."
    exit 0
fi

echo "🔗 Validated Link Found: $SELECTED_URL"

# 5. ⏱️ Get Source Video Duration
echo "✂️ [STEP 5] Checking source video total duration via ffprobe..."
SOURCE_DURATION=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$SELECTED_URL" 2>/dev/null)
echo "⏱️ Raw ffprobe duration output: '$SOURCE_DURATION'"
SOURCE_DURATION=${SOURCE_DURATION%.*}

if [ -z "$SOURCE_DURATION" ] || [ "$SOURCE_DURATION" -le 0 ] 2>/dev/null; then
    echo "⚠️ [WARNING] ffprobe duration failed or returned 0. Defaulting source duration to 60s."
    SOURCE_DURATION=60
fi

# 6. 📸 Frame Extraction & 5x6 Grid Generation Across Full Video
rm -f "$FRAMES_DIR"/*.jpg
echo "📸 [STEP 6] Extracting 30 dynamic frames across source video..."

NUM_FRAMES=30
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
    ffmpeg -y -ss "$ts" -i "$SELECTED_URL" -vframes 1 -q:v 2 "$frame_path" -loglevel info
    if [ ! -f "$frame_path" ] || [ ! -s "$frame_path" ]; then
        ffmpeg -y -ss "00:00:01" -i "$SELECTED_URL" -vframes 1 -q:v 2 "$frame_path" -loglevel info
    fi
done

GRID_PATH="$FRAMES_DIR/merged_30_grid_screenshot.jpg"
echo "🧩 Merging frames into 5x6 vertical grid..."

TIMESTAMPS_STR="${timestamps[*]}" python3 - << 'EOF'
import os
import subprocess

frames_dir = 'temp_frames'
grid_path = os.path.join(frames_dir, 'merged_30_grid_screenshot.jpg')

try:
    from PIL import Image, ImageDraw
except ImportError:
    subprocess.run(["pip", "install", "Pillow"], check=True)
    from PIL import Image, ImageDraw

timestamps_env = os.environ.get('TIMESTAMPS_STR', '')
timestamps = timestamps_env.split()

for i in range(1, 31):
    frame_path = os.path.join(frames_dir, f'frame_{i}.jpg')
    ts = timestamps[i-1] if (i-1) < len(timestamps) else "00:00:00"
    if os.path.exists(frame_path) and os.path.getsize(frame_path) > 0:
        try:
            im = Image.open(frame_path).resize((432, 640))
            draw = ImageDraw.Draw(im)
            draw.rectangle([10, 10, 130, 50], fill=(0, 0, 0))
            draw.text((15, 18), ts, fill=(255, 255, 255))
            im.save(frame_path, 'JPEG', quality=85)
        except Exception as e:
            print(f"⚠️ Frame processing error at {i}: {e}")

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
print("✅ Grid screenshot created successfully.")
EOF

# 7. 🤖 Gemini Smart JSON Analysis
echo "🤖 [STEP 7] Sending grid & past insights to Gemini for Smart Action Cutting Decision..."

INSIGHTS_SUMMARY=$(python3 -c "
import os, json
memory_file = 'logs/agent_memory.json'
if os.path.exists(memory_file):
    try:
        with open(memory_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            print(f'Top Game Scores: {data.get(\"game_scores\", {})}, Styles: {data.get(\"title_styles\", {})}')
    except:
        print('No prior memory stats.')
else:
    print('Fresh run.')
")

if [ "$SELECTED_STYLE" == "aggressive" ]; then
    STYLE_PROMPT="Create a bold, intense, high-energy aggressive gaming hook title."
elif [ "$SELECTED_STYLE" == "question" ]; then
    STYLE_PROMPT="Create a curiosity-driven question hook title."
elif [ "$SELECTED_STYLE" == "emoji_heavy" ]; then
    STYLE_PROMPT="Create a fast-paced viral gaming title with strong emojis."
else
    STYLE_PROMPT="Create a high-curiosity viral Facebook/Instagram Reels hook title (6-10 words preferred)."
fi

GEMINI_JSON_RESULT=""
MAX_TOTAL_RETRIES=4

for ((attempt=1; attempt<=MAX_TOTAL_RETRIES; attempt++)); do
    CURRENT_GEMINI_KEY=$(get_random_gemini_key)
    echo "🤖 Gemini Attempt $attempt/$MAX_TOTAL_RETRIES (Key used: ${CURRENT_GEMINI_KEY:0,6}...)"
    
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
                    prompt_text="Analyze the provided 9:16 gaming screenshot grid. Total video source duration is $SOURCE_DURATION seconds.
Insights Context: $INSIGHTS_SUMMARY
Style Directive: $STYLE_PROMPT

Your primary job as an expert video editor is to find the most thrilling, high-action segment, skipping dull introductions.
Return a JSON object with EXACTLY three keys:
1. 'title' (string: viral title with 1-3 emojis)
2. 'start_time' (string format HH:MM:SS indicating exact peak action start time based on grid timestamps)
3. 'clip_duration' (integer: length between 12 and 45 seconds meeting monetization rules)
Return ONLY valid JSON format, no markdown wrapping."

                    payload=$(jq -n \
                      --arg uri "$file_uri" \
                      --arg mime "image/jpeg" \
                      --arg ptext "$prompt_text" \
                      '{contents: [{parts: [{file_data: {file_uri: $uri, mime_type: $mime}}, {text: $ptext}]}]}')

                    gemini_resp=$(curl -s -X POST -H "Content-Type: application/json" \
                      "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent?key=$CURRENT_GEMINI_KEY" \
                      -d "$payload")

                    GEMINI_JSON_RESULT=$(echo "$gemini_resp" | jq -r '.candidates[0].content.parts[0].text // empty')
                    echo "🤖 Gemini JSON Response: '$GEMINI_JSON_RESULT'"
                fi
            fi
        fi
    fi

    if [ -n "$GEMINI_JSON_RESULT" ] && [ "$GEMINI_JSON_RESULT" != "null" ]; then
        break
    else
        echo "⚠️ Gemini attempt $attempt failed. Retrying..."
        GEMINI_JSON_RESULT=""
        sleep 3
    fi
done

# Safe Python JSON Parser using Heredoc (Fixed Syntax Error)
PARSED_JSON_DATA=$(GEMINI_RAW="$GEMINI_JSON_RESULT" python3 - << 'EOF'
import json, re, sys, os

raw = os.environ.get('GEMINI_RAW', '')
cleaned = re.sub(r'```json', '', raw, flags=re.IGNORECASE)
cleaned = re.sub(r'```', '', cleaned).strip()

data = {}
try:
    match = re.search(r'\{.*?\}', cleaned, re.DOTALL)
    if match:
        data = json.loads(match.group(0))
    else:
        data = json.loads(cleaned)
except Exception as e:
    print(json.dumps({'status': 'failed', 'error': str(e), 'raw': raw}))
    sys.exit(0)

title = data.get('title')
start_time = data.get('start_time')
duration = data.get('clip_duration')

if not title or not start_time or not duration:
    print(json.dumps({'status': 'failed', 'error': 'Missing keys in JSON'}))
else:
    try:
        dur_int = int(duration)
        if dur_int < 12: dur_int = 12
        print(json.dumps({'status': 'success', 'title': title, 'start_time': start_time, 'duration': dur_int}))
    except:
        print(json.dumps({'status': 'failed', 'error': 'Invalid duration format'}))
EOF
)

PARSED_STATUS=$(echo "$PARSED_JSON_DATA" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', 'failed'))" 2>/dev/null)

if [ "$PARSED_STATUS" != "success" ]; then
    echo "❌ [ERROR] Gemini failed to return valid JSON decision! Full parsed output: $PARSED_JSON_DATA"
    exit 1
fi

AI_TITLE=$(echo "$PARSED_JSON_DATA" | python3 -c "import sys, json; print(json.load(sys.stdin).get('title', ''))" 2>/dev/null)
FINAL_START_TIME=$(echo "$PARSED_JSON_DATA" | python3 -c "import sys, json; print(json.load(sys.stdin).get('start_time', ''))" 2>/dev/null)
FINAL_CLIP_DURATION=$(echo "$PARSED_JSON_DATA" | python3 -c "import sys, json; print(json.load(sys.stdin).get('duration', 15))" 2>/dev/null)

echo "🎯 Strict Gemini Decisions Loaded Successfully:"
echo "   - Title: $AI_TITLE"
echo "   - Start Time: $FINAL_START_TIME"
echo "   - Clip Duration: $FINAL_CLIP_DURATION seconds"

CAPTION="$AI_TITLE

#videogames #gamingcommunity #gaming #${SELECTED_GAME_NAME,,} #gamingreels #reels"

# 8. ✂️ Actual Video Cutting via FFmpeg strictly using Gemini's Decision
FINAL_CLIP_PATH="$FRAMES_DIR/final_cut_clip.mp4"
echo "✂️ [STEP 8] Cutting thrilling clip via FFmpeg from $FINAL_START_TIME for $FINAL_CLIP_DURATION seconds..."
ffmpeg -y -ss "$FINAL_START_TIME" -i "$SELECTED_URL" -t "$FINAL_CLIP_DURATION" -c:v copy -c:a copy "$FINAL_CLIP_PATH" -loglevel info

if [ ! -f "$FINAL_CLIP_PATH" ] || [ ! -s "$FINAL_CLIP_PATH" ]; then
    echo "⚠️ Stream copy cut failed. Retrying re-encoding cut..."
    ffmpeg -y -ss "$FINAL_START_TIME" -i "$SELECTED_URL" -t "$FINAL_CLIP_DURATION" -c:v libx264 -preset veryfast -c:a aac "$FINAL_CLIP_PATH" -loglevel info
fi

if [ -f "$FINAL_CLIP_PATH" ] && [ -s "$FINAL_CLIP_PATH" ]; then
    echo "✅ Optimized action clip successfully saved at: $FINAL_CLIP_PATH"
else
    echo "❌ [ERROR] FFmpeg failed to cut the video clip based on Gemini's timing!"
    exit 1
fi

# ================= 5. 🚀 CRON-SAFE PLATFORM CONTROLLER =================
POST_MODE="$DEFAULT_POST_MODE"
echo "🚀 Using Posting Mode: $POST_MODE (1: Both, 2: Insta Only, 3: FB Only)"

PUBLISH_ID=""
FB_POST_ID=""

# --- A. Instagram Reels Upload via GitHub Release Asset ---
if [ "$POST_MODE" == "1" ] || [ "$POST_MODE" == "2" ]; then
    if [ -n "$PAGE_ACCESS_TOKEN" ] && [ -n "$IG_ID" ]; then
        echo "🚀 Uploading to Instagram Reels via GitHub Release Asset..."
        
        TAG_NAME="clip-release-$(date +%s)"
        REPO="${GITHUB_REPOSITORY}"
        TOKEN="${GITHUB_TOKEN:-$GH_PAT}"
        
        echo "🏷️ Creating temporary GitHub Release ($TAG_NAME)..."
        RELEASE_RES=$(curl -s -X POST "https://api.github.com/repos/$REPO/releases" \
          -H "Authorization: token $TOKEN" \
          -H "Content-Type: application/json" \
          -d "{
            \"tag_name\": \"$TAG_NAME\",
            \"name\": \"Temporary Clip Release\",
            \"draft\": false,
            \"prerelease\": true
          }")
          
        RELEASE_ID=$(echo "$RELEASE_RES" | python3 -c "import sys, json; print(json.load(sys.stdin).get('id', ''))" 2>/dev/null)
        
        if [ -n "$RELEASE_ID" ] && [ "$RELEASE_ID" != "None" ]; then
            echo "📦 Release created successfully (ID: $RELEASE_ID). Uploading video asset..."
            
            UPLOAD_URL="https://uploads.github.com/repos/$REPO/releases/$RELEASE_ID/assets?name=final_clip.mp4"
            ASSET_RES=$(curl -s -X POST "$UPLOAD_URL" \
              -H "Authorization: token $TOKEN" \
              -H "Content-Type: video/mp4" \
              --data-binary "@$FINAL_CLIP_PATH")
              
            PUBLIC_VIDEO_URL=$(echo "$ASSET_RES" | python3 -c "import sys, json; print(json.load(sys.stdin).get('browser_download_url', ''))" 2>/dev/null)
            
            if [ -n "$PUBLIC_VIDEO_URL" ] && [ "$PUBLIC_VIDEO_URL" != "None" ]; then
                echo "🔗 Generated Release Asset Public URL: $PUBLIC_VIDEO_URL"
                
                CONTAINER_RES=$(curl -s -X POST "$API/$IG_ID/media" \
                  --data-urlencode "media_type=REELS" \
                  --data-urlencode "video_url=$PUBLIC_VIDEO_URL" \
                  --data-urlencode "caption=$CAPTION" \
                  --data-urlencode "access_token=$PAGE_ACCESS_TOKEN")

                echo "📦 IG Container Response: $CONTAINER_RES"
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
                    
                    echo "📢 IG Publish Response: $PUBLISH_RES"
                    PUBLISH_ID=$(echo "$PUBLISH_RES" | python3 -c "import sys, json; print(json.load(sys.stdin).get('id', ''))" 2>/dev/null)
                    
                    if [ -n "$PUBLISH_ID" ] && [ "$PUBLISH_ID" != "None" ]; then
                        echo "🎉 Instagram Post Published Successfully! ID: $PUBLISH_ID"
                    else
                        echo "❌ Error: Failed to publish container to Instagram!"
                    fi
                fi
            else
                echo "❌ Error: Failed to upload video asset to GitHub release!"
                echo "Response: $ASSET_RES"
            fi
            
            echo "🗑️ Cleaning up temporary GitHub release and tag..."
            curl -s -X DELETE "https://api.github.com/repos/$REPO/releases/$RELEASE_ID" \
              -H "Authorization: token $TOKEN" > /dev/null
              
            curl -s -X DELETE "https://api.github.com/repos/$REPO/git/refs/tags/$TAG_NAME" \
              -H "Authorization: token $TOKEN" > /dev/null
            echo "✨ GitHub release and tag cleaned up successfully."
            
        else
            echo "❌ Error: Failed to create temporary GitHub Release!"
            echo "Response: $RELEASE_RES"
        fi
    fi
fi

# --- B. Facebook Page Video Upload ---
if [ "$POST_MODE" == "1" ] || [ "$POST_MODE" == "3" ]; then
    if [ -n "$PAGE_ACCESS_TOKEN" ] && [ -n "$PAGE_ID" ]; then
        echo "🚀 Uploading to Facebook Page..."
        FB_RES=$(curl -s -X POST "$API/$PAGE_ID/videos" \
          --data-urlencode "source=@$FINAL_CLIP_PATH" \
          --data-urlencode "description=$CAPTION" \
          --data-urlencode "access_token=$PAGE_ACCESS_TOKEN")

        echo "📦 FB Upload Response: $FB_RES"
        FB_POST_ID=$(echo "$FB_RES" | python3 -c "import sys, json; print(json.load(sys.stdin).get('id', ''))" 2>/dev/null)

        if [ -n "$FB_POST_ID" ] && [ "$FB_POST_ID" != "None" ]; then
            echo "🎉 Successfully Published to Facebook Page! Video ID: $FB_POST_ID"
        else
            echo "❌ Error: Failed to publish video to Facebook Page!"
        fi
    fi
fi

# 10. 🧠 Memory & Adaptive Feedback Update & File Cleanup
ACTIVE_ID="${PUBLISH_ID:-$FB_POST_ID}"
echo "📝 [STEP 10] Updating memory and file sync. Active ID: $ACTIVE_ID"

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
print('🧠 Agent Memory Updated Successfully!')
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
print('✅ Link successfully removed from temp file and shifted to posted folder!')
"
else
    echo "⚠️ [WARNING] Skipped file sync because no active post ID was generated."
fi

echo "===================================================="
echo "🏁 Pipeline Finished at: $(date)"
echo "===================================================="
