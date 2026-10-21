#!/usr/bin/env python3
"""
🎙️ AI Commentary Dubber — v9.0 (Fixed Empty/JSON Errors + 3 Models)
===============================================================
"""

import os
import sys
import functools

# 👇 Force print to flush instantly
print = functools.partial(print, flush=True)
try: sys.stdout.reconfigure(line_buffering=True)
except: pass

import argparse
import subprocess
import requests
import json
import base64
import re
import time
import ast
from PIL import Image, ImageDraw, ImageFont, ImageOps
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# CLI ARGUMENTS
# ============================================================
def parse_args():
    p = argparse.ArgumentParser(description="AI Commentary Dubber")
    p.add_argument("--video", required=True, help="Input clip path")
    p.add_argument("--out", required=True, help="Output dubbed clip path")
    p.add_argument("--voice", default=None, help="ElevenLabs voice ID (optional)")
    p.add_argument("--subtitles", choices=["true", "false"], default=None)
    return p.parse_args()

ARGS = parse_args()
FINAL_CLIP_PATH    = ARGS.video
FINAL_DUBBED_VIDEO = ARGS.out

# ============================================================
# 🎛️ ON/OFF SWITCHES & CONFIG
# ============================================================
COMMENTARY_ENABLED = os.getenv("COMMENTARY_ENABLED", "true").lower() == "true"
if ARGS.subtitles is not None:
    SUBTITLES_ENABLED = ARGS.subtitles.lower() == "true"
else:
    SUBTITLES_ENABLED = os.getenv("SUBTITLES_ENABLED", "true").lower() == "true"

# 🔑 MULTI-KEY CONFIG
def _collect_keys(*env_names):
    return [os.getenv(name) for name in env_names if os.getenv(name)]

OPENROUTER_KEYS = _collect_keys("OPENROUTER_API_KEY", "OPENROUTER_API_KEY_2", "OPENROUTER_API_KEY_3", "OPENROUTER_API_KEY_4", "OPENROUTER_API_KEY_5")
GROQ_KEYS = _collect_keys("GROQ_API_KEY", "GROQ_API_KEY_2", "GROQ_API_KEY_3")

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
VOICE_ID           = ARGS.voice or os.getenv("VOICE_ID", "91w4XjqhkWTX1Jr3O344")

AUDIO_PATH         = "extracted_audio.mp3"
SRT_PATH           = "final.srt"
ASS_PATH           = "subtitles.ass"
FONTS_DIR          = "fonts"
ANALYSIS_DIR       = "analysis"
ANALYSIS_GRID_PATH = "analysis/last_analysis.jpg"
SEGMENTS_DIR       = "segments"

MIN_SLOTS_HARD = 6
MAX_SLOTS_HARD = 20
DUCK_VOLUME = 0.35
ANALYSIS_FRAMES = 90
GRID_COLS = 9
GRID_ROWS = 10
CANVAS_W = 4320
CANVAS_H = 7680

VOICE_SPEED_MIN = 1.00
VOICE_SPEED_MAX = 1.17

ATEMPO_MIN = 1.00
ATEMPO_MAX = 1.10
ATEMPO_MAX_LAST = 1.20
ATEMPO_MAX_ACTION = 1.15

MAX_SLOT_EXTEND = 0.2
SLOT_GAP = 0.4      # 👈 GAP (0.4 seconds)
SPEED_ACTION = 1.14
SPEED_DIALOG = 1.05
SPEED_CALM   = 1.00
VOL_ACTION = 1.9
VOL_OTHER  = 1.4

os.makedirs(SEGMENTS_DIR, exist_ok=True)
os.makedirs(ANALYSIS_DIR, exist_ok=True)
os.makedirs(FONTS_DIR, exist_ok=True)

# ============================================================
# 🎨 PAINTING COLOUR FINISHING
# ============================================================
COLOR_WHITE  = "&H00FFFFFF"
COLOR_YELLOW = "&H0000FFFF"
COLOR_BLUE   = "&H00FF0000"
COLOR_RESET  = "&H00FFFFFF"

def get_pattern_color(word_index, total_words):
    if word_index == total_words - 1: return COLOR_BLUE
    if word_index % 2 == 0: return COLOR_WHITE
    else: return COLOR_YELLOW

# ============================================================
# ENV VALIDATION & HELPERS
# ============================================================
def validate_env():
    missing = []
    if not OPENROUTER_KEYS: missing.append("OPENROUTER_API_KEY")
    if not GROQ_KEYS: missing.append("GROQ_API_KEY")
    if not ELEVENLABS_API_KEY: missing.append("ELEVENLABS_API_KEY")
    if missing:
        print(f"❌ Missing env vars: {', '.join(missing)}")
        return False
    if not os.path.exists(FINAL_CLIP_PATH):
        print(f"❌ Input video not found: {FINAL_CLIP_PATH}")
        return False
    print(f"✅ Keys loaded — OpenRouter: {len(OPENROUTER_KEYS)} | Groq: {len(GROQ_KEYS)} | ElevenLabs: 1")
    return True

