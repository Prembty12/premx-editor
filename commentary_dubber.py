#!/usr/bin/env python3
"""
🎙️ AI Commentary Dubber — Multi-Key Auto-Retry + ON/OFF Switch + Auto Voice Speed
===============================================================
Called from pipeline.sh Step 8.5:
    python3 commentary_dubber.py --video X --out Y

Multi-Key Support:
  • OpenRouter: OPENROUTER_API_KEY, _2, _3, _4, _5  (5 keys)
  • Groq:       GROQ_API_KEY, _2, _3                (3 keys)
  • ElevenLabs: ELEVENLABS_API_KEY                  (1 key)

ON/OFF Switch:
  • COMMENTARY_ENABLED=true   → commentary chalegi (default)
  • COMMENTARY_ENABLED=false  → commentary skip, original clip copy

🎮 Auto Voice Speed (Frame-Based):
  • GPT frames dekh ke har slot ka visual_type deta hai
  • Action slots  → 1.10 - 1.15 (hype)
  • Dialog slots  → 1.03
  • Calm slots    → 1.00
  • Speed floor   = 1.0 (kabhi kam nahi)
  • Speed ceiling = 1.15 (kabhi zyada nahi)
  • Fallback: signal-based classifier agar GPT visual_type na de

🎯 PERFECT COMMENTARY FIXES:
  • FIX #1: Tolerance 1.0 → 2.5 + Signal override (GPT galat ho toh signal jeetega)
  • FIX #2: Prompt mein hard action rules
  • FIX #3: Model gpt-4o-mini (Free/Cheap version)
  • FIX #4: 90 frames (9x10 grid) + 8K canvas
  • Analysis image: analysis/full_8k_analysis.jpg (8K, aapke liye)
  • GPT image: analysis/last_analysis.jpg (4K resized, GPT limit ke liye)
  • Git Push: Analysis images auto-commit + push to GitHub (Python ke andar se)
"""

import os
import sys
import argparse
import subprocess
import requests
import json
import base64
import re
import time
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
    return p.parse_args()


ARGS = parse_args()
FINAL_CLIP_PATH    = ARGS.video
FINAL_DUBBED_VIDEO = ARGS.out


# ============================================================
# 🎛️ COMMENTARY ON/OFF SWITCH
# ============================================================
COMMENTARY_ENABLED = os.getenv("COMMENTARY_ENABLED", "true").lower() == "true"


# ============================================================
# 🔑 MULTI-KEY CONFIG — ENV VARIABLES
# ============================================================
def _collect_keys(*env_names):
    """Collect all valid keys from env, in order."""
    return [os.getenv(name) for name in env_names if os.getenv(name)]


OPENROUTER_KEYS = _collect_keys(
    "OPENROUTER_API_KEY",
    "OPENROUTER_API_KEY_2",
    "OPENROUTER_API_KEY_3",
    "OPENROUTER_API_KEY_4",
    "OPENROUTER_API_KEY_5",
)

GROQ_KEYS = _collect_keys(
    "GROQ_API_KEY",
    "GROQ_API_KEY_2",
    "GROQ_API_KEY_3",
)

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
VOICE_ID           = ARGS.voice or os.getenv("VOICE_ID", "91w4XjqhkWTX1Jr3O344")


# Paths
AUDIO_PATH         = "extracted_audio.mp3"
SRT_PATH           = "final.srt"
ANALYSIS_DIR       = "analysis"
ANALYSIS_GRID_PATH = "analysis/last_analysis.jpg"           # GPT ke liye (4K resized)
FULL_8K_PATH       = "analysis/full_8k_analysis.jpg"        # Aapke liye (8K full)
SEGMENTS_DIR       = "segments"

MIN_SLOTS_HARD = 6
MAX_SLOTS_HARD = 20
DUCK_VOLUME = 0.25

# 🎯 90 frames — 8K portrait canvas (9x10 grid)
ANALYSIS_FRAMES = 90
GRID_COLS = 9
GRID_ROWS = 10
CANVAS_W = 4320       # 8K portrait width
CANVAS_H = 7680       # 8K portrait height

# 🎯 GPT ke liye resize target (OpenRouter ki ~20MB limit ke liye)
GPT_TARGET_W = 2160
GPT_TARGET_H = 3840

# 🎮 Voice speed limits — auto adjust, but clamped here
VOICE_SPEED_MIN = 1.00
VOICE_SPEED_MAX = 1.15
ATEMPO_MAX      = 1.08

# 🎮 Speed per visual type
SPEED_ACTION = 1.13
SPEED_DIALOG = 1.03
SPEED_CALM   = 1.00

os.makedirs(SEGMENTS_DIR, exist_ok=True)
os.makedirs(ANALYSIS_DIR, exist_ok=True)
# ============================================================


