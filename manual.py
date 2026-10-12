#!/usr/bin/env python3
"""
🎮 AI GAMING AGENT v7 — Complete Final Script
====================================================
✅ Interactive prompt (Manual Link / Auto Pick)
✅ Title generation (OpenRouter + Gemini fallback)
✅ AI Commentary ON/OFF
✅ Clean filename (emoji-free)
✅ Log: "Title | Video Link" (unlimited)
✅ Auto mode: Success → used_links/
✅ Auto mode: Reject → rejected_links/
✅ NO Facebook
====================================================
"""

import os
import sys
import json
import re
import time
import base64
import random
import argparse
import subprocess
import requests
from datetime import datetime, timedelta, timezone
from PIL import Image, ImageDraw, ImageFont, ImageOps

# ============================================================
# 🇮🇳 IST TIME
# ============================================================
try:
    from zoneinfo import ZoneInfo
    IST = ZoneInfo("Asia/Kolkata")
except Exception:
    IST = timezone(timedelta(hours=5, minutes=30))

def now_ist():
    return datetime.now(IST)

def now_ist_ampm():
    return datetime.now(IST).strftime("%Y-%m-%d %I:%M:%S %p")

# ============================================================
# 🔑 API KEYS
# ============================================================
OPENROUTER_KEYS = [k for k in [
    os.environ.get("OPENROUTER_API_KEY"),
    os.environ.get("OPENROUTER_API_KEY_2"),
    os.environ.get("OPENROUTER_API_KEY_3"),
    os.environ.get("OPENROUTER_API_KEY_4"),
    os.environ.get("OPENROUTER_API_KEY_5"),
] if k]

GEMINI_KEYS = [k for k in [
    os.environ.get("GEMINI_API_KEY_1"),
    os.environ.get("GEMINI_API_KEY_2"),
    os.environ.get("GEMINI_API_KEY_3"),
    os.environ.get("GEMINI_API_KEY_4"),
    os.environ.get("GEMINI_API_KEY_5"),
    os.environ.get("GEMINI_API_KEY_6"),
] if k]

GROQ_KEYS = [k for k in [
    os.environ.get("GROQ_API_KEY"),
    os.environ.get("GROQ_API_KEY_2"),
    os.environ.get("GROQ_API_KEY_3"),
] if k]

ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")
VOICE_ID = os.environ.get("VOICE_ID", "91w4XjqhkWTX1Jr3O344")

# ============================================================
# 📁 PATHS
# ============================================================
LINKS_DIR = "game_links_editor"
USED_LINKS_DIR = "used_links"
REJECTED_LINKS_DIR = "rejected_links"
FRAMES_DIR = "temp_frames"
SEGMENTS_DIR = "segments"
ANALYSIS_DIR = "analysis"
LOGS_DIR = "logs"
FONTS_DIR = "fonts"
OUTPUT_DIR = "output"

GRID_PATH = f"{FRAMES_DIR}/merged_90_grid_portrait.jpg"
VIDEO_LOG = f"{LOGS_DIR}/video_log.json"
ROTATION_FILE = f"{LOGS_DIR}/rotation.json"

# ============================================================
# ⚙️ CONFIG
# ============================================================
NUM_FRAMES = 90
GRID_COLS = 10
GRID_ROWS = 9
CANVAS_W = 4320
CANVAS_H = 7680

MIN_CLIP_DURATION = 12
MAX_CLIP_DURATION = 60

COMMENTARY_ENABLED = os.environ.get("COMMENTARY_ENABLED", "true").lower() == "true"
SUBTITLES_ENABLED = os.environ.get("SUBTITLES_ENABLED", "true").lower() == "true"

# Commentary config
MIN_SLOTS_HARD = 6
MAX_SLOTS_HARD = 20
DUCK_VOLUME = 0.50
VOICE_SPEED_MIN = 1.00
VOICE_SPEED_MAX = 1.17
ATEMPO_MIN = 1.00
ATEMPO_MAX = 1.10
ATEMPO_MAX_LAST = 1.20
ATEMPO_MAX_ACTION = 1.15
MAX_SLOT_EXTEND = 0.2
SPEED_ACTION = 1.14
SPEED_DIALOG = 1.05
SPEED_CALM = 1.00
VOL_ACTION = 1.9
VOL_OTHER = 1.4

# ============================================================
# 🛠️ HELPERS
# ============================================================
def log(msg, also_print=True):
    sys.stderr.write(f"{msg}\n")
    sys.stderr.flush()
    if also_print:
        print(msg, flush=True)

def ensure_dirs():
    for d in [LINKS_DIR, USED_LINKS_DIR, REJECTED_LINKS_DIR, FRAMES_DIR,
              SEGMENTS_DIR, ANALYSIS_DIR, LOGS_DIR, FONTS_DIR, OUTPUT_DIR]:
        os.makedirs(d, exist_ok=True)

def get_duration(path):
    cmd = f'ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{path}"'
    try:
        out = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode().strip()
        return float(out) if out else 0.0
    except Exception:
        return 0.0

def seconds_to_srt_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def seconds_to_ass_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(((seconds - int(seconds)) * 100))
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def encode_image(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode('utf-8')

def extract_urls(text):
    urls = re.findall(r'https?://[^\s\)\]\'"<>,;]+', text)
    cleaned = []
    seen = set()
    for u in urls:
        u = u.rstrip('.,;)\']"')
        if u and u not in seen:
            seen.add(u)
            cleaned.append(u)
    return cleaned

def parse_srt(srt_content):
    entries = []
    for block in srt_content.strip().split("\n\n"):
        lines = block.split("\n")
        if len(lines) >= 3:
            tm = re.match(r"(\d+):(\d+):(\d+),(\d+) --> (\d+):(\d+):(\d+),(\d+)", lines[1])
            if tm:
                s = int(tm.group(1))*3600 + int(tm.group(2))*60 + int(tm.group(3)) + int(tm.group(4))/1000
                e = int(tm.group(5))*3600 + int(tm.group(6))*60 + int(tm.group(7)) + int(tm.group(8))/1000
                entries.append({"start": s, "end": e, "text": lines[2].strip()})
    return entries

def speed_for_type(slot_type):
    if slot_type == "action":
        return SPEED_ACTION
    elif slot_type == "dialog":
        return SPEED_DIALOG
    return SPEED_CALM

# ============================================================
# 📝 LOG — Sirf "Title | Video Link" (Unlimited)
# ============================================================
def save_video_log(title, edited_video_link):
    os.makedirs(LOGS_DIR, exist_ok=True)

    entries = []
    if os.path.exists(VIDEO_LOG):
        try:
            with open(VIDEO_LOG, 'r', encoding='utf-8') as f:
                entries = json.load(f)
                if not isinstance(entries, list):
                    entries = []
        except Exception:
            entries = []

    video_link = os.path.abspath(edited_video_link)
    line = f"{title} | {video_link}"

    entries.append(line)

    with open(VIDEO_LOG, 'w', encoding='utf-8') as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)

    log(f"📝 Log: {title}")
    log(f"   └─ {line}")
    log(f"   📊 Total: {len(entries)}")
    return line