def seconds_to_srt_time(seconds):
    h, m, s = int(seconds // 3600), int((seconds % 3600) // 60), int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def seconds_to_ass_time(seconds):
    h, m, s = int(seconds // 3600), int((seconds % 3600) // 60), int(seconds % 60)
    cs = int(((seconds - int(seconds)) * 100))
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def encode_image(path):
    with open(path, "rb") as f: return base64.b64encode(f.read()).decode('utf-8')

def get_duration(path):
    try:
        cmd = f"ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 {path}"
        out = subprocess.check_output(cmd, shell=True).decode().strip()
        return float(out) if out else 10.0
    except: return 10.0

def parse_srt(srt_content):
    entries = []
    for block in srt_content.strip().split("\n\n"):
        lines = block.split("\n")
        if len(lines) >= 3:
            tm = re.match(r"(\d+):(\d+):(\d+),(\d+) --> (\d+):(\d+):(\d+),(\d+)", lines[1])
            if tm:
                s = int(tm.group(1))*3600 + int(tm.group(2))*60 + int(tm.group(3)) + int(tm.group(4))/1000
                e = int(tm.group(5))*3600 + int(tm.group(6))*60 + int(tm.group(7)) + int(tm.group(8))/1000
                text = " ".join(l.strip() for l in lines[2:])
                entries.append({"start": s, "end": e, "text": text})
    return entries

def speed_for_type(slot_type):
    if slot_type == "action": return SPEED_ACTION
    elif slot_type == "dialog": return SPEED_DIALOG
    else: return SPEED_CALM

# ============================================================
# 🔥 ULTIMATE JSON EXTRACTOR
# ============================================================
def extract_json_from_response(raw):
    if not raw: return None
    text = str(raw).strip()
    
    try: 
        parsed = json.loads(text)
        if isinstance(parsed, dict) and "segments" in parsed: return parsed
        if isinstance(parsed, list) and len(parsed) > 0: return {"segments": parsed}
    except: pass
    
    m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL | re.IGNORECASE)
    if m:
        try:
            parsed = json.loads(m.group(1))
            if isinstance(parsed, dict) and "segments" in parsed: return parsed
            if isinstance(parsed, list) and len(parsed) > 0: return {"segments": parsed}
        except: pass

    for start_c, end_c in [('{', '}'), ('[', ']')]:
        start, end = text.find(start_c), text.rfind(end_c)
        if start != -1 and end != -1 and end > start:
            json_str = text[start:end+1]
            try:
                parsed = json.loads(json_str)
                if isinstance(parsed, dict) and "segments" in parsed: return parsed
                if isinstance(parsed, list) and len(parsed) > 0: return {"segments": parsed}
            except: pass
            
            try:
                fixed = re.sub(r',\s*([\]}])', r'\1', json_str)
                parsed = json.loads(fixed)
                if isinstance(parsed, dict) and "segments" in parsed: return parsed
                if isinstance(parsed, list) and len(parsed) > 0: return {"segments": parsed}
            except: pass
            
            try:
                py_str = json_str.replace("true", "True").replace("false", "False").replace("null", "None")
                parsed = ast.literal_eval(py_str)
                if isinstance(parsed, dict) and "segments" in parsed: return parsed
                if isinstance(parsed, list) and len(parsed) > 0: return {"segments": parsed}
            except: pass
            
    return None

# ============================================================
# ASS SUBTITLE GENERATOR
# ============================================================
def generate_full_ass_script(audio_files, font_name="Arial", font_size=60, alignment=2, vertical_margin=40, outline_size=3, shadow_size=2):
    print("🎨 Generating ASS Subtitles...")
    ass_content = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,{outline_size},{shadow_size},{alignment},10,10,{vertical_margin},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    written = 0
    for item in audio_files:
        start, end = item.get("start", 0), item.get("actual_end", item.get("end", 3))
        text = item.get("text", "").strip()
        if not text: continue
        words = text.split()
        if not words: continue
        total_dur = max(end - start, 0.1)
        total_chars = sum(len(w) for w in words) or 1
        total_words = len(words)
        current_time, cumulative_chars = start, 0

        for i, w in enumerate(words):
            cumulative_chars += len(w)
            seg_end = start + (total_dur * (cumulative_chars / total_chars))
            visible_words = words[:i+1]
            colored_text = " ".join(f"{{\\c{get_pattern_color(j, total_words)}}}{vw}{{\\c{COLOR_RESET}}}" for j, vw in enumerate(visible_words))
            ass_content += f"Dialogue: 0,{seconds_to_ass_time(current_time)},{seconds_to_ass_time(seg_end)},Default,,0,0,0,,{colored_text}\n"
            written += 1
            current_time = seg_end

    with open(ASS_PATH, "w", encoding="utf-8") as f: f.write(ass_content)
    print(f"✅ ASS Subtitles saved: {ASS_PATH} ({written} lines)\n")

# ============================================================
# SIGNAL EXTRACTION & MOTION SCORE
# ============================================================
def get_motion_score(video_path, start, end):
    try:
        duration = max(end - start, 0.5)
        cmd = f'ffmpeg -ss {start:.2f} -t {duration:.2f} -i {video_path} -vf "select=\'gt(scene,0.1)\',metadata=print" -f null -hide_banner -loglevel error - 2>&1'
        out = subprocess.run(cmd, shell=True, capture_output=True, text=True).stderr
        return len(re.findall(r"pts_time", out))
    except: return 0

def get_scene_timeline(video_path):
    cmd = f'ffmpeg -i {video_path} -filter:v "select=\'gt(scene,0.3)\',showinfo" -f null -hide_banner -loglevel error - 2>&1'
    out = subprocess.run(cmd, shell=True, capture_output=True, text=True).stderr
    return [float(m.group(1)) for m in re.finditer(r"pts_time:([\d.]+)", out)]

def get_loudness_timeline(video_path):
    cmd = f'ffmpeg -i {video_path} -af "astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-" -f null -hide_banner -loglevel error - 2>&1'
    out = subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout
    timeline, t = [], 0.0
    for line in out.split("\n"):
        m = re.search(r"RMS_level=(-?[\d.]+|inf)", line)
        if m and m.group(1) != "-inf":
            try: timeline.append((t, float(m.group(1))))
            except: pass
            t += 0.1
    return timeline

def slot_loudness(timeline, start, end):
    vals = [v for t, v in timeline if start <= t < end]
    return max(vals) if vals else -60

# ============================================================
# GIT PUSH
# ============================================================
def commit_analysis_to_github():
    print("📤 [10] Pushing analysis image to GitHub...")
    if not os.path.exists(ANALYSIS_GRID_PATH): return
    try:
        subprocess.run("git config --global user.name 'GitHub Action'", shell=True, check=False)
        subprocess.run("git config --global user.email 'action@github.com'", shell=True, check=False)
        subprocess.run("git fetch -q origin", shell=True, check=False)
        subprocess.run("git pull -q --rebase --autostash origin main", shell=True, check=False)
        subprocess.run(f"git add {ANALYSIS_GRID_PATH}", shell=True, check=False)
        subprocess.run("git commit -m 'Update analysis image [skip ci]'", shell=True, check=False)
        subprocess.run("git push -q origin HEAD --force-with-lease", shell=True, check=False)
        print("   🚀 Pushed to GitHub successfully.")
    except Exception as e: print(f"   ⚠️ Git operation failed: {e}")
    print()

# ============================================================
# STEP 1 & 2 — Extract & Transcribe
# ============================================================
def extract_audio(video_path, out_path):
    print("🎧 [1] Extracting audio...")
    subprocess.run(f"ffmpeg -y -i {video_path} -vn -acodec libmp3lame -q:a 4 {out_path} -hide_banner -loglevel error", shell=True, check=True)
    print("✅ Audio extracted\n")

def transcribe(audio_path):
    print(f"📝 [2] Transcribing audio (Groq — {len(GROQ_KEYS)} keys)...")
    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    srt_content, success = "", False

    for key_idx, groq_key in enumerate(GROQ_KEYS, start=1):
        print(f"   🔑 Trying Groq key {key_idx}/{len(GROQ_KEYS)}...")
        try:
            with open(audio_path, "rb") as f:
                files = {"file": (audio_path, f, "audio/mp3")}
                data = {"model": "whisper-large-v3", "response_format": "verbose_json"}
                headers = {"Authorization": f"Bearer {groq_key}"}
                r = requests.post(url, headers=headers, files=files, data=data, timeout=120)

            if r.status_code == 200:
                res = r.json()
                for i, seg in enumerate(res.get("segments", []), start=1):
                    srt_content += f"{i}\n{seconds_to_srt_time(seg.get('start', 0))} --> {seconds_to_srt_time(seg.get('end', 0))}\n{seg.get('text', '').strip()}\n\n"
                with open(SRT_PATH, "w", encoding="utf-8") as sf: sf.write(srt_content)
                print(f"   ✅ Key {key_idx} worked! SRT saved\n")
                success = True
                break
            elif r.status_code in (401, 403, 429): time.sleep(1); continue
            else: time.sleep(2); continue
        except Exception: time.sleep(2); continue

    if not success: print("   ❌ All Groq keys failed\n")
    return srt_content

# ============================================================
# STEP 3 & 4 — Slots & Classification
# ============================================================
def build_auto_slots(video_path, vid_duration, srt_content):
    print("📐 [3] Building AUTO slots...")
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
            if v >= threshold and v > -20: audio_peaks.add(round(t, 2))

    base = 2.5 if vid_duration <= 20 else 3.0 if vid_duration <= 40 else 3.5 if vid_duration <= 70 else 4.5 if vid_duration <= 120 else 5.5
    if speech_ratio > 0.7: base *= 0.85
    elif speech_ratio < 0.25: base *= 1.15
    cuts_per_sec = len(scene_times) / max(vid_duration, 1)
    if cuts_per_sec > 0.5: base *= 0.85
    elif cuts_per_sec < 0.12: base *= 1.1

    total = max(MIN_SLOTS_HARD, min(MAX_SLOTS_HARD, int(round(vid_duration / base))))
    
    slot_sec = (vid_duration - (total - 1) * SLOT_GAP) / total
    if slot_sec < 1.0: slot_sec = 1.0

    all_boundaries = sorted(srt_boundaries | scene_boundaries | audio_peaks)
    all_boundaries = [b for b in all_boundaries if 0.5 < b < vid_duration - 0.5]

    slots, t, used = [], 0.0, set()
    for i in range(total):
        target_end = vid_duration if i == total - 1 else t + slot_sec
        candidates = [b for b in all_boundaries if b not in used and t + 1.0 < b < target_end + 0.5]

        if candidates and i < total - 1:
            srt_cands = [b for b in candidates if b in srt_boundaries]
            scene_cands = [b for b in candidates if b in scene_boundaries]
            snap = min(srt_cands if srt_cands else scene_cands if scene_cands else candidates, key=lambda x: abs(x - target_end))
            end = snap if abs(snap - target_end) < 1.0 else target_end
            used.add(snap)
        else: 
            end = target_end

        end = min(end, vid_duration)
        end = max(end, t + 1.0)

        slots.append({
            "start": round(t, 2), "end": round(end, 2), "type": None, "visual_type": None, 
            "srt_text": "", "scene_count": 0, "avg_loud": -50, "sub_analysis": {}, 
            "voice_speed": 1.0, "motion_score": 0, "gpt_type": None, "final_type": None, "speed_boost_log": []
        })
        
        if i == total - 1:
            t = end
        else:
            t = end + SLOT_GAP
            
        if t >= vid_duration - 0.5: break

    if slots and slots[-1]["end"] < vid_duration - 0.1: slots[-1]["end"] = round(vid_duration, 2)
    for slot in slots:
        slot_srt = [e for e in srt_entries if e["start"] >= slot["start"] - 0.15 and e["end"] <= slot["end"] + 0.15]
        slot["srt_text"] = " ".join(e["text"] for e in slot_srt)
        for e in slot_srt:
            e["start"], e["end"] = slot["start"], slot["end"]

    print(f"   ✅ Built {len(slots)} slots (Gap: {SLOT_GAP}s)\n")
    return slots

def classify_slots_combined(video_path, slots, srt_content):
    print("🔍 [4] Classifying slots (signal + motion)...")
    scene_times = get_scene_timeline(video_path)
    loud_timeline = get_loudness_timeline(video_path)
    srt_entries = parse_srt(srt_content)
    ACTION_WORDS = {"shoot","fire","hit","run","kill","die","attack","grenade","boom","jump","dodge","cover","reload","go","move","watch","left","right","down","up","quick","destroy","target","lock","bang","drop","danger","whoa","oh","yeah","nice","sick","cook","big","fast"}

    for slot in slots:
        motion = get_motion_score(video_path, slot["start"], slot["end"])
        slot["motion_score"] = motion
        sub_windows, t = [], slot["start"]
        while t < slot["end"]:
            sw_end = min(t + 0.5, slot["end"])
            sub_windows.append({"start": t, "end": sw_end})
            t = sw_end

        action_count, dialog_count, calm_count = 0, 0, 0
        for sw in sub_windows:
            scene_cuts = sum(1 for st in scene_times if sw["start"] <= st < sw["end"])
            loud = slot_loudness(loud_timeline, sw["start"], sw["end"])
            sw_text = " ".join(e["text"] for e in srt_entries if e["start"] >= sw["start"] and e["end"] <= sw["end"]).lower()
            words = set(sw_text.split())
            has_action_word = len(words & ACTION_WORDS) >= 1
            has_speech = len(sw_text.strip()) > 3

            if has_action_word or scene_cuts >= 2 or loud > -15: action_count += 1
            elif has_speech: dialog_count += 1
            else: calm_count += 1

        total = max(len(sub_windows), 1)
        action_ratio, dialog_ratio, calm_ratio = action_count/total, dialog_count/total, calm_count/total

        if motion >= 5: action_ratio = min(1.0, action_ratio + 0.40)
        elif motion >= 3: action_ratio = min(1.0, action_ratio + 0.25)
        if motion >= 3: calm_ratio = max(0.0, calm_ratio - 0.30)

        if action_ratio >= 0.30 or motion >= 5: slot["type"] = "action"
        elif dialog_ratio >= 0.40: slot["type"] = "dialog"
        elif calm_ratio >= 0.50 and motion < 2: slot["type"] = "calm"
        elif action_ratio >= 0.20 or motion >= 3: slot["type"] = "action"
        elif dialog_ratio >= 0.20: slot["type"] = "dialog"
        else: slot["type"] = "calm"

        slot["scene_count"] = sum(1 for st in scene_times if slot["start"] <= st < slot["end"])
        slot["avg_loud"] = round(slot_loudness(loud_timeline, slot["start"], slot["end"]), 1)
        slot["sub_analysis"] = {"action_ratio": round(action_ratio, 2), "dialog_ratio": round(dialog_ratio, 2), "calm_ratio": round(calm_ratio, 2), "motion_score": motion}
        voice_speed = speed_for_type(slot["type"])
        if slot["type"] == "action":
            if slot["scene_count"] >= 3: voice_speed += 0.03
            if slot["avg_loud"] > -12: voice_speed += 0.03
            if motion >= 5: voice_speed += 0.02
        slot["voice_speed"] = round(max(VOICE_SPEED_MIN, min(VOICE_SPEED_MAX, voice_speed)), 2)

    print(f"✅ Slots classified: {len(slots)}\n")
    return slots

# ============================================================
# STEP 5 — 8K PORTRAIT ANALYSIS GRID
# ============================================================
def build_analysis_grid(video_path, vid_duration, slots, num_frames=ANALYSIS_FRAMES):
    print(f"🖼️ [5] Building 8K PORTRAIT grid — {num_frames} frames...")
    if os.path.exists(ANALYSIS_GRID_PATH):
        try: os.remove(ANALYSIS_GRID_PATH)
        except: pass

    frame_specs = []
    if slots:
        total_dur = sum(s["end"] - s["start"] for s in slots)
        for slot_idx, slot in enumerate(slots):
            slot_dur = slot["end"] - slot["start"]
            n_frames = max(1, round(num_frames * (slot_dur / total_dur)))
            for k in range(n_frames):
                frame_specs.append((slot["start"] + (slot_dur * ((k + 0.5) / n_frames)), slot["start"], slot["end"], slot_idx))

    frame_specs = sorted(frame_specs, key=lambda x: x[0])
    if len(frame_specs) > num_frames:
        step = len(frame_specs) / num_frames
        frame_specs = [frame_specs[int(i * step)] for i in range(num_frames)]

    frame_paths = []
    for i, (t, slot_start, slot_end, slot_idx) in enumerate(frame_specs):
        fp = f"temp_analysis_{i:03d}.jpg"
        subprocess.run(f"ffmpeg -y -ss {t:.2f} -i {video_path} -vframes 1 -q:v 1 {fp} -hide_banner -loglevel error", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(fp): frame_paths.append((fp, t, slot_start, slot_end, slot_idx))
        if i > 0 and i % 20 == 0: print(f"   📸 Extracted {i}/{len(frame_specs)} frames...")

    cell_w, cell_h = CANVAS_W // GRID_COLS, CANVAS_H // GRID_ROWS
    grid = Image.new("RGB", (CANVAS_W, CANVAS_H), (0, 0, 0))
    draw = ImageDraw.Draw(grid)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", max(28, cell_w // 16))
        small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", max(20, cell_w // 24))
    except: font = small_font = ImageFont.load_default()

    for idx, (fp, t, slot_start, slot_end, slot_idx) in enumerate(frame_paths):
        if idx >= GRID_COLS * GRID_ROWS: break
        try: img = ImageOps.fit(Image.open(fp), (cell_w, cell_h), method=Image.LANCZOS)
        except: continue
        x, y = (idx % GRID_COLS) * cell_w, (idx // GRID_COLS) * cell_h
        grid.paste(img, (x, y))
        draw.rectangle([x + 6, y + 6, x + 420, y + 100], fill="black")
        draw.text((x + 14, y + 12), f"SLOT {slot_idx+1}: {slot_start:.1f}-{slot_end:.1f}s", fill="yellow", font=font)
        draw.text((x + 14, y + 58), f"frame@{t:.2f}s", fill="cyan", font=small_font)

    grid.save(ANALYSIS_GRID_PATH, quality=92, optimize=True, subsampling=2)
    print(f"✅ 8K Full Quality: {grid.size[0]}x{grid.size[1]} ({os.path.getsize(ANALYSIS_GRID_PATH)/(1024*1024):.2f} MB)")
    print(f"💾 Saved: {ANALYSIS_GRID_PATH}")
    print(f"   📸 Frames captured : {len(frame_paths)}")
    print(f"   📋 Slots covered   : {len(set(f[4] for f in frame_paths))}/{len(slots)}\n")

    for fp, _, _, _, _ in frame_paths:
        if os.path.exists(fp): os.remove(fp)

# ============================================================
# STEP 6 — GENERATE SCRIPT (FIXED JSON & SAFETY FILTERS)
# ============================================================
def generate_full_script(slots, srt_content, analysis_grid_path):
    print(f"🤖 [6] Generating script (No Image Compression)...")
    if os.path.exists(analysis_grid_path):
        try:
            img = Image.open(analysis_grid_path)
            print(f"   📸 Analysis Screenshot: {os.path.abspath(analysis_grid_path)} ({os.path.getsize(analysis_grid_path)/(1024*1024):.2f} MB)\n")
        except Exception: pass

    slot_lines = [f"- Slot {i}: {s['start']:.2f}s → {s['end']:.2f}s [{s['type'].upper()}] (scenes={s['scene_count']}, loud={s['avg_loud']}dB, action={sa.get('action_ratio', 0)}, dialog={sa.get('dialog_ratio', 0)}, motion={sa.get('motion_score', 0)}) SRT: \"{s['srt_text'][:70]}\"" for i, s in enumerate(slots, 1) if (sa := s.get("sub_analysis", {})) is not None]

    prompt = f"""You are a HYPED-UP gaming YouTuber — like a streamer going CRAZY on stream.
You shout, laugh, hype, roast. Pure energy. Zero boring lines.

**YOU ARE GETTING 1 IMAGE — ANALYSIS GRID:**
- Each cell shows: "SLOT X: A.A-B.Bs" (yellow) + "frame@T.TTs" (cyan)
- ⚠️ USE THE SLOT TIME (yellow label) — NOT the frame time
- Match frames to slots by SLOT number

**YOUR JOB:**
Look at the frames. React LOUDLY like a real streamer watching live gameplay.
Focus on VISUALS — characters, screens, action, environment, weapons, enemies, faces.

**HOW TO TALK — NATURAL CASUAL ENGLISH:**
- Contractions: "he's", "ain't", "gonna", "wanna", "kinda"
- Slang: "bruh", "yo", "bro", "nah", "fr", "lowkey", "bet", "cap"
- Short sentences. Fragments OK.
- Start with reactions: "YO!", "BRO!", "WAIT!", "NAH!", "AYY!", "WHAT'S UP GUYS!", "YO WHAT'S UP GUYS!",

**REACTION PATTERNS (use 20-25 varied):**
1. BIG ACTION
2. PREDICTIONS WITH HOOK
3. SMART MOVES
4. ENEMY ROAST
5. EPIC MOMENTS
6. FULL FREEDOM
7. HYPE
8. WEIRD
9. CLOSE CALL
10. FOLLOW REQUEST (2-3 total)
11. FREESTYLE
12. ENVIRONMENT
13. SOUND
14. CINEMATIC SHOT
15. FLIRTY/FUNNY "BABY" (1-2 times only)
16. LIKE + BELL CTA (3-4 times)
17. SWEARING (Max 5-7 times, censored)
18. HMM / THINKING (2-3 times, dialog/calm only)
19. HYPE INTRO (2-3 times)
20. COMMENT CTA
21. KILL/DEATH/HIT — React INSTANTLY

**🎮 REAL-TIME GAMEPLAY MODE:**
- You ARE the player. Not watching. React LIVE like you're in the fight RIGHT NOW.
- Always PRESENT TENSE — happening this second, not after.
- Every enemy death, every hit, every dodge, every shot fired — react INSTANTLY. Never miss a moment.
- Use SHORT, EXPLOSIVE reactions when killing or destroying. Full sentences only for calm moments.
- NEVER repeat the same reaction twice in a row. Every moment deserves a UNIQUE response.
- VARY your reaction LENGTH — some words, some fragments, some full sentences.
- Match VOICE TONE to the moment — whisper for tension, SHOUT for action, calm for chill.
- If you see FIGHTING or INTENSE ACTION — react FIRST, describe LATER. Reaction > description.
- Add SUSPENSE before big moments when you sense buildup — hold the tension.
- NEVER say what you SEE — say what you FEEL. Emotion over description.
- When multiple enemies go down at once — react with ESCALATING hype, not the same tone.
- When YOU take damage — react with PAIN or PANIC, not calm.
- When YOU dodge or survive — react with RELIEF or COCKY confidence.
- When YOU win a fight — react with DOMINANCE, not just happiness.
- ALWAYS address the viewer naturally — make them feel part of the fight.
- Keep reactions SHORTER when action is FAST, LONGER when action is SLOW.
- NEVER narrate like a documentary. YOU are IN the moment, not outside it.
- If nothing big happens — build ANTICIPATION, don't fill silence with boring lines.

**🎯 ENGAGEMENT & RETENTION**
- Address the viewer directly (guys, friends, you)
- Ask natural questions
- Hype them up
- Keep them watching till the end

**🎭 SCENE-MATCHING:**
- ACTION → shout, hype, CAPS lines
- DIALOG → conversational, NO shouting
- CALM → chill, relaxed, NO hype

**🚫 NEVER shout on non-action scenes.**

**PACING:**
- "action" → 3-5 words, HIGH energy, CAPS
- "dialog" → 5-7 words, conversational
- "calm" → 6-8 words, chill

**🎯 VISUAL CLASSIFICATION RULES**

**⚠️⚠️⚠️ AGGRESSIVE ACTION DETECTION ⚠️⚠️⚠️**
If you see ANY of these → visual_type = "action":
- 🔥 FIRE, FLAMES, EXPLOSIONS, BLAST
- 💥 SMOKE, SPARKS, DUST
- 🩸 IMPACT, DAMAGE, HITS
- 🔫 WEAPONS FIRING, MUZZLE FLASH
- ⚔️ COMBAT STANCE, FISTS UP, MID-ATTACK
- 👥 MULTIPLE CHARACTERS CLOSE
- 🏃 RUNNING, JUMPING, DODGING
- 💢 CHARACTER BEING HIT, KNOCKED BACK
- 📊 HEALTH BARS, HIT MARKERS
- 🎯 AIMING DOWN SIGHTS
- 🎬 CINEMATIC ACTION, SHAKY CAM

**visual_type = "dialog" ONLY if:**
- Close-up of face while speaking
- Character standing still, facing camera

**visual_type = "calm" for EVERYTHING ELSE:**
- Slow camera panning, scenery, menus, walking slowly

**RULES:**
1. NATURAL — casual, slang, contractions
2. REACT with emotion
3. Focus on VISUALS
4. UNIQUE lines based on actual frames
5. 5-8 words per line
6. Reference "guys" or "you" naturally
7. Max 2-3 follow requests

**STORY CONTEXT:**
{srt_content[:2500]}

**YOUR SLOTS (fill ALL {len(slots)}):**
{chr(10).join(slot_lines)}

**BANNED:** "insane play", "here we go", "game on"

**CRITICAL JSON RULES:**
- NO markdown formatting (Do NOT use ```json ... ```)
- NO extra text before or after the JSON
- NO escaped quotes (use standard double quotes)
- NO null values (use empty string "" instead)
- NO empty values (every field must have content)
- ONLY return the JSON object

Return ONLY valid JSON:
{{
  "story_summary": "Brief one-line summary.",
  "segments": [
    {{
      "slot": 1,
      "start": 0.0,
      "end": 3.5,
      "text": "YOUR COMMENTARY HERE",
      "visual_type": "calm"
    }}
  ]
}}
"""

    full_b64 = encode_image(analysis_grid_path)
    segments, winning_model, winning_route = None, None, None

    # Helper function to avoid repetitive code
    def _try_call(model_id, key):
        payload = {
            "model": model_id,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{full_b64}", "detail": "high"}}
            ]}],
            "max_tokens": 4000,
            "temperature": 0.9,
            "response_format": {"type": "json_object"}, # 👈 FIXED: Reverted to json_object
            "plugins": [{"id": "response-healing"}]     # 👈 FIXED: Added healing plugin
        }
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        
        try:
            r = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=240)
            if r.status_code == 200:
                ai = r.json()
                actual_model = ai.get('model', model_id)
                content = ai.get('choices', [{}])[0].get('message', {}).get('content')
                raw = str(content).strip() if content else ""
                
                if not raw: return None, actual_model, "empty"
                
                parsed = extract_json_from_response(raw)
                if parsed and isinstance(parsed.get("segments"), list) and len(parsed["segments"]) > 0:
                    return parsed["segments"], actual_model, None
                return None, actual_model, "json"
            
            elif r.status_code == 404: return None, model_id, "not_found"
            elif r.status_code in (401, 402, 403): return None, model_id, "auth"
            elif r.status_code == 429: return None, model_id, "rate"
            else: return None, model_id, f"http_{r.status_code}"
        except Exception:
            return None, model_id, "exception"

    # =====================================================
    # MODEL 1 — nvidia/nemotron-3.5-super-vl:free
    # =====================================================
    print(f"🤖 [MODEL TRY 1] nvidia/nemotron-3.5-super-vl:free (max 2 attempts total)")
    first_attempts = [OPENROUTER_KEYS[0], OPENROUTER_KEYS[1]] if len(OPENROUTER_KEYS) >= 2 else [OPENROUTER_KEYS[0]] * 2 if len(OPENROUTER_KEYS) == 1 else []

    for attempt, key in enumerate(first_attempts, start=1):
        if segments: break
        if attempt > 1: time.sleep(2) # Rate limit safety
        print(f"   🔑 Attempt {attempt}/{len(first_attempts)}...", end=" ")
        
        segs, actual, err = _try_call("nvidia/nemotron-3.5-super-vl:free", key)
        if segs:
            segments, winning_model, winning_route = segs, "nvidia/nemotron-3.5-super-vl:free", actual
            print(f"✅ SUCCESS! (Actual: {actual})")
        elif err == "not_found":
            print("❌ Model Not Found — skipping")
            break
        else:
            print(f"⚠️ {err} → next attempt")
    print()

    # =====================================================
    # MODEL 2 — nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free
    # =====================================================
    if not segments:
        print(f"🤖 [MODEL TRY 2] nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free (max 2 attempts total)")
        for attempt, key in enumerate(first_attempts, start=1):
            if segments: break
            if attempt > 1: time.sleep(2)
            print(f"   🔑 Attempt {attempt}/{len(first_attempts)}...", end=" ")
            
            segs, actual, err = _try_call("nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free", key)
            if segs:
                segments, winning_model, winning_route = segs, "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free", actual
                print(f"✅ SUCCESS! (Actual: {actual})")
            elif err == "not_found":
                print("❌ Model Not Found — skipping")
                break
            else:
                print(f"⚠️ {err} → next attempt")
        print()

    # =====================================================
    # MODEL 3 — openrouter/free (Max 10 attempts)
    # =====================================================
    if not segments:
        print(f"🤖 [MODEL TRY 3] openrouter/free (each key up to 2 tries → max {len(OPENROUTER_KEYS)*2} attempts)")
        stop_m3 = False
        for k_idx, key in enumerate(OPENROUTER_KEYS, start=1):
            if segments or stop_m3: break
            for retry in range(2):
                if segments or stop_m3: break
                if retry > 0: time.sleep(1.5)
                print(f"   🔑 Key {k_idx}/{len(OPENROUTER_KEYS)} — try {retry+1}/2...", end=" ")
                
                segs, actual, err = _try_call("openrouter/free", key)
                if segs:
                    segments, winning_model, winning_route = segs, "openrouter/free", actual
                    print(f"✅ SUCCESS! (Actual: {actual})")
                    break
                elif err == "not_found":
                    print("❌ Model Not Found — skipping")
                    stop_m3 = True
                    break
                elif err in ("json", "empty"):
                    if retry == 0:
                        print(f"⚠️ {err} → retry same key")
                        continue
                    else:
                        print(f"⚠️ {err} → next key")
                        break
                else:
                    print(f"⚠️ {err} → next key")
                    break
        print()

    if not segments:
        print("=" * 60 + "\n❌ ALL MODELS AND KEYS FAILED\n⚠️ Returning empty. Original video will be uploaded.\n" + "=" * 60 + "\n")
        return []

    print(f"=======================================================\n🏆 WINNING MODEL: {winning_model}")
    if winning_model != winning_route and winning_route: print(f"   🔀 ACTUAL ROUTE: {winning_route}")
    print(f"=======================================================\n")

    # =========================================================
    # 🔒 STRICT TIMING LOCK
    # =========================================================
    print(f"   🔒 TIMING LOCK — Forcing all segments to match slots...")
    if len(segments) == len(slots):
        for i, seg in enumerate(segments):
            seg["slot"] = i + 1
            seg["start"] = slots[i]["start"]
            seg["end"] = slots[i]["end"]
    else:
        for seg in segments:
            slot_num = seg.get("slot")
            if slot_num and isinstance(slot_num, int) and 1 <= slot_num <= len(slots):
                exact_slot = slots[slot_num - 1]
                seg["start"], seg["end"] = exact_slot["start"], exact_slot["end"]
            else:
                best_slot, best_diff = None, 999
                for s in slots:
                    diff = abs(s["start"] - float(seg.get("start", 0)))
                    if diff < best_diff: best_diff, best_slot = diff, s
                if best_slot:
                    seg["start"], seg["end"] = best_slot["start"], best_slot["end"]
                    seg["slot"] = slots.index(best_slot) + 1

    print(f"   ✅ ALL SEGMENTS LOCKED TO SLOT TIMES\n")
    print(f"   📝 AI COMMENTARY & TIMING VERIFICATION:")
    for seg in segments:
        print(f"      🎬 Slot {seg.get('slot', '?')}: [{seg.get('start', 0.0):.2f}s → {seg.get('end', 0.0):.2f}s] [{str(seg.get('visual_type', 'calm')).upper()}] | \"{seg.get('text', '')}\"")
    print()

    # TYPE REFINEMENT
    for seg in segments:
        vt = str(seg.get("visual_type") or "").lower().strip()
        if vt not in ("action", "dialog", "calm"): continue
        best_slot, best_diff = None, 999
        for slot in slots:
            diff = abs(slot["start"] - float(seg.get("start", 0)))
            if diff < best_diff: best_diff, best_slot = diff, slot

        if best_slot and best_diff < 2.5:
            signal_type, scene_count, avg_loud = best_slot.get("type", "calm"), best_slot.get("scene_count", 0), best_slot.get("avg_loud", -50)
            sa = best_slot.get("sub_analysis", {})
            action_ratio, motion = sa.get("action_ratio", 0), sa.get("motion_score", 0)
            srt_word_count = len(best_slot.get("srt_text", "").split())

            signal_says_action = (signal_type == "action" and action_ratio >= 0.25) or (motion >= 3) or (action_ratio >= 0.30) or (scene_count >= 3 and avg_loud > -18)
            has_strong_dialog = (srt_word_count >= 8 and action_ratio < 0.40 and motion < 3)
            is_likely_scenery = (avg_loud < -30 and scene_count == 0 and motion < 2)

            final_type = vt
            if vt == "calm" and signal_says_action and not has_strong_dialog and not is_likely_scenery:
                final_type = "action"
            elif vt == "calm" and signal_says_action and has_strong_dialog:
                final_type = "dialog"

            if final_type != best_slot.get("type"):
                best_slot["voice_speed"] = speed_for_type(final_type)
                if final_type == "action":
                    if scene_count >= 3: best_slot["voice_speed"] = min(VOICE_SPEED_MAX, best_slot["voice_speed"] + 0.03)
                    if avg_loud > -12: best_slot["voice_speed"] = min(VOICE_SPEED_MAX, best_slot["voice_speed"] + 0.03)
                    if motion >= 5: best_slot["voice_speed"] = min(VOICE_SPEED_MAX, best_slot["voice_speed"] + 0.02)

            best_slot["visual_type"], best_slot["type"] = final_type, final_type

    return segments