# ============================================================
# ENV VALIDATION
# ============================================================
def validate_env():
    missing = []
    if not OPENROUTER_KEYS:
        missing.append("OPENROUTER_API_KEY (1-5)")
    if not GROQ_KEYS:
        missing.append("GROQ_API_KEY (1-3)")
    if not ELEVENLABS_API_KEY:
        missing.append("ELEVENLABS_API_KEY")

    if missing:
        print(f"❌ Missing env vars: {', '.join(missing)}")
        return False

    if not os.path.exists(FINAL_CLIP_PATH):
        print(f"❌ Input video not found: {FINAL_CLIP_PATH}")
        return False

    print(f"✅ Keys loaded — OpenRouter: {len(OPENROUTER_KEYS)} | Groq: {len(GROQ_KEYS)} | ElevenLabs: 1")
    return True


# ============================================================
# HELPERS
# ============================================================
def seconds_to_srt_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def encode_image(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode('utf-8')


def get_duration(path):
    cmd = (
        f"ffprobe -v error -show_entries format=duration "
        f"-of default=noprint_wrappers=1:nokey=1 {path}"
    )
    try:
        out = subprocess.check_output(cmd, shell=True).decode().strip()
        return float(out) if out else 10.0
    except Exception as e:
        print(f"⚠️ duration fail: {e}")
        return 10.0


def parse_srt(srt_content):
    entries = []
    for block in srt_content.strip().split("\n\n"):
        lines = block.split("\n")
        if len(lines) >= 3:
            tm = re.match(
                r"(\d+):(\d+):(\d+),(\d+) --> (\d+):(\d+):(\d+),(\d+)",
                lines[1]
            )
            if tm:
                s = int(tm.group(1))*3600 + int(tm.group(2))*60 + int(tm.group(3)) + int(tm.group(4))/1000
                e = int(tm.group(5))*3600 + int(tm.group(6))*60 + int(tm.group(7)) + int(tm.group(8))/1000
                entries.append({"start": s, "end": e, "text": lines[2].strip()})
    return entries


def speed_for_type(slot_type):
    """Slot type se voice speed nikaalo"""
    if slot_type == "action":
        return SPEED_ACTION
    elif slot_type == "dialog":
        return SPEED_DIALOG
    else:
        return SPEED_CALM


# ============================================================
# 🎯 GIT PUSH — Analysis image ko GitHub par bhejo (Python version)
# ============================================================
def commit_analysis_to_github():
    print("📤 [10] Pushing analysis images to GitHub...")

    files_to_push = []
    if os.path.exists(ANALYSIS_GRID_PATH):
        files_to_push.append(ANALYSIS_GRID_PATH)
    if os.path.exists(FULL_8K_PATH):
        files_to_push.append(FULL_8K_PATH)

    if not files_to_push:
        print("   ⚠️ No analysis images found, skipping git commit.")
        return

    try:
        # Git config
        subprocess.run("git config --global user.name 'GitHub Action'", shell=True, check=False)
        subprocess.run("git config --global user.email 'action@github.com'", shell=True, check=False)

        # Pull latest to prevent conflicts
        subprocess.run("git pull --rebase origin main || git pull --rebase origin master || true", shell=True, check=False)

        # Add both images
        for f in files_to_push:
            subprocess.run(f"git add {f}", shell=True, check=False)
            print(f"   📎 Staged: {f}")

        # Commit
        commit_res = subprocess.run(
            "git commit -m 'Update analysis images [skip ci]'",
            shell=True, capture_output=True, text=True
        )
        if commit_res.returncode == 0:
            print("   ✅ Committed analysis images.")
        else:
            print("   ℹ️ No changes to commit (images might be identical).")

        # Push
        push_res = subprocess.run("git push origin HEAD", shell=True, capture_output=True, text=True)
        if push_res.returncode == 0:
            print("   🚀 Pushed to GitHub successfully.")
        else:
            print(f"   ⚠️ Push failed: {push_res.stderr.strip()}")

    except Exception as e:
        print(f"   ⚠️ Git operation failed: {e}")
    print()


# ============================================================
# STEP 1 — Extract Audio
# ============================================================
def extract_audio(video_path, out_path):
    print("🎧 [1] Extracting audio...")
    subprocess.run(
        f"ffmpeg -y -i {video_path} -vn -acodec libmp3lame -q:a 4 {out_path}",
        shell=True, check=True
    )
    print("✅ Audio extracted\n")


# ============================================================
# STEP 2 — Transcribe (MULTI-KEY GROQ)
# ============================================================
def transcribe(audio_path):
    print(f"📝 [2] Transcribing audio (Groq — {len(GROQ_KEYS)} keys available)...")
    url = "https://api.groq.com/openai/v1/audio/transcriptions"

    srt_content = ""
    success = False

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
                    srt_content += (
                        f"{i}\n"
                        f"{seconds_to_srt_time(seg.get('start', 0))} --> "
                        f"{seconds_to_srt_time(seg.get('end', 0))}\n"
                        f"{seg.get('text', '').strip()}\n\n"
                    )
                with open(SRT_PATH, "w", encoding="utf-8") as sf:
                    sf.write(srt_content)
                print(f"   ✅ Key {key_idx} worked! SRT saved ({len(srt_content)} chars)\n")
                success = True
                break

            elif r.status_code in (401, 403):
                print(f"   ❌ Key {key_idx} invalid/expired (HTTP {r.status_code}) — trying next...")
                time.sleep(1)
                continue

            elif r.status_code == 429:
                print(f"   ⚠️ Key {key_idx} rate-limited (429) — trying next...")
                time.sleep(2)
                continue

            else:
                print(f"   ⚠️ Key {key_idx} error {r.status_code}: {r.text[:120]}")
                time.sleep(2)
                continue

        except requests.exceptions.Timeout:
            print(f"   ⏱️ Key {key_idx} timeout — trying next...")
            time.sleep(2)
            continue
        except Exception as e:
            print(f"   ⚠️ Key {key_idx} exception: {e}")
            time.sleep(2)
            continue

    if not success:
        print("   ❌ All Groq keys failed — SRT empty (commentary may be limited)\n")

    return srt_content


# ============================================================
# SIGNAL EXTRACTION
# ============================================================
def get_scene_timeline(video_path):
    cmd = (
        f'ffmpeg -i {video_path} -filter:v "select=\'gt(scene,0.3)\',showinfo" '
        f'-f null - 2>&1'
    )
    out = subprocess.run(cmd, shell=True, capture_output=True, text=True).stderr
    return [float(m.group(1)) for m in re.finditer(r"pts_time:([\d.]+)", out)]


def get_loudness_timeline(video_path):
    cmd = (
        f'ffmpeg -i {video_path} -af "astats=metadata=1:reset=1,'
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
            except:
                pass
            t += 0.1
    return timeline


def slot_loudness(timeline, start, end):
    vals = [v for t, v in timeline if start <= t < end]
    return max(vals) if vals else -60


# ============================================================
# STEP 3 — AUTO SLOTS
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
            if v >= threshold and v > -20:
                audio_peaks.add(round(t, 2))

    print(f"   📝 SRT boundaries: {len(srt_boundaries)}")
    print(f"   🎬 Scene cuts: {len(scene_boundaries)}")
    print(f"   🔊 Audio peaks: {len(audio_peaks)}")
    print(f"   🗣️  Speech ratio: {speech_ratio*100:.0f}%")

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

    print(f"   ⏱️  Base slot: {slot_sec:.2f}s")
    print(f"   📋 Target slots: {total}")

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

        candidates = [
            b for b in all_boundaries
            if b not in used and t + 1.5 < b < target_end + 1.0
        ]

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

        slot_text = " ".join(
            e["text"] for e in srt_entries
            if e["start"] >= t and e["end"] <= end
        ).strip()

        slots.append({
            "start": round(t, 2),
            "end": round(end, 2),
            "type": None,
            "visual_type": None,
            "srt_text": slot_text,
            "scene_count": 0,
            "avg_loud": -50,
            "sub_analysis": {},
            "voice_speed": 1.0
        })
        t = end

        if t >= vid_duration - 0.1:
            break

    if slots and slots[-1]["end"] < vid_duration - 0.1:
        slots[-1]["end"] = round(vid_duration, 2)

    print(f"   ✅ Built {len(slots)} slots\n")
    return slots


# ============================================================
# STEP 4 — SUB-WINDOW CLASSIFY (Fallback) + AUTO VOICE SPEED
# ============================================================
def classify_slots_combined(video_path, slots, srt_content):
    print("🔍 [4] Classifying slots (signal-based fallback)...")

    scene_times = get_scene_timeline(video_path)
    loud_timeline = get_loudness_timeline(video_path)
    srt_entries = parse_srt(srt_content)

    print(f"   🎬 Scene cuts: {len(scene_times)}")
    print(f"   🔊 Loudness samples: {len(loud_timeline)}")
    print(f"   📝 SRT entries: {len(srt_entries)}")

    ACTION_WORDS = {"shoot","fire","hit","run","kill","die","attack",
                    "grenade","boom","jump","dodge","cover","reload",
                    "go","move","watch","left","right","down","up","quick",
                    "destroy","target","lock","bang","drop","danger",
                    "whoa","oh","yeah","nice","sick","cook","big","fast"}
    DIALOG_WORDS = {"you","me","we","what","why","how","hey","listen",
                    "wait","okay","yeah","know","think","feel","want",
                    "need","can","will"}

    for slot in slots:
        sub_windows = []
        t = slot["start"]
        while t < slot["end"]:
            sw_end = min(t + 0.5, slot["end"])
            sub_windows.append({"start": t, "end": sw_end})
            t = sw_end

        action_count = 0
        dialog_count = 0
        calm_count = 0

        for sw in sub_windows:
            scene_cuts = sum(
                1 for st in scene_times if sw["start"] <= st < sw["end"]
            )
            loud = slot_loudness(loud_timeline, sw["start"], sw["end"])
            sw_text = " ".join(
                e["text"] for e in srt_entries
                if e["start"] >= sw["start"] and e["end"] <= sw["end"]
            ).lower()
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

        if action_ratio >= 0.15:
            slot["type"] = "action"
        elif dialog_ratio >= 0.4:
            slot["type"] = "dialog"
        elif calm_ratio >= 0.6:
            slot["type"] = "calm"
        elif action_ratio >= 0.10:
            slot["type"] = "action"
        elif dialog_ratio >= 0.20:
            slot["type"] = "dialog"
        else:
            slot["type"] = "calm"

        slot["scene_count"] = sum(
            1 for st in scene_times if slot["start"] <= st < slot["end"]
        )
        slot["avg_loud"] = round(
            slot_loudness(loud_timeline, slot["start"], slot["end"]), 1
        )
        slot["sub_analysis"] = {
            "action_ratio": round(action_ratio, 2),
            "dialog_ratio": round(dialog_ratio, 2),
            "calm_ratio": round(calm_ratio, 2),
            "total_subs": total
        }

        voice_speed = speed_for_type(slot["type"])

        if slot["type"] == "action":
            if slot["scene_count"] >= 3:
                voice_speed += 0.05
            if slot["avg_loud"] > -12:
                voice_speed += 0.04

        slot["voice_speed"] = round(max(VOICE_SPEED_MIN, min(VOICE_SPEED_MAX, voice_speed)), 2)

    speeds = [s["voice_speed"] for s in slots]
    print(f"✅ Slots classified (signal-based): {len(slots)}")
    print(f"🎮 Voice speeds (pre-GPT): min={min(speeds):.2f} max={max(speeds):.2f} avg={sum(speeds)/len(speeds):.2f}\n")
    return slots


# ============================================================
# STEP 5 — 8K PORTRAIT ANALYSIS GRID (90 frames, 9x10)
# ============================================================
def build_analysis_grid(video_path, vid_duration, num_frames=ANALYSIS_FRAMES):
    print(f"🖼️ [5] Building 8K PORTRAIT grid ({CANVAS_W}×{CANVAS_H}) — {num_frames} frames...")

    # 🗑️ Purani analysis images delete karo
    for path in [ANALYSIS_GRID_PATH, FULL_8K_PATH]:
        if os.path.exists(path):
            try:
                os.remove(path)
                print(f"   🗑️  Old file deleted: {path}")
            except Exception as e:
                print(f"   ⚠️  Could not delete {path}: {e}")

    interval = vid_duration / num_frames
    frame_paths = []

    for i in range(num_frames):
        t = i * interval
        fp = f"temp_analysis_{i:03d}.jpg"
        subprocess.run(
            f"ffmpeg -y -ss {t:.2f} -i {video_path} -vframes 1 -q:v 1 {fp}",
            shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        if os.path.exists(fp):
            frame_paths.append((fp, t))

    cell_w = CANVAS_W // GRID_COLS
    cell_h = CANVAS_H // GRID_ROWS

    grid = Image.new("RGB", (CANVAS_W, CANVAS_H), (0, 0, 0))
    draw = ImageDraw.Draw(grid)

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", max(24, cell_w // 18))
    except:
        try:
            font = ImageFont.truetype("/system/fonts/Roboto-Bold.ttf", max(24, cell_w // 18))
        except:
            font = ImageFont.load_default()

    for idx, (fp, t) in enumerate(frame_paths):
        if idx >= GRID_COLS * GRID_ROWS:
            break
        try:
            img = Image.open(fp)
            img = ImageOps.pad(img, (cell_w, cell_h), color=(0, 0, 0), method=Image.LANCZOS)
        except:
            continue

        x = (idx % GRID_COLS) * cell_w
        y = (idx // GRID_COLS) * cell_h
        grid.paste(img, (x, y))

        label = f"{t:.1f}s"
        draw.rectangle([x + 8, y + 8, x + 160, y + 60], fill="black")
        draw.text((x + 16, y + 14), label, fill="yellow", font=font)

    # ==================================================
    # 🎯 SAVE 1: 8K FULL QUALITY (aapke liye)
    # ==================================================
    grid.save(FULL_8K_PATH, quality=92, optimize=True, subsampling=2)
    size_8k = os.path.getsize(FULL_8K_PATH) / (1024 * 1024)
    print(f"✅ 8K Full Quality: {grid.size[0]}x{grid.size[1]} ({size_8k:.2f} MB)")
    print(f"💾 Saved: {FULL_8K_PATH}")

    # ==================================================
    # 🎯 SAVE 2: GPT ke liye resize (OpenRouter limit ke liye)
    # ==================================================
    grid_gpt = grid.resize((GPT_TARGET_W, GPT_TARGET_H), Image.LANCZOS)
    grid_gpt.save(ANALYSIS_GRID_PATH, quality=92, optimize=True, subsampling=2)
    size_gpt = os.path.getsize(ANALYSIS_GRID_PATH) / (1024 * 1024)
    print(f"✅ GPT Version: {grid_gpt.size[0]}x{grid_gpt.size[1]} ({size_gpt:.2f} MB)")
    print(f"💾 Saved: {ANALYSIS_GRID_PATH}\n")

    for fp, _ in frame_paths:
        if os.path.exists(fp):
            os.remove(fp)


# ============================================================
# STEP 6 — GPT Call (MULTI-KEY OPENROUTER) — WITH VISUAL TYPE
# ============================================================
def generate_full_script(slots, srt_content, analysis_grid_path):
    print(f"🤖 [6] Generating FULL script + visual classification (OpenRouter — {len(OPENROUTER_KEYS)} keys)...")

    slot_lines = []
    for i, s in enumerate(slots, 1):
        sa = s.get("sub_analysis", {})
        slot_lines.append(
            f"- Slot {i}: {s['start']:.1f}s → {s['end']:.1f}s "
            f"[{s['type'].upper()}] "
            f"(scenes={s['scene_count']}, loud={s['avg_loud']}dB, "
            f"action={sa.get('action_ratio', 0)}, dialog={sa.get('dialog_ratio', 0)}) "
            f"SRT: \"{s['srt_text'][:70]}\""
        )

    prompt = f"""You are a HYPED-UP gaming YouTuber — like a streamer going CRAZY on stream.
You shout, laugh, hype, roast. Pure energy. Zero boring lines.

**YOU ARE GETTING 1 IMAGE — ANALYSIS GRID:**
- 90 frames with timestamps
- Match frames to slots.

**YOUR JOB:**
Look at the frames. React LOUDLY like a real streamer watching live gameplay.
Focus on VISUALS — characters, screens, action, environment, weapons, enemies, faces, graphics.

**HOW TO TALK — NATURAL CASUAL ENGLISH:**
- Contractions: "he's", "ain't", "gonna", "wanna", "kinda"
- Slang: "bruh", "yo", "bro", "nah", "fr", "lowkey", "bet", "cap"
- Short sentences. Fragments OK.
- Start with reactions: "YO!", "BRO!", "WAIT!", "NAH!", "AYY!"
- Repeat for emphasis: "No no no no", "Wait wait wait"

**REACTION PATTERNS (use 10-14 varied):**
1. BIG ACTION: "OHHHH! He's GONE!", "BRO! That was NASTY!", "AYYYY! Dropped him!"
2. SWEARING (max 5-8 total, censor): "OHHH Fuckk that was CLEAN!", "Holy sh*t!"
3. VIEWER QUESTIONS (2-4): "Guys, is this game worth buying?", "Yo, anyone else play this?"
4. GRAPHICS (2-3): "Bro these graphics are INSANE!", "Yo the visuals are FIRE!", "Nah the lighting is next level!", "These graphics look AMAZING!", "Bro the details are CRAZY!"
5. ENEMY ROAST: "Bro this guy's aim is worse than mine.", "Enemy NPCs look so confused lol."
6. GAME JOKES: "Bro reloading with 1 HP left, risky business.", "This map design is cursed."
7. CINEMATIC: "Okay that was actually cinema, wow."
8. FUNNY: "Bro's collecting stuff like it's a grocery run."
9. FOLLOW REQUEST (2-3 total): "Ayy if you're vibing, hit that follow yo."
10. HYPE: "Okay okay okay — something's coming!", "Wait wait WAIT!"
11. CHILL: "Just vibing here, chilling.", "Too quiet... sus.", "Too quiet... something's off.", "Too quiet... fishy.", "Too quiet... suspicious."
12. WEIRD: "What even is that thing?!"
13. PREDICTIONS (2-4): "He's gonna die here, watch.", "guys I'm calling it — this is a W."
14. SELF-DEPRECATING (2-3): "I would've died there honestly.", "This is why I'm not a pro."
15. Guys (2-4): "guys, you seeing this?!", "Yo guys, you believe this?"
16. SOUND (2-3): "Yo did you HEAR that?!", "That audio is crispy."
17. CALLBACKS (1-2): "Remember that guy from earlier? Yeah."
18. KNOCK EVENTS: "KNOCKED HIM!", "He's DOWN!", "One knocked, push push!", "Got him down!"
19. HYPE VARIETY: "Let him COOK!", "Bro is COOKED!", "We eating good tonight!", "He's on fire!"
20. CLUTCH: "CLUTCHED IT!", "One HP and he's alive!", "Bro is HIM!", "What a save!"
21. BIG HYPE: "What a blast today!", "He's gonna wreck everyone today!", "I'm gonna wreck everyone today!", "He's gonna body everyone!", "Nobody can stop him today!"
22. SWEARING (max 5-8 total, censor with asterisks): "Holy sh*t!", "What the f*ck!", "That's bullsh*t!", "Son of a b*tch!", "Damn!", "Hell yeah!", "Get rekt!", "You suck!", "Trash!", "Noob!", "Bot!", "Dumbass!"
23. INSULTS/ROASTS (safe, 3-5): "Get rekt!", "Trash!", "Noob!", "Bot!", "You suck!", "What a bot!", "Delete the game!", "Uninstall!", "GG ez!"
24. ENEMY CAMPING ROAST: "Come out, where you hiding?!", "Stop camping, you coward!", "Come fight me, bro!", "Stop hiding, you bot!", "Camping again? Trash!", "Show yourself, coward!", "Where you at, you noob?!"

**🎯 CRITICAL: VISUAL CLASSIFICATION — HARD RULES**
Look at the frames for each slot's time range. Classify each slot:

**visual_type = "action" if you see ANY of these:**
- Multiple people in a single frame
- Any weapon (knife, gun, stick, bat)
- Body in motion (running pose, kick, punch, jump)
- Motion blur in the frame
- Character facing AWAY from camera while moving
- Stairs/doors being rushed
- Blood, impact effects, particles
- Character in crouched/combat stance
- Two characters close together (fighting distance)

**visual_type = "dialog" ONLY if:**
- Close-up of face while speaking
- Character standing still facing camera
- Subtitles/words visible on screen
- Two people standing still facing each other

**visual_type = "calm" ONLY if:**
- ZERO motion across 3+ consecutive frames
- Empty environment shot
- Menu/UI screen
- Walking slowly with no threat

**⚠️ DEFAULT TO "action" IF UNSURE — NEVER default to calm.**

**Be ACCURATE. This decides voice speed!**

**PACING RULES (based on visual_type):**
- visual_type = "action" → VERY short punchy lines (3-5 words), HIGH energy, CAPS
- visual_type = "dialog" → 5-7 words, conversational
- visual_type = "calm" → 6-8 words, chill/observational

**RULES:**
1. NATURAL — casual, slang, contractions
2. REACT with emotion — hype, scream, laugh, roast
3. Focus on VISUALS
4. UNIQUE lines based on actual frames
5. Roast ENEMIES and GAME MECHANICS
6. 5-8 words per line — short, punchy
7. Vary energy — sometimes chill, sometimes WILD
8. Reference "guys" or "you" naturally
9. Max 2-3 follow requests total
10. Use CAPS for shouting

**STORY CONTEXT:**
{srt_content[:2500]}

**YOUR SLOTS (fill ALL {len(slots)}):**
{chr(10).join(slot_lines)}

**BANNED phrases:** "insane play", "here we go", "game on"

Return ONLY valid JSON:
{{
  "story_summary": "Brief one-line summary.",
  "segments": [
    {{
      "slot": 1,
      "start": 0.0,
      "end": 3.5,
      "text": "...",
      "visual_type": "action"
    }}
  ]
}}
"""

    or_url = "https://openrouter.ai/api/v1/chat/completions"
    analysis_b64 = encode_image(analysis_grid_path)

    # 🎯 Model: gpt-4o-mini (Free tier)
    payload = {
        "model": "openai/gpt-4o-mini",
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url",
                 "image_url": {
                     "url": f"data:image/jpeg;base64,{analysis_b64}",
                     "detail": "high"
                 }}
            ]
        }],
        "max_tokens": 4000,
        "temperature": 0.9,
        "response_format": {"type": "json_object"}
    }

    for key_idx, or_key in enumerate(OPENROUTER_KEYS, start=1):
        print(f"\n   🔑 Trying OpenRouter key {key_idx}/{len(OPENROUTER_KEYS)}...")

        headers = {
            "Authorization": f"Bearer {or_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/",
            "X-Title": "Gaming Commentary"
        }

        for attempt in range(2):
            try:
                print(f"      Attempt {attempt+1}/2...")
                r = requests.post(or_url, headers=headers, json=payload, timeout=240)
                print(f"      Status: {r.status_code}")

                if r.status_code == 200:
                    ai = r.json()
                    raw = ai['choices'][0]['message'].get('content', '').strip()

                    if raw.startswith("```"):
                        raw = raw.split("```")[1]
                        if raw.startswith("json"):
                            raw = raw[4:].strip()
                        raw = raw.rstrip("`").strip()

                    parsed = json.loads(raw)
                    segments = parsed.get("segments", [])

                    # 🎯 FIX #1: Tolerance 2.5 + Signal override
                    updated_count = 0
                    for seg in segments:
                        vt = (seg.get("visual_type") or "").lower().strip()
                        if vt not in ("action", "dialog", "calm"):
                            continue

                        best_slot = None
                        best_diff = 999
                        for slot in slots:
                            diff = abs(slot["start"] - seg.get("start", 0))
                            if diff < best_diff:
                                best_diff = diff
                                best_slot = slot

                        if best_slot and best_diff < 2.5:
                            signal_type = best_slot.get("type", "calm")
                            scene_count = best_slot.get("scene_count", 0)
                            avg_loud = best_slot.get("avg_loud", -50)
                            sa = best_slot.get("sub_analysis", {})
                            action_ratio = sa.get("action_ratio", 0)

                            signal_says_action = (
                                signal_type == "action"
                                or scene_count >= 2
                                or avg_loud > -15
                                or action_ratio >= 0.15
                            )

                            if vt == "calm" and signal_says_action:
                                final_type = "action"
                                print(f"   ⚠️  Slot @{best_slot['start']:.1f}s: GPT said CALM but signal says ACTION → using ACTION")
                            elif vt == "action" and signal_type == "calm" and scene_count == 0 and avg_loud < -25:
                                final_type = "calm"
                                print(f"   ⚠️  Slot @{best_slot['start']:.1f}s: GPT said ACTION but signal says CALM → using CALM")
                            else:
                                final_type = vt

                            best_slot["visual_type"] = final_type
                            best_slot["type"] = final_type
                            best_slot["voice_speed"] = speed_for_type(final_type)
                            updated_count += 1

                    print(f"   ✅ Key {key_idx} worked! {len(segments)} segments")
                    print(f"   🎯 Visual classification applied to {updated_count}/{len(slots)} slots\n")
                    return segments

                elif r.status_code in (401, 403):
                    print(f"      ❌ Key {key_idx} invalid (HTTP {r.status_code})")
                    break

                elif r.status_code == 429:
                    print(f"      ⚠️ Key {key_idx} rate-limited (429)")
                    time.sleep(2)
                    continue

                else:
                    print(f"      ⚠️ Error {r.status_code}: {r.text[:120]}")
                    time.sleep(2)
                    continue

            except json.JSONDecodeError as e:
                print(f"      ⚠️ JSON error: {e}")
                time.sleep(2)
                continue
            except requests.exceptions.Timeout:
                print(f"      ⏱️ Timeout")
                time.sleep(2)
                continue
            except Exception as e:
                print(f"      ⚠️ Exception: {e}")
                time.sleep(2)
                continue

    print("⚠️ All OpenRouter keys failed — using fallback lines\n")
    FALLBACK = {
        "action": ["Ohh things are heating up!", "He's in the middle of it!",
                   "Chaos everywhere!", "Let him cook!"],
        "dialog": ["Wait, what did he say?", "Hmm interesting...",
                   "He's talking to someone!", "What's the plan here?"],
        "calm":   ["Just cruising along...", "Taking in the view...",
                   "Quiet moment...", "Chill vibes here..."]
    }
    return [
        {"slot": i+1, "start": s["start"], "end": s["end"],
         "text": FALLBACK[s["type"]][i % 4],
         "visual_type": s["type"]}
        for i, s in enumerate(slots)
    ]


# ============================================================
# STEP 7 — ElevenLabs TTS (Visual-type based speed)
# ============================================================
def generate_audio(segments, slots):
    print("🔊 [7] Generating TTS...")
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": ELEVENLABS_API_KEY
    }

    slot_speed_map = {round(s["start"], 2): s.get("voice_speed", 1.0) for s in slots}

    audio_files = []
    for idx, seg in enumerate(segments):
        text = seg.get("text", "").strip()
        if not text:
            continue

        target_dur = seg["end"] - seg["start"]
        seg_file = f"{SEGMENTS_DIR}/seg_{idx:03d}.mp3"

        visual_type = (seg.get("visual_type") or "").lower().strip()
        if visual_type in ("action", "dialog", "calm"):
            voice_speed = speed_for_type(visual_type)
        else:
            voice_speed = 1.0
            best_diff = 999
            for s_start, s_speed in slot_speed_map.items():
                diff = abs(s_start - seg["start"])
                if diff < best_diff:
                    best_diff = diff
                    voice_speed = s_speed

        voice_speed = max(VOICE_SPEED_MIN, min(VOICE_SPEED_MAX, voice_speed))

        data = {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.4,
                "similarity_boost": 0.75,
                "style": 0.5,
                "use_speaker_boost": True,
                "speed": voice_speed
            }
        }

        try:
            r = requests.post(url, json=data, headers=headers, timeout=60)
            if r.status_code == 200:
                with open(seg_file, "wb") as af:
                    af.write(r.content)

                actual = get_duration(seg_file)
                if actual > 0 and target_dur > 0:
                    tempo = actual / target_dur
                    tempo = max(1.0, min(ATEMPO_MAX, tempo))

                    if tempo > 1.01:
                        fit_file = f"{SEGMENTS_DIR}/seg_{idx:03d}_fit.mp3"
                        subprocess.run(
                            f"ffmpeg -y -i {seg_file} "
                            f"-filter:a atempo={tempo:.3f} {fit_file}",
                            shell=True,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL
                        )
                        final = fit_file if os.path.exists(fit_file) else seg_file
                    else:
                        final = seg_file

                    audio_files.append({
                        "file": final, "start": seg["start"],
                        "end": seg["end"], "text": text,
                        "visual_type": visual_type
                    })
                    print(f"   ✅ [{seg['start']:5.1f}s] speed={voice_speed:.2f} ({visual_type or 'signal'}) | {text[:50]}")
            elif r.status_code == 401:
                print("   ❌ 401 — ElevenLabs key galat!")
                break
            elif r.status_code == 429:
                print("   ⚠️ 429 — rate limit, waiting 3s...")
                time.sleep(3)
            else:
                print(f"   ❌ {r.status_code}: {r.text[:100]}")
        except Exception as e:
            print(f"   ⚠️ seg {idx}: {e}")

    print(f"✅ {len(audio_files)} audio segments\n")
    return audio_files