# ============================================================
# 🔄 SIMPLE ROTATION
# ============================================================
def load_rotation():
    if os.path.exists(ROTATION_FILE):
        try:
            with open(ROTATION_FILE, 'r', encoding='utf-8') as f:
                return json.load(f).get("last_game", "")
        except Exception:
            pass
    return ""

def save_rotation(game_name):
    os.makedirs(LOGS_DIR, exist_ok=True)
    with open(ROTATION_FILE, 'w', encoding='utf-8') as f:
        json.dump({"last_game": game_name, "updated": now_ist_ampm()}, f, indent=2)

def get_all_games():
    if not os.path.exists(LINKS_DIR):
        return []
    games = []
    for f in os.listdir(LINKS_DIR):
        if f.endswith(".txt"):
            gname = (f.replace("_links_editor.txt", "")
                      .replace("_uploaded_links.txt", "")
                      .replace(".txt", "").strip())
            if gname:
                games.append({"game": gname, "file": os.path.join(LINKS_DIR, f)})
    return sorted(games, key=lambda x: x["game"])

def get_links_from_file(filepath):
    if not os.path.exists(filepath):
        return []
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    links = []
    for line in content.split('\n'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        urls = extract_urls(line)
        if urls:
            title = line.replace(urls[0], '').replace('| Link:', '').replace('|', '').strip()
            if not title:
                title = os.path.basename(urls[0]).split('?')[0] or "Video"
            links.append({"title": title, "url": urls[0], "raw": line})
    return links

def pick_next_game():
    games = get_all_games()
    if not games:
        return None
    last_game = load_rotation()
    game_names = [g["game"] for g in games]
    if last_game and last_game in game_names:
        idx = (game_names.index(last_game) + 1) % len(game_names)
    else:
        idx = 0
    for offset in range(len(games)):
        try_idx = (idx + offset) % len(games)
        picked = games[try_idx]
        links = get_links_from_file(picked["file"])
        if links:
            chosen = random.choice(links)
            return {
                "game": picked["game"],
                "file": picked["file"],
                "title": chosen["title"],
                "url": chosen["url"],
                "raw": chosen["raw"],
                "mode": "auto",
            }
    return None

def resolve_video_source(args):
    if args.link:
        url = args.link.strip()
        if url.startswith("http://") or url.startswith("https://"):
            return {
                "game": args.game or "Manual",
                "file": "",
                "title": args.title or os.path.basename(url).split('?')[0] or "Manual Video",
                "url": url,
                "raw": "",
                "mode": "manual_url",
            }
    log("🔄 Auto mode — picking from game_links_editor/...")
    return pick_next_game()

# ============================================================
# 📦 MOVE LINK TO USED FOLDER (Success)
# ============================================================
def move_link_to_used_folder(current_file, used_line, current_game):
    if not current_file or not os.path.exists(current_file):
        return False
    if not used_line:
        return False
    os.makedirs(USED_LINKS_DIR, exist_ok=True)

    try:
        with open(current_file, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        lines = content.split('\n')
        new_lines = []
        removed = False
        for line in lines:
            if line.strip() == used_line.strip() and not removed:
                removed = True
                continue
            new_lines.append(line)
        if not removed:
            return False
        while new_lines and not new_lines[-1].strip():
            new_lines.pop()
        with open(current_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(new_lines).rstrip() + '\n')
        log(f"   🗑️ Removed from: {os.path.basename(current_file)}")
    except Exception as e:
        log(f"   ⚠️ Remove error: {e}")
        return False

    try:
        safe_game = re.sub(r'[^\w\-]', '_', current_game)
        used_file = os.path.join(USED_LINKS_DIR, f"{safe_game}_used_links.txt")
        if os.path.exists(used_file):
            with open(used_file, 'r', encoding='utf-8', errors='ignore') as f:
                if used_line.strip() in f.read():
                    return True
        with open(used_file, 'a', encoding='utf-8') as f:
            f.write(f"\n{used_line.strip()}\n")
            f.write(f"# Used at: {now_ist_ampm()}\n")
        log(f"   📥 Moved to : {os.path.basename(used_file)}")
        return True
    except Exception as e:
        log(f"   ⚠️ Paste error: {e}")
        return False

# ============================================================
# 🚫 MOVE LINK TO REJECTED FOLDER (AI Reject)
# ============================================================
def move_link_to_rejected_folder(current_file, used_line, current_game, reason=""):
    if not current_file or not os.path.exists(current_file):
        return False
    if not used_line:
        return False
    os.makedirs(REJECTED_LINKS_DIR, exist_ok=True)

    try:
        with open(current_file, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        lines = content.split('\n')
        new_lines = []
        removed = False
        for line in lines:
            if line.strip() == used_line.strip() and not removed:
                removed = True
                continue
            new_lines.append(line)
        if not removed:
            log(f"   ⚠️ Line not found")
            return False
        while new_lines and not new_lines[-1].strip():
            new_lines.pop()
        with open(current_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(new_lines).rstrip() + '\n')
        log(f"   🗑️ Removed from: {os.path.basename(current_file)}")
    except Exception as e:
        log(f"   ⚠️ Remove error: {e}")
        return False

    try:
        safe_game = re.sub(r'[^\w\-]', '_', current_game)
        rejected_file = os.path.join(REJECTED_LINKS_DIR, f"{safe_game}_rejected_links.txt")
        if os.path.exists(rejected_file):
            with open(rejected_file, 'r', encoding='utf-8', errors='ignore') as f:
                if used_line.strip() in f.read():
                    return True
        with open(rejected_file, 'a', encoding='utf-8') as f:
            f.write(f"\n{used_line.strip()}\n")
            f.write(f"# REJECTED at: {now_ist_ampm()}\n")
            if reason:
                f.write(f"# Reason: {reason}\n")
        log(f"   📥 Moved to : {os.path.basename(rejected_file)}")
        log(f"   📁 Folder   : {REJECTED_LINKS_DIR}/")
        if reason:
            log(f"   📝 Reason   : {reason[:80]}")
        return True
    except Exception as e:
        log(f"   ⚠️ Paste error: {e}")
        return False

# ============================================================
# 🎯 INTERACTIVE PROMPT (2 Options)
# ============================================================
def ask_user_choice():
    print()
    print("=" * 60)
    print("🎬 AI VIDEO EDITOR v7")
    print("=" * 60)
    print()
    print("📥 Video source kya chahiye?")
    print()
    print("   1. 🔗 Manual Link  (URL daalna hai)")
    print("   2. 🎲 Auto Pick    (game_links_editor/ se)")
    print()

    while True:
        try:
            choice = input("Select option (1/2): ").strip()
            if choice in ("1", "2"):
                break
            print("   ⚠️ Invalid — 1 ya 2 daalo")
        except (KeyboardInterrupt, EOFError):
            print("\n❌ Cancelled")
            sys.exit(0)

    result = {"mode": choice, "value": "", "game": "", "title": ""}

    if choice == "1":
        while True:
            url = input("🔗 URL daalo: ").strip()
            if url.startswith("http://") or url.startswith("https://"):
                result["value"] = url
                break
            print("   ⚠️ URL 'http://' ya 'https://' se start hona chahiye")

        game = input("🎮 Game name (optional, Enter = skip): ").strip()
        result["game"] = game

        title = input("📝 Custom title (optional, Enter = AI banayega): ").strip()
        result["title"] = title

    elif choice == "2":
        games = get_all_games()
        if not games:
            print("❌ game_links_editor/ folder me koi game file nahi mili")
            print("   Pehle links daalo, phir chalao")
            sys.exit(1)
        print(f"✅ {len(games)} games mili — auto pick kar raha hu...")

    return result

# ============================================================
# 🎯 TITLE GENERATION
# ============================================================
def build_title_prompt(game_name, source_duration, style):
    return f"""You are an expert gaming video editor. Analyze the 9:16 gaming screenshot grid.

VIDEO INFO:
- Game: {game_name}
- Total Duration: {source_duration} seconds
- Style Directive: {style}

YOUR TASK: Decide APPROVE or REJECT for this video.

REJECT IF:
- Only menus, maps, inventory, shopping, loading screens
- No actual gameplay or action visible
- Frames look identical, frozen, or boring
- Zero pacing, stagnant motion, filler content
- Fake tension (dramatic lighting but no action)

APPROVE IF:
- Real gameplay with clear engaging moment (combat, boss fight, explosion, clutch)
- High retention value, adrenaline, emotion, comedy
- Cinematic sequence that's genuinely gripping

TITLE RULES (APPROVE only):
- Under 6-10 words, 1-2 emojis
- No commas, periods, dots, punctuation
- BANNED EMOJIS: 💀 ☠️ 👹 🩸
- BANNED WORDS: Epic Insane Crazy Best Battle Clash Escape Warrior Beast Mission Wait For The End You Won't Believe Watch Till End This Changed Everything No Escape Fierce Clash Tactical Mission Sniper Headshot Clutch Save

5 THINGS FOR VIRAL TITLE:
1. SPECIFIC - real thing (Knife vs Sniper, Diamond, Boss)
2. SUSPENSE - curiosity with dots
3. HYPE - strong verb (cooked, wrecked, clutched)
4. NUMBER - 1 HP, 4 Enemies, 100 Days
5. EMOTION - Last Bullet, Betrayal, Crash

Every title needs at least 3 of these.

GOOD EXAMPLES:
- 1 HP 4 Enemies Left 🔥🎯
- Knife vs Sniper He Won 🔪🎯
- Last Bullet Saved His Team 🔫🔥
- Tank Walked Into 5 Players 💥😳

STRICT JSON OUTPUT:
If REJECT: {{"status": "REJECT", "reason": "<max 10 words>"}}
If APPROVE: {{"status": "APPROVE", "title": "<6-10 words with emojis>", "start_time": <int seconds>, "clip_duration": <int seconds min 12 max {min(source_duration, MAX_CLIP_DURATION)}>, "reason": "<max 10 words>"}}

STRICT: start_time + clip_duration must not exceed {source_duration}. Capture FULL action sequence. Return ONLY raw JSON."""

def call_openrouter(prompt, image_b64, max_tokens=800, timeout=120):
    if not OPENROUTER_KEYS:
        return None
    url = "https://openrouter.ai/api/v1/chat/completions"
    models = ["openai/gpt-4o-mini", "openrouter/free"]
    for attempt in range(6):
        key = random.choice(OPENROUTER_KEYS)
        model = models[0] if attempt < 2 else models[1]
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/",
            "X-Title": "Gaming AI Agent v7",
        }
        payload = {
            "model": model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
                ]
            }],
            "max_tokens": max_tokens,
            "temperature": 0.7,
            "response_format": {"type": "json_object"},
        }
        try:
            log(f"   🔑 OpenRouter attempt {attempt+1}/6 | model={model}")
            r = requests.post(url, headers=headers, json=payload, timeout=timeout)
            if r.status_code == 200:
                data = r.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                if content:
                    log(f"   ✅ Got response ({len(content)} chars)")
                    return content.strip()
            else:
                log(f"   ⚠️ HTTP {r.status_code}: {r.text[:120]}")
        except Exception as e:
            log(f"   ⚠️ Exception: {e}")
        time.sleep(1.5)
    return None