# ============================================================
# STEP 7 — ElevenLabs TTS
# ============================================================
def generate_audio(segments, slots, vid_duration):
    print("🔊 [7] Generating TTS...")
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"
    headers = {"Accept": "audio/mpeg", "Content-Type": "application/json", "xi-api-key": ELEVENLABS_API_KEY}
    audio_files = []

    for idx, seg in enumerate(segments):
        text = seg.get("text", "").strip()
        if not text: continue
        matched_slot = None
        slot_num = seg.get("slot")
        if slot_num and isinstance(slot_num, int) and 1 <= slot_num <= len(slots): 
            matched_slot = slots[slot_num - 1]
        else:
            best_diff = 999
            for s in slots:
                diff = abs(s["start"] - float(seg.get("start", 0)))
                if diff < best_diff: best_diff, matched_slot = diff, s
        if not matched_slot: continue

        slot_start, slot_end = matched_slot["start"], matched_slot["end"]
        target_dur = slot_end - slot_start
        voice_speed = max(VOICE_SPEED_MIN, min(VOICE_SPEED_MAX, matched_slot.get("voice_speed", 1.0)))
        visual_type = (matched_slot.get("type") or "calm").lower().strip()
        seg_file = f"{SEGMENTS_DIR}/seg_{idx:03d}.mp3"

        data = {"text": text, "model_id": "eleven_multilingual_v2", "voice_settings": {"stability": 0.4, "similarity_boost": 0.75, "style": 0.5, "use_speaker_boost": True, "speed": voice_speed}}

        try:
            r = requests.post(url, json=data, headers=headers, timeout=60)
            if r.status_code == 200:
                with open(seg_file, "wb") as af: af.write(r.content)
                actual = get_duration(seg_file)
                atempo_used, slot_extended = "none", 0.0
                is_last = (idx == len(segments) - 1)
                atempo_max = ATEMPO_MAX_LAST if is_last else ATEMPO_MAX

                if visual_type == "action" and not is_last:
                    if actual > target_dur + 0.05:
                        tempo = max(ATEMPO_MIN, min(ATEMPO_MAX_ACTION, actual / target_dur))
                        if tempo > 1.01:
                            fit_file = f"{SEGMENTS_DIR}/seg_{idx:03d}_fit.mp3"
                            subprocess.run(f"ffmpeg -y -i {seg_file} -filter:a atempo={tempo:.3f} {fit_file} -hide_banner -loglevel error", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            final = fit_file if os.path.exists(fit_file) else seg_file
                            atempo_used = f"{tempo:.3f} (action)"
                        else: final = seg_file
                    else: final = seg_file
                    final_dur = get_duration(final)
                    if final_dur > target_dur + 0.2:
                        slot_extended = min(final_dur - target_dur, MAX_SLOT_EXTEND)
                        atempo_used += f" + slot+{slot_extended:.2f}s"
                else:
                    if actual > 0 and target_dur > 0:
                        tempo = max(ATEMPO_MIN, min(atempo_max, actual / target_dur))
                        if tempo > 1.01:
                            fit_file = f"{SEGMENTS_DIR}/seg_{idx:03d}_fit.mp3"
                            subprocess.run(f"ffmpeg -y -i {seg_file} -filter:a atempo={tempo:.3f} {fit_file} -hide_banner -loglevel error", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            final = fit_file if os.path.exists(fit_file) else seg_file
                            atempo_used = f"{tempo:.3f}" + (" (last)" if is_last else "")
                        else: final = seg_file
                    else: final = seg_file

                audio_files.append({"file": final, "start": slot_start, "end": slot_end + slot_extended, "actual_end": slot_start + get_duration(final), "actual_dur": actual, "text": text, "visual_type": visual_type, "slot_extended": slot_extended})
                print(f"   ✅ FIT [Slot {slot_num}] [{visual_type.upper()}] [speed={voice_speed:.2f}] Audio={actual:.2f}s → {get_duration(final):.2f}s | atempo={atempo_used}")
            elif r.status_code == 401: print("   ❌ 401 — ElevenLabs key galat!"); break
            elif r.status_code == 429: print("   ⚠️ 429 — rate limit"); time.sleep(3)
        except Exception as e: print(f"   ⚠️ seg {idx}: {e}")

    print(f"\n✅ {len(audio_files)} audio segments generated\n")
    return audio_files

# ============================================================
# STEP 8 & 9 — Audio & Merge
# ============================================================
def build_timed_audio(audio_files, vid_duration):
    print("🎼 [8] Building timed audio...")
    silent = f"{SEGMENTS_DIR}/silent_base.mp3"
    subprocess.run(f"ffmpeg -y -f lavfi -i anullsrc=r=44100:cl=stereo -t {vid_duration} -q:a 9 -acodec libmp3lame {silent} -hide_banner -loglevel error", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    inputs, parts, mix_inputs = ["-i", silent], [], ["[0:a]"]
    for i, a in enumerate(audio_files, start=1):
        inputs.extend(["-i", a["file"]])
        delay = int(a["start"] * 1000)
        parts.append(f"[{i}:a]adelay={delay}|{delay}[a{i}]")
        mix_inputs.append(f"[a{i}]")
    filter_complex = ";".join(parts) + f";{''.join(mix_inputs)}amix=inputs={len(mix_inputs)}:duration=first:dropout_transition=0:normalize=0,alimiter=limit=0.95[out]"
    final_audio = f"{SEGMENTS_DIR}/final_commentary.mp3"
    subprocess.run(f"ffmpeg -y {' '.join(inputs)} -filter_complex \"{filter_complex}\" -map \"[out]\" -acodec libmp3lame -q:a 4 {final_audio} -hide_banner -loglevel error", shell=True, check=True)
    print("✅ Timed commentary built\n")
    return final_audio

def merge_final(video_path, commentary_audio, out_path, audio_files, enable_subtitles=True):
    print("🎬 [9] Merging...")
    action_times = [f"between(t,{a['start']:.2f},{a['end']:.2f})" for a in audio_files if (a.get("visual_type") or "").lower().strip() == "action"]
    other_times = [f"between(t,{a['start']:.2f},{a['end']:.2f})" for a in audio_files if (a.get("visual_type") or "").lower().strip() != "action"]
    all_conditions = "+".join(action_times + other_times) if (action_times + other_times) else "0"
    action_condition = "+".join(action_times) if action_times else "0"

    filter_complex = f"[0:a]volume='if({all_conditions},{DUCK_VOLUME},1.0)':eval=frame[bg];[1:a]volume='if({action_condition},{VOL_ACTION},{VOL_OTHER})':eval=frame[vo];[bg][vo]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,alimiter=limit=0.95[aout]"
    vf_flag = f'-vf "subtitles={ASS_PATH}:fontsdir={FONTS_DIR}"' if enable_subtitles and os.path.exists(ASS_PATH) else ""
    video_codec = "-c:v libx264 -preset fast -crf 23 -pix_fmt yuv420p" if vf_flag else "-c:v copy"

    subprocess.run(f'ffmpeg -y -i {video_path} -i {commentary_audio} -filter_complex "{filter_complex}" {vf_flag} -map 0:v:0 -map "[aout]" {video_codec} -c:a aac -b:a 192k -shortest {out_path} -hide_banner -loglevel error', shell=True, check=True)
    print(f"🔥 Final video ready: {out_path}\n")

def fallback_copy_original():
    try:
        subprocess.run(f"ffmpeg -y -i {FINAL_CLIP_PATH} -c copy {FINAL_DUBBED_VIDEO} -hide_banner -loglevel error", shell=True, check=True)
        print(f"✅ Original copied: {FINAL_DUBBED_VIDEO}")
        return True
    except Exception as e:
        print(f"❌ Fallback failed: {e}")
        return False

# ============================================================
# MAIN
# ============================================================
def main():
    print("=" * 60 + "\n🎙️ AI COMMENTARY DUBBER — v9.0 (No Image Compression)\n" + "=" * 60)
    
    if not COMMENTARY_ENABLED:
        print("🚫 Commentary OFF — copying original...")
        sys.exit(0 if fallback_copy_original() else 1)

    if not validate_env():
        print("⚠️ Missing Keys — falling back...")
        fallback_copy_original()
        sys.exit(0)

    vid_dur = get_duration(FINAL_CLIP_PATH)
    print(f"📹 Video duration: {vid_dur:.2f}s\n")

    try:
        extract_audio(FINAL_CLIP_PATH, AUDIO_PATH)
        srt_content = transcribe(AUDIO_PATH)
        slots = build_auto_slots(FINAL_CLIP_PATH, vid_dur, srt_content)
        slots = classify_slots_combined(FINAL_CLIP_PATH, slots, srt_content)
        build_analysis_grid(FINAL_CLIP_PATH, vid_dur, slots, num_frames=ANALYSIS_FRAMES)
        
        segments = generate_full_script(slots, srt_content, ANALYSIS_GRID_PATH)

        if not segments:
            print("=" * 60 + "\n⚠️ NO SEGMENTS — Original video upload ho raha hai.\n" + "=" * 60)
            commit_analysis_to_github()
            sys.exit(0 if fallback_copy_original() else 1)

        audio_files = generate_audio(segments, slots, vid_dur)
        if not audio_files: raise Exception("No audio files generated")

        if SUBTITLES_ENABLED:
            generate_full_ass_script(audio_files, font_name="BebasNeue-Regular", font_size=55, alignment=2, vertical_margin=65)

        final_audio = build_timed_audio(audio_files, vid_dur)
        merge_final(FINAL_CLIP_PATH, final_audio, FINAL_DUBBED_VIDEO, audio_files, enable_subtitles=SUBTITLES_ENABLED)

        print("=" * 60 + f"\n🔥🔥 DONE! {FINAL_DUBBED_VIDEO}\n" + "=" * 60)
        commit_analysis_to_github()
        sys.exit(0)

    except Exception as e:
        print(f"\n❌ Pipeline failed: {e}")
        commit_analysis_to_github()
        sys.exit(0 if fallback_copy_original() else 1)

if __name__ == "__main__":
    main()