# ============================================================
# STEP 8 — Timed Audio
# ============================================================
def build_timed_audio(audio_files, vid_duration):
    print("🎼 [8] Building timed audio...")
    silent = f"{SEGMENTS_DIR}/silent_base.mp3"
    subprocess.run(
        f"ffmpeg -y -f lavfi -i anullsrc=r=44100:cl=stereo -t {vid_duration} "
        f"-q:a 9 -acodec libmp3lame {silent}",
        shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    inputs = ["-i", silent]
    parts = []
    mix_inputs = ["[0:a]"]

    for i, a in enumerate(audio_files, start=1):
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
        f"ffmpeg -y {' '.join(inputs)} "
        f'-filter_complex "{filter_complex}" '
        f"-map \"[out]\" -acodec libmp3lame -q:a 4 {final_audio}"
    )
    subprocess.run(cmd, shell=True, check=True)
    print("✅ Timed commentary built\n")
    return final_audio


# ============================================================
# STEP 9 — Final Merge with Ducking
# ============================================================
def merge_final(video_path, commentary_audio, out_path, audio_files):
    print("🎬 [9] Merging (duck during commentary)...")

    time_conditions = "+".join([
        f"between(t,{a['start']:.2f},{a['end']:.2f})"
        for a in audio_files
    ])

    volume_expr = f"if({time_conditions},{DUCK_VOLUME},1.0)"

    filter_complex = (
        f"[0:a]volume='{volume_expr}':eval=frame[bg];"
        f"[1:a]volume=1.4[vo];"
        f"[bg][vo]amix=inputs=2:duration=first:dropout_transition=0:"
        f"normalize=0,alimiter=limit=0.95[aout]"
    )

    cmd = (
        f'ffmpeg -y -i {video_path} -i {commentary_audio} '
        f'-filter_complex "{filter_complex}" '
        f'-map 0:v:0 -map "[aout]" -c:v copy -shortest {out_path}'
    )
    subprocess.run(cmd, shell=True, check=True)
    print(f"🔥 Final video ready: {out_path}\n")