def call_gemini(prompt, image_b64, max_tokens=800):
    if not GEMINI_KEYS:
        return None
    for attempt in range(6):
        key = random.choice(GEMINI_KEYS)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={key}"
        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": "image/jpeg", "data": image_b64}}
                ]
            }],
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": 0.7,
                "responseMimeType": "application/json",
            }
        }
        try:
            log(f"   🔑 Gemini attempt {attempt+1}/6")
            r = requests.post(url, json=payload, timeout=90)
            if r.status_code == 200:
                data = r.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        content = parts[0].get("text", "")
                        if content:
                            log(f"   ✅ Gemini response ({len(content)} chars)")
                            return content.strip()
            else:
                log(f"   ⚠️ Gemini HTTP {r.status_code}: {r.text[:120]}")
        except Exception as e:
            log(f"   ⚠️ Gemini exception: {e}")
        time.sleep(1.5)
    return None

def extract_json(text):
    if not text:
        return None
    clean = re.sub(r"```json\s*|\s*```", "", text, flags=re.IGNORECASE).strip()
    clean = re.sub(r"<think>.*?</think>", "", clean, flags=re.DOTALL).strip()
    try:
        d = json.loads(clean)
        if isinstance(d, dict):
            return d
    except Exception:
        pass
    match = re.search(r"\{.*\}", clean, re.DOTALL)
    if match:
        try:
            d = json.loads(match.group(0))
            if isinstance(d, dict):
                return d
        except Exception:
            pass
    return None

def generate_title(game_name, source_duration, style, grid_path):
    log("🤖 Generating title...")
    image_b64 = encode_image(grid_path)
    prompt = build_title_prompt(game_name, source_duration, style)

    response = call_openrouter(prompt, image_b64)
    if not response:
        log("   ⚠️ OpenRouter failed — trying Gemini...")
        response = call_gemini(prompt, image_b64)

    if not response:
        log("❌ Both failed — fallback")
        return {
            "status": "success",
            "title": f"{game_name} Gameplay Highlights 🔥",
            "start_time": 0,
            "duration": min(30, int(source_duration)),
            "reason": "Fallback",
        }

    data = extract_json(response)
    if not data:
        return {
            "status": "success",
            "title": f"{game_name} Gameplay 🔥",
            "start_time": 0,
            "duration": min(30, int(source_duration)),
            "reason": "JSON parse failed",
        }

    status = str(data.get("status", "")).upper()
    if status == "REJECT":
        return {"status": "reject", "reason": data.get("reason", "Rejected")}

    if status == "APPROVE":
        title = str(data.get("title", "")).strip()
        title = re.sub(r'[\*\#\`\"]', '', title).strip()
        try:
            start_time = int(data.get("start_time", 0))
        except Exception:
            start_time = 0
        try:
            duration = int(data.get("clip_duration", 15))
        except Exception:
            duration = 15

        if duration < MIN_CLIP_DURATION:
            duration = MIN_CLIP_DURATION
        if duration > source_duration:
            duration = int(source_duration)
        if duration > MAX_CLIP_DURATION:
            duration = MAX_CLIP_DURATION
        if start_time + duration > source_duration:
            start_time = max(0, int(source_duration) - duration)

        return {
            "status": "success",
            "title": title or f"{game_name} Epic Moment 🔥",
            "start_time": start_time,
            "duration": duration,
            "reason": data.get("reason", ""),
        }

    return {
        "status": "success",
        "title": f"{game_name} Gameplay 🔥",
        "start_time": 0,
        "duration": min(30, int(source_duration)),
        "reason": "Unknown status",
    }

# ============================================================
# 📸 FRAMES + GRID
# ============================================================
def extract_frames(video_path, num_frames=NUM_FRAMES):
    log(f"📸 Extracting {num_frames} frames...")
    os.makedirs(FRAMES_DIR, exist_ok=True)
    for f in os.listdir(FRAMES_DIR):
        if f.startswith("frame_") and f.endswith(".jpg"):
            try:
                os.remove(os.path.join(FRAMES_DIR, f))
            except Exception:
                pass

    duration = get_duration(video_path)
    if duration <= 0:
        duration = 60.0

    timestamps = [i * (duration / num_frames) for i in range(num_frames)]
    success = 0
    for i, ts in enumerate(timestamps, 1):
        fp = f"{FRAMES_DIR}/frame_{i}.jpg"
        subprocess.run(
            f'ffmpeg -y -ss {ts:.3f} -i "{video_path}" -frames:v 1 -q:v 2 "{fp}"',
            shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        if os.path.exists(fp) and os.path.getsize(fp) > 0:
            success += 1
    log(f"✅ Extracted {success}/{num_frames} frames")
    return timestamps

def build_grid(timestamps):
    log("🧩 Building 8K portrait grid...")
    cell_w = CANVAS_W // GRID_COLS
    cell_h = CANVAS_H // GRID_ROWS

    grid = Image.new("RGB", (CANVAS_W, CANVAS_H), (0, 0, 0))
    draw = ImageDraw.Draw(grid)

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48)
    except Exception:
        try:
            font = ImageFont.truetype("/system/fonts/Roboto-Bold.ttf", 48)
        except Exception:
            font = ImageFont.load_default()

    for i in range(1, NUM_FRAMES + 1):
        fp = f"{FRAMES_DIR}/frame_{i}.jpg"
        try:
            im = Image.open(fp)
            im = ImageOps.fit(im, (cell_w, cell_h), method=Image.LANCZOS)
        except Exception:
            im = Image.new('RGB', (cell_w, cell_h), (0, 0, 0))

        col = (i - 1) % GRID_COLS
        row = (i - 1) // GRID_COLS
        x = col * cell_w
        y = row * cell_h
        grid.paste(im, (x, y))

        ts = timestamps[i-1] if (i-1) < len(timestamps) else 0
        m = int(ts // 60)
        s = int(ts % 60)
        label = f"F{i} {m:02d}:{s:02d}"
        draw.rectangle([x + 10, y + 10, x + 260, y + 80], fill="black")
        draw.text((x + 20, y + 20), label, fill="yellow", font=font)

    grid.save(GRID_PATH, 'JPEG', quality=92, optimize=True)
    size_mb = os.path.getsize(GRID_PATH) / (1024 * 1024)
    log(f"✅ Grid: {GRID_PATH} ({size_mb:.2f} MB)")
    return GRID_PATH

# ============================================================
# ✂️ CUT CLIP
# ============================================================
def cut_clip(video_path, start_time, duration, output_path):
    log(f"✂️ Cutting: start={start_time}s, dur={duration}s")
    cmd = f'ffmpeg -y -ss {start_time} -i "{video_path}" -t {duration} -c:v copy -c:a copy "{output_path}" -loglevel error'
    subprocess.run(cmd, shell=True)
    if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        log("   ⚠️ Copy failed — re-encoding...")
        cmd = f'ffmpeg -y -ss {start_time} -i "{video_path}" -t {duration} -c:v libx264 -preset veryfast -c:a aac "{output_path}" -loglevel error'
        subprocess.run(cmd, shell=True)
    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        log(f"✅ Clip: {output_path}")
        return True
    return False

# ============================================================
# 🎙️ COMMENTARY
# ============================================================
def extract_audio(video_path, out_path):
    log("🎧 Extracting audio...")
    subprocess.run(
        f'ffmpeg -y -i "{video_path}" -vn -acodec libmp3lame -q:a 4 "{out_path}" -loglevel error',
        shell=True
    )

def transcribe(audio_path, srt_path):
    log(f"📝 Transcribing ({len(GROQ_KEYS)} Groq keys)...")
    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    srt_content = ""
    for idx, key in enumerate(GROQ_KEYS, 1):
        try:
            with open(audio_path, "rb") as f:
                files = {"file": (audio_path, f, "audio/mp3")}
                data = {"model": "whisper-large-v3", "response_format": "verbose_json"}
                headers = {"Authorization": f"Bearer {key}"}
                r = requests.post(url, headers=headers, files=files, data=data, timeout=120)
            if r.status_code == 200:
                res = r.json()
                for i, seg in enumerate(res.get("segments", []), 1):
                    srt_content += (
                        f"{i}\n"
                        f"{seconds_to_srt_time(seg.get('start', 0))} --> "
                        f"{seconds_to_srt_time(seg.get('end', 0))}\n"
                        f"{seg.get('text', '').strip()}\n\n"
                    )
                with open(srt_path, "w", encoding="utf-8") as sf:
                    sf.write(srt_content)
                log(f"   ✅ Groq key {idx}")
                return srt_content
            elif r.status_code in (401, 403):
                continue
            elif r.status_code == 429:
                time.sleep(2)
                continue
        except Exception as e:
            log(f"   ⚠️ Key {idx}: {e}")
            time.sleep(1)
    return ""

def get_scene_timeline(video_path):
    cmd = f'ffmpeg -i "{video_path}" -filter:v "select=\'gt(scene,0.3)\',showinfo" -f null - 2>&1'
    out = subprocess.run(cmd, shell=True, capture_output=True, text=True).stderr
    return [float(m.group(1)) for m in re.finditer(r"pts_time:([\d.]+)", out)]

def get_loudness_timeline(video_path):
    cmd = (
        f'ffmpeg -i "{video_path}" -af "astats=metadata=1:reset=1,'
        f'ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-" '
        f'-f null - 2>&1'
    )
    out = subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout
    timeline = []
    t = 0.0
    for line in out.split("\n"):
        m = re.search(r"RMS_level=(-?[\d.]+|inf)", line)
        if m and m.group(1) != "-inf":
            try:
                timeline.append((t, float(m.group(1))))
            except Exception:
                pass
            t += 0.1
    return timeline

def slot_loudness(timeline, start, end):
    vals = [v for t, v in timeline if start <= t < end]
    return max(vals) if vals else -60

def get_motion_score(video_path, start, end):
    try:
        duration = max(end - start, 0.5)
        cmd = (
            f'ffmpeg -ss {start:.2f} -t {duration:.2f} -i "{video_path}" '
            f'-vf "select=\'gt(scene,0.1)\',metadata=print" '
            f'-f null - 2>&1'
        )
        out = subprocess.run(cmd, shell=True, capture_output=True, text=True).stderr
        return len(re.findall(r"pts_time", out))
    except Exception:
        return 0

def build_slots(video_path, vid_duration, srt_content):
    log("📐 Building slots...")
    srt_entries = parse_srt(srt_content)
    srt_boundaries = set()
    for e in srt_entries:
        srt_boundaries.add(round(e["start"], 2))
        srt_boundaries.add(round(e["end"], 2))

    total_speech = sum(e["end"] - e["start"] for e in srt_entries)
    speech_ratio = total_speech / max(vid_duration, 1)

    scene_times = get_scene_timeline(video_path)
    scene_boundaries = set(round(t, 2) for t in scene_times)

    loud_timeline = get_loudness_timeline(video_path)
    audio_peaks = set()
    if len(loud_timeline) > 5:
        vals = [v for _, v in loud_timeline]
        threshold = sorted(vals)[int(len(vals) * 0.8)]
        for t, v in loud_timeline:
            if v >= threshold and v > -20:
                audio_peaks.add(round(t, 2))

    if vid_duration <= 20:
        base = 2.5
    elif vid_duration <= 40:
        base = 3.0
    elif vid_duration <= 70:
        base = 3.5
    elif vid_duration <= 120:
        base = 4.5
    else:
        base = 5.5

    if speech_ratio > 0.7:
        base *= 0.85
    elif speech_ratio < 0.25:
        base *= 1.15

    cuts_per_sec = len(scene_times) / max(vid_duration, 1)
    if cuts_per_sec > 0.5:
        base *= 0.85
    elif cuts_per_sec < 0.12:
        base *= 1.1

    slot_sec = base
    total = int(round(vid_duration / slot_sec))
    total = max(MIN_SLOTS_HARD, min(MAX_SLOTS_HARD, total))
    slot_sec = vid_duration / total

    all_boundaries = sorted(srt_boundaries | scene_boundaries | audio_peaks)
    all_boundaries = [b for b in all_boundaries if 0.5 < b < vid_duration - 0.5]

    slots = []
    t = 0.0
    used = set()
    for i in range(total):
        if i == total - 1:
            target_end = vid_duration
        else:
            target_end = t + slot_sec
        candidates = [b for b in all_boundaries if b not in used and t + 1.5 < b < target_end + 1.0]
        if candidates and i < total - 1:
            srt_cands = [b for b in candidates if b in srt_boundaries]
            scene_cands = [b for b in candidates if b in scene_boundaries]
            if srt_cands:
                snap = min(srt_cands, key=lambda x: abs(x - target_end))
            elif scene_cands:
                snap = min(scene_cands, key=lambda x: abs(x - target_end))
            else:
                snap = min(candidates, key=lambda x: abs(x - target_end))
            end = snap if abs(snap - target_end) < 1.0 else target_end
            used.add(snap)
        else:
            end = target_end
        end = min(end, vid_duration)
        end = max(end, t + 1.5)

        slot_text = " ".join(e["text"] for e in srt_entries if e["start"] >= t and e["end"] <= end).strip()
        slots.append({
            "start": round(t, 2), "end": round(end, 2),
            "type": None, "srt_text": slot_text,
            "scene_count": 0, "avg_loud": -50,
            "sub_analysis": {}, "voice_speed": 1.0,
            "motion_score": 0, "speed_boost_log": []
        })
        t = end
        if t >= vid_duration - 0.1:
            break

    if slots and slots[-1]["end"] < vid_duration - 0.1:
        slots[-1]["end"] = round(vid_duration, 2)

    log(f"   ✅ {len(slots)} slots")
    return slots

def classify_slots(video_path, slots, srt_content):
    log("🔍 Classifying slots...")
    scene_times = get_scene_timeline(video_path)
    loud_timeline = get_loudness_timeline(video_path)
    srt_entries = parse_srt(srt_content)

    ACTION_WORDS = {"shoot","fire","hit","run","kill","die","attack","grenade","boom",
                    "jump","dodge","cover","reload","go","move","watch","left","right",
                    "down","up","quick","destroy","target","lock","bang","drop","danger",
                    "whoa","oh","yeah","nice","sick","cook","big","fast"}
    DIALOG_WORDS = {"you","me","we","what","why","how","hey","listen","wait","okay",
                    "yeah","know","think","feel","want","need","can","will"}

    for slot in slots:
        motion = get_motion_score(video_path, slot["start"], slot["end"])
        slot["motion_score"] = motion

        sub_windows = []
        t = slot["start"]
        while t < slot["end"]:
            sub_windows.append({"start": t, "end": min(t + 0.5, slot["end"])})
            t += 0.5

        action_count = dialog_count = calm_count = 0
        for sw in sub_windows:
            scene_cuts = sum(1 for st in scene_times if sw["start"] <= st < sw["end"])
            loud = slot_loudness(loud_timeline, sw["start"], sw["end"])
            sw_text = " ".join(e["text"] for e in srt_entries if e["start"] >= sw["start"] and e["end"] <= sw["end"]).lower()
            words = set(sw_text.split())
            has_action_word = len(words & ACTION_WORDS) >= 1
            has_dialog_word = len(words & DIALOG_WORDS) >= 1
            has_speech = len(sw_text.strip()) > 3

            if has_action_word and scene_cuts >= 1:
                action_count += 1
            elif has_action_word:
                action_count += 1
            elif scene_cuts >= 2:
                action_count += 1
            elif loud > -15:
                action_count += 1
            elif has_speech and has_dialog_word:
                dialog_count += 1
            elif has_speech:
                dialog_count += 1
            else:
                calm_count += 1

        total = max(len(sub_windows), 1)
        action_ratio = action_count / total
        dialog_ratio = dialog_count / total
        calm_ratio = calm_count / total

        if motion >= 5:
            action_ratio = min(1.0, action_ratio + 0.40)
        elif motion >= 3:
            action_ratio = min(1.0, action_ratio + 0.25)
        elif motion >= 2:
            action_ratio = min(1.0, action_ratio + 0.15)

        if motion >= 3:
            calm_ratio = max(0.0, calm_ratio - 0.30)

        if action_ratio >= 0.30 or motion >= 5:
            slot["type"] = "action"
        elif dialog_ratio >= 0.40:
            slot["type"] = "dialog"
        elif calm_ratio >= 0.50 and motion < 2:
            slot["type"] = "calm"
        elif action_ratio >= 0.20 or motion >= 3:
            slot["type"] = "action"
        elif dialog_ratio >= 0.20:
            slot["type"] = "dialog"
        else:
            slot["type"] = "calm"

        slot["scene_count"] = sum(1 for st in scene_times if slot["start"] <= st < slot["end"])
        slot["avg_loud"] = round(slot_loudness(loud_timeline, slot["start"], slot["end"]), 1)
        slot["sub_analysis"] = {
            "action_ratio": round(action_ratio, 2),
            "dialog_ratio": round(dialog_ratio, 2),
            "calm_ratio": round(calm_ratio, 2),
            "total_subs": total, "motion_score": motion
        }

        voice_speed = speed_for_type(slot["type"])
        slot["speed_boost_log"] = [f"base_{slot['type']}={voice_speed:.2f}"]
        if slot["type"] == "action":
            if slot["scene_count"] >= 3:
                voice_speed += 0.03
            if slot["avg_loud"] > -12:
                voice_speed += 0.03
            if motion >= 5:
                voice_speed += 0.02

        slot["voice_speed"] = round(max(VOICE_SPEED_MIN, min(VOICE_SPEED_MAX, voice_speed)), 2)

    log(f"   ✅ {len(slots)} slots classified")
    return slots

def generate_commentary_script(slots, srt_content, grid_path):
    log(f"🤖 Generating commentary ({len(OPENROUTER_KEYS)} keys)...")
    slot_lines = []
    for i, s in enumerate(slots, 1):
        sa = s.get("sub_analysis", {})
        slot_lines.append(
            f"- Slot {i}: {s['start']:.2f}s → {s['end']:.2f}s [{s['type'].upper()}] "
            f"(scenes={s['scene_count']}, loud={s['avg_loud']}dB, "
            f"action={sa.get('action_ratio',0)}, motion={sa.get('motion_score',0)}) "
            f"SRT: \"{s['srt_text'][:70]}\""
        )

    prompt = f"""You are a HYPED-UP gaming YouTuber. React LIVE like a streamer.

RULES:
- Contractions: "he's", "gonna", "wanna"
- Slang: "bruh", "yo", "bro", "nah", "lowkey", "bet"
- Short sentences. Fragments OK.
- ACTION → shout, hype, CAPS
- DIALOG → conversational, NO shouting
- CALM → chill, relaxed, NO hype
- NEVER shout on non-action scenes
- 5-8 words per line
- Address "guys" or "you" naturally

SLOTS (fill ALL {len(slots)}):
{chr(10).join(slot_lines)}

Return ONLY valid JSON:
{{
  "segments": [
    {{"slot": 1, "start": 0.0, "end": 3.5, "text": "...", "visual_type": "calm"}}
  ]
}}"""

    image_b64 = encode_image(grid_path)
    response = call_openrouter(prompt, image_b64, max_tokens=4000, timeout=180)

    if not response:
        log("   ⚠️ Using fallback")
        fallback = {
            "action": ["Ohh things are heating up!", "He's in the middle of it!", "Chaos everywhere!"],
            "dialog": ["Wait what did he say?", "Hmm interesting...", "What's the plan here?"],
            "calm": ["Just vibing here.", "Too quiet... sus.", "Chill vibes here..."]
        }
        return [{"slot": i+1, "start": s["start"], "end": s["end"],
                 "text": fallback[s["type"]][i % 3], "visual_type": s["type"]}
                for i, s in enumerate(slots)]

    data = extract_json(response)
    segments = data.get("segments", []) if data else []

    if not segments:
        fallback = {
            "action": ["Ohh things are heating up!", "He's in the middle of it!"],
            "dialog": ["Wait what did he say?", "Hmm interesting..."],
            "calm": ["Just vibing here.", "Chill vibes..."]
        }
        return [{"slot": i+1, "start": s["start"], "end": s["end"],
                 "text": fallback[s["type"]][i % 2], "visual_type": s["type"]}
                for i, s in enumerate(slots)]

    for seg in segments:
        slot_num = seg.get("slot")
        if slot_num and 1 <= slot_num <= len(slots):
            exact = slots[slot_num - 1]
            seg["start"] = exact["start"]
            seg["end"] = exact["end"]

    log(f"   ✅ {len(segments)} segments")
    return segments

def generate_tts(segments, slots, vid_duration):
    log(f"🔊 Generating TTS...")
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": ELEVENLABS_API_KEY
    }

    audio_files = []
    for idx, seg in enumerate(segments):
        text = seg.get("text", "").strip()
        if not text:
            continue
        slot_num = seg.get("slot")
        matched = None
        if slot_num and 1 <= slot_num <= len(slots):
            matched = slots[slot_num - 1]
        else:
            best_diff = 999
            for s in slots:
                diff = abs(s["start"] - seg.get("start", 0))
                if diff < best_diff:
                    best_diff = diff
                    matched = s

        if not matched:
            continue

        slot_start = matched["start"]
        slot_end = matched["end"]
        target_dur = slot_end - slot_start
        voice_speed = max(VOICE_SPEED_MIN, min(VOICE_SPEED_MAX, matched.get("voice_speed", 1.0)))
        visual_type = (matched.get("type") or "calm").lower()

        seg_file = f"{SEGMENTS_DIR}/seg_{idx:03d}.mp3"
        data = {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.4, "similarity_boost": 0.75,
                "style": 0.5, "use_speaker_boost": True,
                "speed": voice_speed
            }
        }

        try:
            r = requests.post(url, json=data, headers=headers, timeout=60)
            if r.status_code == 200:
                with open(seg_file, "wb") as af:
                    af.write(r.content)
                actual = get_duration(seg_file)
                atempo_used = "none"
                slot_extended = 0.0
                is_last = (idx == len(segments) - 1)
                atempo_max = ATEMPO_MAX_LAST if is_last else ATEMPO_MAX

                if visual_type == "action" and not is_last:
                    if actual > target_dur + 0.05:
                        needed = actual / target_dur
                        tempo = max(ATEMPO_MIN, min(ATEMPO_MAX_ACTION, needed))
                        if tempo > 1.01:
                            fit = f"{SEGMENTS_DIR}/seg_{idx:03d}_fit.mp3"
                            subprocess.run(
                                f'ffmpeg -y -i "{seg_file}" -filter:a atempo={tempo:.3f} "{fit}"',
                                shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                            )
                            final = fit if os.path.exists(fit) else seg_file
                            atempo_used = f"{tempo:.3f} (action)"
                        else:
                            final = seg_file
                    else:
                        final = seg_file
                else:
                    if actual > 0 and target_dur > 0:
                        needed = actual / target_dur
                        tempo = max(ATEMPO_MIN, min(atempo_max, needed))
                        if tempo > 1.01:
                            fit = f"{SEGMENTS_DIR}/seg_{idx:03d}_fit.mp3"
                            subprocess.run(
                                f'ffmpeg -y -i "{seg_file}" -filter:a atempo={tempo:.3f} "{fit}"',
                                shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                            )
                            final = fit if os.path.exists(fit) else seg_file
                            atempo_used = f"{tempo:.3f}" + (" (last)" if is_last else "")
                        else:
                            final = seg_file
                    else:
                        final = seg_file

                actual_end = slot_start + get_duration(final)
                audio_files.append({
                    "file": final, "start": slot_start, "end": slot_end + slot_extended,
                    "actual_end": actual_end, "text": text,
                    "visual_type": visual_type, "slot_extended": slot_extended
                })
                log(f"   [{visual_type.upper()}] {slot_start:.2f}-{slot_end:.2f}s | audio={actual:.2f}s | atempo={atempo_used}")
            elif r.status_code == 401:
                log("   ❌ ElevenLabs 401")
                break
            elif r.status_code == 429:
                time.sleep(3)
        except Exception as e:
            log(f"   ⚠️ seg {idx}: {e}")

    log(f"✅ {len(audio_files)} audio segments")
    return audio_files