# ============================================================
# FALLBACK — copy original clip
# ============================================================
def fallback_copy_original():
    try:
        subprocess.run(
            f"ffmpeg -y -i {FINAL_CLIP_PATH} -c copy {FINAL_DUBBED_VIDEO}",
            shell=True, check=True
        )
        print(f"✅ Original copied: {FINAL_DUBBED_VIDEO}")
        return True
    except Exception as e:
        print(f"❌ Fallback failed: {e}")
        return False


# ============================================================
# MAIN PIPELINE
# ============================================================
def main():
    print("=" * 60)
    print("🎙️ AI COMMENTARY DUBBER — Multi-Key + ON/OFF + Frame-Based Speed")
    print("=" * 60)
    print(f"📹 Input : {FINAL_CLIP_PATH}")
    print(f"📤 Output: {FINAL_DUBBED_VIDEO}")
    print(f"🎤 Voice : {VOICE_ID}")
    print(f"🎛️  Switch: COMMENTARY_ENABLED = {COMMENTARY_ENABLED}")
    print(f"🎮 Speed : {VOICE_SPEED_MIN} - {VOICE_SPEED_MAX} (auto, frame-based)")
    print(f"🖼️  Frames: {ANALYSIS_FRAMES} ({GRID_COLS}x{GRID_ROWS} grid, {CANVAS_W}x{CANVAS_H} 8K)")
    print(f"🤖 Model : openai/gpt-4o-mini (Free tier)")
    print("=" * 60 + "\n")

    # 🎛️ ON/OFF SWITCH
    if not COMMENTARY_ENABLED:
        print("🚫 Commentary is OFF — copying original clip...")
        if fallback_copy_original():
            sys.exit(0)
        else:
            sys.exit(1)

    # Env validation
    if not validate_env():
        print("⚠️ Falling back to original clip...")
        fallback_copy_original()
        sys.exit(0)

    vid_dur = get_duration(FINAL_CLIP_PATH)
    print(f"📹 Video duration: {vid_dur:.2f}s\n")

    try:
        extract_audio(FINAL_CLIP_PATH, AUDIO_PATH)
        srt_content = transcribe(AUDIO_PATH)
        slots = build_auto_slots(FINAL_CLIP_PATH, vid_dur, srt_content)
        slots = classify_slots_combined(FINAL_CLIP_PATH, slots, srt_content)
        build_analysis_grid(FINAL_CLIP_PATH, vid_dur, num_frames=ANALYSIS_FRAMES)
        segments = generate_full_script(slots, srt_content, ANALYSIS_GRID_PATH)

        if not segments:
            raise Exception("No segments generated")

        speeds = [s["voice_speed"] for s in slots]
        print(f"🎮 Final voice speeds (after GPT visual): "
              f"min={min(speeds):.2f} max={max(speeds):.2f} avg={sum(speeds)/len(speeds):.2f}\n")

        audio_files = generate_audio(segments, slots)
        if not audio_files:
            raise Exception("No audio files generated")

        final_audio = build_timed_audio(audio_files, vid_dur)
        merge_final(FINAL_CLIP_PATH, final_audio, FINAL_DUBBED_VIDEO, audio_files)

        print("=" * 60)
        print(f"🔥🔥 DONE! {FINAL_DUBBED_VIDEO}")
        print(f"📊 Slots: {len(slots)} | Segments: {len(audio_files)}")
        print("=" * 60)

        # 🎯 Push analysis images to GitHub
        commit_analysis_to_github()

        sys.exit(0)

    except Exception as e:
        print(f"\n❌ Commentary pipeline failed: {e}")
        print("⚠️ Falling back to original clip...")

        # Even if commentary fails, push images for debugging
        commit_analysis_to_github()

        if fallback_copy_original():
            sys.exit(0)
        else:
            sys.exit(1)


if __name__ == "__main__":
    main()