def build_timed_audio(audio_files, vid_duration):
    log("🎼 Building timed audio...")
    silent = f"{SEGMENTS_DIR}/silent_base.mp3"
    subprocess.run(
        f'ffmpeg -y -f lavfi -i anullsrc=r=44100:cl=stereo -t {vid_duration} '
        f'-q:a 9 -acodec libmp3lame "{silent}" -loglevel error',
        shell=True
    )
    inputs = ["-i", silent]
    parts = []
    mix_inputs = ["[0:a]"]
    for i, a in enumerate(audio_files, 1):
        inputs.extend(["-i", a["file"]])
        delay = int(a["start"] * 1000)
        parts.append(f"[{i}:a]adelay={delay}|{delay}[a{i}]")
        mix_inputs.append(f"[a{i}]")
    filter_complex = (
        ";".join(parts) +
        f";{''.join(mix_inputs)}amix=inputs={len(mix_inputs)}:"
        f"duration=first:dropout_transition=0:normalize=0,"
        f"alimiter=limit=0.95[out]"
    )
    final_audio = f"{SEGMENTS_DIR}/final_commentary.mp3"
    cmd = (
        f'ffmpeg -y {" ".join(inputs)} -filter_complex "{filter_complex}" '
        f'-map "[out]" -acodec libmp3lame -q:a 4 "{final_audio}" -loglevel error'
    )
    subprocess.run(cmd, shell=True)
    log("✅ Timed audio")
    return final_audio

def generate_ass_subtitles(audio_files, ass_path):
    log("🎨 Generating ASS subtitles...")
    ass_content = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,60,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,3,2,2,10,10,40,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    written = 0
    CW = "&H00FFFFFF"
    CY = "&H0000FFFF"
    CB = "&H00FF0000"
    CR = "&H00FFFFFF"

    def get_color(i, total):
        if i == total - 1:
            return CB
        return CW if i % 2 == 0 else CY

    for item in audio_files:
        start = item.get("start", 0)
        end = item.get("actual_end", item.get("end", 3))
        text = item.get("text", "").strip()
        if not text:
            continue
        words = text.split()
        if not words:
            continue
        total_dur = end - start
        if total_dur <= 0:
            total_dur = 1.0
        total_chars = sum(len(w) for w in words) or 1
        total_words = len(words)
        current = start
        cumulative = 0
        for i, w in enumerate(words):
            cumulative += len(w)
            frac = cumulative / total_chars
            seg_end = start + (total_dur * frac)
            visible = words[:i+1]
            colored = []
            for j, vw in enumerate(visible):
                color = get_color(j, total_words)
                colored.append(f"{{\\c{color}}}{vw}{{\\c{CR}}}")
            colored_text = " ".join(colored)
            start_t = seconds_to_ass_time(current)
            end_t = seconds_to_ass_time(seg_end)
            ass_content += f"Dialogue: 0,{start_t},{end_t},Default,,0,0,0,,{colored_text}\n"
            written += 1
            current = seg_end

    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(ass_content)
    log(f"✅ ASS: {written} lines")
    return ass_path

def merge_final(video_path, commentary_audio, out_path, audio_files, ass_path, enable_subtitles=True):
    log("🎬 Merging final...")
    action_times = []
    other_times = []
    for a in audio_files:
        vt = (a.get("visual_type") or "").lower()
        if vt == "action":
            action_times.append(f"between(t,{a['start']:.2f},{a['end']:.2f})")
        else:
            other_times.append(f"between(t,{a['start']:.2f},{a['end']:.2f})")

    all_times = action_times + other_times
    all_conditions = "+".join(all_times) if all_times else "0"
    volume_expr = f"if({all_conditions},{DUCK_VOLUME},1.0)"

    if action_times:
        action_cond = "+".join(action_times)
        vo_volume_expr = f"if({action_cond},{VOL_ACTION},{VOL_OTHER})"
    else:
        vo_volume_expr = f"{VOL_OTHER}"

    filter_complex = (
        f"[0:a]volume='{volume_expr}':eval=frame[bg];"
        f"[1:a]volume='{vo_volume_expr}':eval=frame[vo];"
        f"[bg][vo]amix=inputs=2:duration=first:dropout_transition=0:"
        f"normalize=0,alimiter=limit=0.95[aout]"
    )

    subtitles_active = enable_subtitles and os.path.exists(ass_path)
    if subtitles_active:
        vf_flag = f'-vf "subtitles={ass_path}:fontsdir={FONTS_DIR}"'
        video_codec = "-c:v libx264 -preset fast -crf 23 -pix_fmt yuv420p"
    else:
        vf_flag = ""
        video_codec = "-c:v copy"

    cmd = (
        f'ffmpeg -y -i "{video_path}" -i "{commentary_audio}" '
        f'-filter_complex "{filter_complex}" '
        f'{vf_flag} '
        f'-map 0:v:0 -map "[aout]" '
        f'{video_codec} -c:a aac -b:a 192k -shortest "{out_path}" -loglevel error'
    )
    subprocess.run(cmd, shell=True)
    if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
        log(f"🔥 Final: {out_path}")
        return True
    log("❌ Merge failed")
    return False

def process_commentary(clip_path, output_path):
    log("=" * 60)
    log("🎙️ COMMENTARY")
    log("=" * 60)
    if not ELEVENLABS_API_KEY or not GROQ_KEYS or not OPENROUTER_KEYS:
        log("⚠️ Missing keys — skipping")
        return False

    vid_dur = get_duration(clip_path)
    if vid_dur <= 0:
        return False

    try:
        audio_path = f"{SEGMENTS_DIR}/extracted_audio.mp3"
        srt_path = f"{SEGMENTS_DIR}/final.srt"
        ass_path = f"{SEGMENTS_DIR}/subtitles.ass"

        extract_audio(clip_path, audio_path)
        srt_content = transcribe(audio_path, srt_path)
        if not srt_content:
            srt_content = ""

        slots = build_slots(clip_path, vid_dur, srt_content)
        slots = classify_slots(clip_path, slots, srt_content)

        comm_grid = f"{ANALYSIS_DIR}/comm_grid.jpg"
        log("🖼️ Building commentary grid...")
        cell_w = 480
        cell_h = 854
        cols = 3
        rows = 3
        small = Image.new("RGB", (cell_w * cols, cell_h * rows), (0, 0, 0))
        for i in range(9):
            t = i * (vid_dur / 9)
            tmp = f"{FRAMES_DIR}/comm_{i}.jpg"
            subprocess.run(
                f'ffmpeg -y -ss {t:.2f} -i "{clip_path}" -frames:v 1 -q:v 3 "{tmp}" -loglevel error',
                shell=True
            )
            if os.path.exists(tmp):
                try:
                    im = Image.open(tmp)
                    im = ImageOps.fit(im, (cell_w, cell_h), method=Image.LANCZOS)
                    small.paste(im, ((i % cols) * cell_w, (i // cols) * cell_h))
                except Exception:
                    pass
                try:
                    os.remove(tmp)
                except Exception:
                    pass
        small.save(comm_grid, 'JPEG', quality=85)

        segments = generate_commentary_script(slots, srt_content, comm_grid)
        audio_files = generate_tts(segments, slots, vid_dur)
        if not audio_files:
            log("❌ No audio")
            return False

        if SUBTITLES_ENABLED:
            generate_ass_subtitles(audio_files, ass_path)

        final_audio = build_timed_audio(audio_files, vid_dur)
        success = merge_final(clip_path, final_audio, output_path, audio_files, ass_path, SUBTITLES_ENABLED)
        if success:
            log(f"🔥 Commentary: {output_path}")
            return True
    except Exception as e:
        log(f"❌ Commentary: {e}")
    return False

# ============================================================
# 🎯 MAIN
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="AI Video Editor (Manual + Auto)")
    parser.add_argument("--link", help="Direct video URL")
    parser.add_argument("--title", help="Force custom title")
    parser.add_argument("--out", default="", help="Output path")
    parser.add_argument("--game", help="Game name")
    parser.add_argument("--list-games", action="store_true", help="List games")
    parser.add_argument("--reset-rotation", action="store_true", help="Reset rotation")
    parser.add_argument("--no-prompt", action="store_true", help="Skip interactive prompt")
    args = parser.parse_args()

    ensure_dirs()

    # Special commands
    if args.list_games:
        games = get_all_games()
        if not games:
            print("❌ No games in game_links_editor/")
            return
        print(f"\n📁 {len(games)} games:\n")
        for g in games:
            links = get_links_from_file(g["file"])
            print(f"   🎮 {g['game']:25s} | {len(links):3d} links")
        print()
        return

    if args.reset_rotation:
        save_rotation("")
        print("✅ Rotation reset")
        return

    # Interactive prompt
    if not args.link and not args.no_prompt:
        user_choice = ask_user_choice()

        if user_choice["mode"] == "1":
            args.link = user_choice["value"]
            if user_choice["game"]:
                args.game = user_choice["game"]
            if user_choice["title"]:
                args.title = user_choice["title"]

        elif user_choice["mode"] == "2":
            pass  # Auto mode

    log("=" * 60)
    log("🎬 AI VIDEO EDITOR v7")
    log("=" * 60)
    log(f"⏰ {now_ist_ampm()}")
    log("=" * 60)

    # Source resolve
    source = resolve_video_source(args)
    if not source:
        log("❌ No source — exiting")
        log("   Use: --link URL | add to game_links_editor/")
        sys.exit(1)

    source_url = source["url"]
    game_name = source["game"]
    mode = source["mode"]
    used_line = source.get("raw", "")
    game_file_path = source.get("file", "")

    log(f"🎯 Mode: {mode.upper()}")
    log(f"🎮 Game: {game_name}")
    log(f"🔗 URL: {source_url}")
    log("=" * 60)

    source_duration = get_duration(source_url)
    if source_duration <= 0:
        source_duration = 60.0
    log(f"⏱️ Duration: {source_duration:.2f}s")

    # Frames + grid
    timestamps = extract_frames(source_url, NUM_FRAMES)
    build_grid(timestamps)

    # Title
    style = random.choice(["curiosity", "aggressive", "question", "emoji_heavy"])
    title_result = generate_title(game_name, source_duration, style, GRID_PATH)

    # 🚫 REJECT HANDLER
    if title_result.get("status") == "reject":
        reject_reason = title_result.get("reason", "No reason given")
        log(f"🚫 AI Rejected: {reject_reason}")

        if mode == "auto" and game_file_path and used_line:
            log("=" * 60)
            log("🚫 MOVING REJECTED LINK")
            log("=" * 60)

            moved = move_link_to_rejected_folder(
                current_file=game_file_path,
                used_line=used_line,
                current_game=game_name,
                reason=reject_reason,
            )

            if moved:
                save_rotation(game_name)
                log(f"   ✅ Rejected link moved")
                log(f"   🔄 Next run me dusra link")
            else:
                log(f"   ⚠️ Move failed")
        else:
            log("📦 Manual mode — reject link not moved")

        log("=" * 60)
        log("❌ PIPELINE STOPPED (AI Rejected)")
        log("=" * 60)
        sys.exit(0)

    # SUCCESS — continue
    ai_title = args.title or title_result.get("title", f"{game_name} Clip 🔥")
    start_time = title_result.get("start_time", 0)
    clip_duration = title_result.get("duration", 15)

    log(f"🎯 Title: {ai_title}")
    log(f"⏱️ Start: {start_time}s | Dur: {clip_duration}s")
    log("=" * 60)

    # Cut
    clip_path = f"{FRAMES_DIR}/clip.mp4"
    if not cut_clip(source_url, start_time, clip_duration, clip_path):
        log("❌ Cut failed")
        sys.exit(1)

    final_video = clip_path

    # Commentary
    if COMMENTARY_ENABLED:
        dubbed = f"{FRAMES_DIR}/dubbed.mp4"
        if process_commentary(clip_path, dubbed):
            final_video = dubbed
            log("🎙️ Commentary applied")

    # Clean filename
    clean_name = re.sub(r'[^\w\s\-]', '', ai_title, flags=re.UNICODE)
    clean_name = re.sub(r'\s+', '_', clean_name)
    clean_name = re.sub(r'_+', '_', clean_name).strip('_')
    if not clean_name:
        clean_name = f"clip_{now_ist().strftime('%Y%m%d_%H%M%S')}"
    clean_name = clean_name[:100]

    output_path = os.path.join(OUTPUT_DIR, f"{clean_name}.mp4")
    counter = 1
    while os.path.exists(output_path):
        output_path = os.path.join(OUTPUT_DIR, f"{clean_name}_{counter}.mp4")
        counter += 1

    if args.out:
        output_path = args.out
        os.makedirs(os.path.dirname(output_path) or OUTPUT_DIR, exist_ok=True)

    if final_video != output_path:
        subprocess.run(f'cp "{final_video}" "{output_path}"', shell=True)
    log(f"📁 Saved: {output_path}")

    # Log
    save_video_log(title=ai_title, edited_video_link=output_path)

    # Move link to used (auto mode only)
    if mode == "auto" and game_file_path and used_line:
        log("=" * 60)
        log("📦 MOVING LINK TO USED FOLDER")
        log("=" * 60)
        moved = move_link_to_used_folder(game_file_path, used_line, game_name)
        if moved:
            save_rotation(game_name)
            log(f"   ✅ Link moved | Rotation saved")
        else:
            log(f"   ⚠️ Move failed")
    else:
        log("📦 Manual mode — no move")

    # Done
    log("=" * 60)
    log("✅ DONE")
    log("=" * 60)
    log(f"🎬 Title: {ai_title}")
    log(f"🔗 Video: {output_path}")
    log("=" * 60)

    print(json.dumps({
        "status": "success",
        "title": ai_title,
        "video_link": os.path.abspath(output_path),
        "source_url": source_url,
        "mode": mode,
    }))


if __name__ == "__main__":
    main()
