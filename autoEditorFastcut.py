"""
================================================================
AUTO EDITOR - VIRAL REEL STYLE (FINAL)
================================================================
- Preserves video length when content is good
- Inserts memes at exciting moments
- Adds SFX on action
- Loud background music
- Even dimensions (no FFMPEG error)
- Git pull before push
================================================================
"""

import os
import sys
import json
import math
import random
import base64
import argparse
import subprocess
import traceback
import time
from datetime import datetime

import cv2
import numpy as np
import librosa
from PIL import Image, ImageDraw, ImageFont

from moviepy.editor import (
    VideoFileClip, AudioFileClip, CompositeVideoClip,
    CompositeAudioClip, concatenate_videoclips, TextClip
)
import moviepy.video.fx.all as vfx

from openai import OpenAI


# ================================================================
# CONFIG
# ================================================================
BASE_DIR    = "FASTCUT"
TEMP_DIR    = os.path.join(BASE_DIR, "temp_frames")
MEME_DIR    = os.path.join(BASE_DIR, "memes")
SFX_DIR     = os.path.join(BASE_DIR, "sfx")
MUSIC_DIR   = os.path.join(BASE_DIR, "music")
GRID_DIR    = os.path.join(BASE_DIR, "grids")
DEBUG_DIR   = os.path.join(BASE_DIR, "debug")
OUTPUT_DIR  = os.path.join(BASE_DIR, "output")

OPENROUTER_MODEL = "openai/gpt-4o-mini"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Video output
ASPECT_RATIO = "9:16"
VIDEO_BITRATE = "16000k"
AUDIO_BITRATE = "320k"
VIDEO_CRF = 18
VIDEO_PRESET = "slow"

# ⭐ AUDIO VOLUMES
MUSIC_VOLUME = 0.5
SFX_VOLUME = 1.0
ORIGINAL_AUDIO_VOLUME = 0.8

# Meme
MEME_MIN_DURATION = 1.5
MEME_MAX_DURATION = 3.0
MEME_ALLOWED_EXT = (".mp4", ".mov", ".gif", ".webm")

# Speed
DEFAULT_SPEED = 1.0
MAX_SPEED = 1.5
MIN_SPEED = 0.7

# Cuts
ALLOW_CUTS = True
PRESERVE_GOOD = True
MIN_CLIP_DURATION = 0.5
TARGET_MIN_SEC = 20
TARGET_MAX_SEC = 90

# API
API_KEY_NAMES = [
    "OPENROUTER_API_KEY",
    "OPENROUTER_API_KEY_2",
    "OPENROUTER_API_KEY_3",
    "OPENROUTER_API_KEY_4",
    "OPENROUTER_API_KEY_5",
]
ATTEMPTS_PER_KEY = 2


# ================================================================
# LOGGING
# ================================================================
def log_step(title):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)

def log_ok(msg):    print(f"   ✅ {msg}")
def log_warn(msg):  print(f"   ⚠️  {msg}")
def log_err(msg):   print(f"   ❌ {msg}")
def log_info(msg):  print(f"   ℹ️  {msg}")


# ================================================================
# FOLDERS
# ================================================================
def ensure_folders():
    folders = [
        BASE_DIR, TEMP_DIR, GRID_DIR, DEBUG_DIR, OUTPUT_DIR,
        MEME_DIR,
        os.path.join(MEME_DIR, "shocked"),
        os.path.join(MEME_DIR, "funny"),
        os.path.join(MEME_DIR, "sad"),
        os.path.join(MEME_DIR, "victory"),
        os.path.join(MEME_DIR, "reaction"),
        os.path.join(MEME_DIR, "hype"),
        os.path.join(MEME_DIR, "fail"),
        os.path.join(MEME_DIR, "win"),
        SFX_DIR,
        os.path.join(SFX_DIR, "hype"),
        os.path.join(SFX_DIR, "dramatic"),
        os.path.join(SFX_DIR, "funny"),
        os.path.join(SFX_DIR, "victory"),
        os.path.join(SFX_DIR, "whoosh"),
        os.path.join(SFX_DIR, "impact"),
        os.path.join(SFX_DIR, "notification"),
        MUSIC_DIR,
    ]

    created = 0
    for f in folders:
        if not os.path.exists(f):
            os.makedirs(f, exist_ok=True)
            created += 1

    if created:
        log_ok(f"Created {created} new folders")
    else:
        log_ok(f"All {len(folders)} folders ready")

    for f in folders:
        if f == BASE_DIR:
            continue
        gitkeep = os.path.join(f, ".gitkeep")
        if not os.path.exists(gitkeep):
            try:
                with open(gitkeep, "w") as fh:
                    fh.write("")
            except Exception:
                pass


# ================================================================
# GIT
# ================================================================
def git_commit_folders():
    if not os.getenv("GITHUB_ACTIONS"):
        return
    try:
        subprocess.run(["git", "config", "user.email", "actions@github.com"],
                       check=True, timeout=10)
        subprocess.run(["git", "config", "user.name", "github-actions[bot]"],
                       check=True, timeout=10)
        subprocess.run(["git", "add", f"{BASE_DIR}/"], check=True, timeout=30)

        diff = subprocess.run(["git", "diff", "--cached", "--quiet"], timeout=30)
        if diff.returncode == 0:
            log_info("No changes to commit")
            return

        subprocess.run(["git", "commit", "-m",
                        "📁 Auto: Update FASTCUT [skip ci]"],
                       check=True, timeout=30)

        subprocess.run(["git", "pull", "--rebase", "--no-edit", "origin", "main"],
                       capture_output=True, text=True, timeout=60)

        push = subprocess.run(["git", "push"], capture_output=True,
                              text=True, timeout=60)
        if push.returncode == 0:
            log_ok("Structure pushed ✅")
    except Exception as e:
        log_warn(f"Git error: {e}")


# ================================================================
# VIDEO INFO
# ================================================================
def get_video_info(video_path):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise Exception(f"Video open nahi hua: {video_path}")
    fps = cap.get(cv2.CAP_PROP_FPS)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total / fps if fps > 0 else 0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    return {"duration": duration, "fps": fps, "width": w, "height": h, "total_frames": total}


# ================================================================
# FRAME INDEX
# ================================================================
def create_frame_index(video_path, fps=3):
    info = get_video_info(video_path)
    total = int(info["duration"] * fps)
    frames = [{"idx": i, "t": round(i / fps, 3)} for i in range(total)]
    return {
        "video_duration": info["duration"],
        "fps_sampling": fps,
        "total_frames": total,
        "frames": frames,
        "info": info
    }


# ================================================================
# GRIDS
# ================================================================
def create_grids(video_path, frame_index, output_dir, max_images=6):
    total_frames = frame_index["total_frames"]
    if total_frames == 0:
        return []

    num_grids = min(max_images, math.ceil(total_frames / 45))
    frames_per_grid = math.ceil(total_frames / num_grids)
    cols = math.ceil(math.sqrt(frames_per_grid * 1.15))
    rows = math.ceil(frames_per_grid / cols)
    thumb_size = max(150, min(2000 // cols, 300))

    log_info(f"Frames: {total_frames} | Grids: {num_grids} | Layout: {cols}x{rows}")

    cap = cv2.VideoCapture(video_path)
    paths = []

    for g in range(num_grids):
        start_idx = g * frames_per_grid
        end_idx = min(start_idx + frames_per_grid, total_frames)
        frames = []

        for i in range(start_idx, end_idx):
            f = frame_index["frames"][i]
            cap.set(cv2.CAP_PROP_POS_MSEC, f["t"] * 1000)
            ret, frame = cap.read()
            if not ret:
                continue

            h, w = frame.shape[:2]
            thumb_h = int(thumb_size * (h / w))
            tw = thumb_size if thumb_size % 2 == 0 else thumb_size - 1
            th = thumb_h if thumb_h % 2 == 0 else thumb_h - 1

            frame = cv2.resize(frame, (tw, th))
            img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            draw = ImageDraw.Draw(img)

            try:
                font = ImageFont.truetype(
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                    max(12, thumb_size // 12)
                )
            except Exception:
                font = ImageFont.load_default()

            ts = f"{int(f['t']//60):02d}:{f['t']%60:04.1f}"
            label = f"#{f['idx']} | {ts}"
            bbox = draw.textbbox((0, 0), label, font=font)
            pad = max(2, thumb_size // 50)
            draw.rectangle([pad, pad, 2 * pad + bbox[2], 2 * pad + bbox[3]], fill="black")
            draw.text((pad + 2, pad + 1), label, fill="yellow", font=font)
            frames.append(np.array(img))

        if not frames:
            continue

        th, tw = frames[0].shape[:2]
        grid = np.zeros((rows * th, cols * tw, 3), dtype=np.uint8)
        for i, f in enumerate(frames):
            r, c = i // cols, i % cols
            if r < rows:
                grid[r * th:(r + 1) * th, c * tw:(c + 1) * tw] = f

        out = os.path.join(output_dir, f"grid_{g + 1}.jpg")
        Image.fromarray(grid).save(out, quality=92)
        paths.append(out)
        size_kb = os.path.getsize(out) / 1024
        log_ok(f"grid_{g+1}.jpg ({grid.shape[1]}x{grid.shape[0]}px, {size_kb:.0f} KB)")

    cap.release()
    log_ok(f"📸 TOTAL GRIDS: {len(paths)}")
    return paths


# ================================================================
# TRANSCRIPT
# ================================================================
_WHISPER_MODEL = None

def get_whisper_model():
    global _WHISPER_MODEL
    if _WHISPER_MODEL is None:
        from faster_whisper import WhisperModel
        log_info("Loading whisper...")
        _WHISPER_MODEL = WhisperModel("base", device="cpu", compute_type="int8")
    return _WHISPER_MODEL


def get_transcript(video_path, use_whisper=True):
    if not use_whisper:
        log_info("Whisper skipped")
        return "No transcript"
    try:
        model = get_whisper_model()
        segments, info = model.transcribe(video_path)
        lines = [f"[{s.start:6.1f}s] {s.text.strip()}"
                 for s in segments if s.text.strip()]
        if not lines:
            log_warn("No speech detected")
            return "No speech"
        log_ok(f"{len(lines)} segments (lang: {info.language})")
        return "\n".join(lines)
    except Exception as e:
        log_err(f"Whisper error: {e}")
        return "No transcript"


# ================================================================
# SPIKES
# ================================================================
def get_spikes(video_path):
    log_info("Detecting audio spikes...")
    try:
        y, sr = librosa.load(video_path, sr=16000, mono=True)
        rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=512)[0]
        hop_sec = 512 / sr
        win = max(1, int(1 / hop_sec))
        per_sec = []
        for i in range(0, len(rms), win):
            chunk = rms[i:i + win]
            if len(chunk) > 0:
                per_sec.append(float(chunk.max()))
        if not per_sec:
            return "No spikes"
        threshold = float(np.percentile(per_sec, 75))
        spikes = [f"[{i:6.1f}s] RMS={v:.3f}" for i, v in enumerate(per_sec) if v > threshold]
        if not spikes:
            return "No spikes"
        log_ok(f"{len(spikes)} spikes detected")
        return "\n".join(spikes)
    except Exception as e:
        log_err(f"Spike error: {e}")
        return "No spikes"


# ================================================================
# MOODS
# ================================================================
def get_available_moods():
    memes, sfx, music = {}, {}, []

    if os.path.exists(MEME_DIR):
        for mood in os.listdir(MEME_DIR):
            p = os.path.join(MEME_DIR, mood)
            if os.path.isdir(p):
                files = [f for f in os.listdir(p)
                         if f.lower().endswith(MEME_ALLOWED_EXT)]
                if files:
                    memes[mood] = files

    if os.path.exists(SFX_DIR):
        for mood in os.listdir(SFX_DIR):
            p = os.path.join(SFX_DIR, mood)
            if os.path.isdir(p):
                files = [f for f in os.listdir(p)
                         if f.lower().endswith(('.mp3', '.wav', '.m4a', '.aac'))]
                if files:
                    sfx[mood] = files

    if os.path.exists(MUSIC_DIR):
        music = [f for f in os.listdir(MUSIC_DIR)
                 if f.lower().endswith(('.mp3', '.wav', '.m4a', '.aac'))]

    return memes, sfx, music


# ================================================================
# BUILD PROMPT — SMART LENGTH + MEMES + SFX
# ================================================================
def build_prompt(frame_index, grid_count, transcript, spikes, memes, sfx, music):
    frame_lines = [f"#{f['idx']}={f['t']}s" for f in frame_index["frames"][::3]]
    frame_list = "\n".join(frame_lines)
    source_dur = frame_index['video_duration']

    prompt = f"""You are a VIRAL REEL EDITOR. Make this gameplay entertaining.

VIDEO: {source_dur:.1f}s | Total frames: {frame_index['total_frames']} | FPS: {frame_index['fps_sampling']}

FRAME INDEX (use ONLY these frames):
{frame_list}

GRIDS: {grid_count} images. Each frame labeled "#idx | MM:SS.S".

TRANSCRIPT:
{transcript}

AUDIO SPIKES (loud = action):
{spikes}

AVAILABLE:
- Meme moods: {list(memes.keys())}
- SFX moods: {list(sfx.keys())}
- Music: {music}

╔══════════════════════════════════════════════════════════════╗
║  🎯 PRIMARY RULE: VIDEO LENGTH                                ║
╚══════════════════════════════════════════════════════════════╝

**If content is GOOD (fights, action, kills):**
  → KEEP SAME LENGTH (42s source → 40-42s output)
  → DO NOT cut. Preserve everything.
  → Only insert memes + SFX

**If content is MIXED (some boring):**
  → Cut ONLY boring parts (menus, loading, idle)
  → Target: 70-90% of source (42s → 30-38s)

**If content is BORING (nothing happening):**
  → Cut aggressively
  → Target: 40-60% of source (42s → 17-25s)

⚠️ DEFAULT: Assume content is GOOD. Preserve full video.

╔══════════════════════════════════════════════════════════════╗
║  🎭 MEME INSERTION RULES                                      ║
╚══════════════════════════════════════════════════════════════╝

Insert 3-6 memes at exciting moments:
- Kill / win → mood: "victory" or "win"
- Death / fail → mood: "fail" or "sad"
- Funny moment → mood: "funny" or "reaction"
- Surprise / shock → mood: "shocked"
- Hype / action → mood: "hype"

Meme duration: 1.5-3 seconds.
Insert memes BETWEEN video clips (never overlap).

╔══════════════════════════════════════════════════════════════╗
║  🔊 SFX RULES                                                 ║
╚══════════════════════════════════════════════════════════════╝

Add "sfx_mood" field to KEEP edits on action moments:
- Kill / punch → sfx_mood: "impact"
- Big moment → sfx_mood: "dramatic"
- Whoosh / transition → sfx_mood: "whoosh"
- Funny → sfx_mood: "funny"
- Victory → sfx_mood: "victory"
- Hype → sfx_mood: "hype"

Add 3-5 SFX total.

╔══════════════════════════════════════════════════════════════╗
║  ⚡ SPEED                                                     ║
╚══════════════════════════════════════════════════════════════╝

- Normal: 1.0x (use this for MOST clips)
- Slightly boring: 1.2-1.5x
- Clutch moments: 0.7x (slow-mo)

╔══════════════════════════════════════════════════════════════╗
║  📋 OUTPUT FORMAT                                             ║
╚══════════════════════════════════════════════════════════════╝

Return ONLY valid JSON (no markdown, no code fences):

{{
  "content_quality": "good|mixed|boring",
  "reasoning": "Brief explanation",
  "target_duration": {int(source_dur)},
  "aspect_ratio": "{ASPECT_RATIO}",
  "bg_music": "<filename from AVAILABLE music>",
  "edits": [
    {{"start_frame": 0, "end_frame": 15, "speed": 1.0, "reason": "Intro gameplay"}},
    {{"insert_meme": "auto", "meme_mood": "funny", "reason": "Funny moment"}},
    {{"start_frame": 15, "end_frame": 30, "speed": 1.0, "sfx_mood": "impact", "reason": "Kill"}},
    {{"insert_meme": "auto", "meme_mood": "shocked", "reason": "Surprise"}},
    {{"start_frame": 30, "end_frame": 90, "speed": 1.0, "reason": "Main action"}},
    {{"insert_meme": "auto", "meme_mood": "victory", "reason": "Win"}},
    {{"start_frame": 90, "end_frame": 126, "speed": 1.0, "sfx_mood": "victory", "reason": "Finale"}}
  ]
}}

REMINDER:
- If content is GOOD → output ~= source length
- Insert memes BETWEEN clips (not overlapping)
- Add sfx_mood to KEEP edits
- Do NOT cut exciting parts
"""
    return prompt


# ================================================================
# JSON EXTRACTOR
# ================================================================
def extract_json(text):
    if not text:
        raise ValueError("Empty AI response")
    text = text.strip()

    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) >= 2:
            text = parts[1]
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found")

    json_str = text[start:end + 1]

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        cleaned = json_str.replace("'", '"')
        try:
            return json.loads(cleaned)
        except Exception:
            raise ValueError(f"JSON parse failed: {e}")


# ================================================================
# API KEYS
# ================================================================
def get_api_keys():
    keys = []
    for name in API_KEY_NAMES:
        val = os.getenv(name, "").strip()
        if val:
            keys.append((name, val))
    return keys


# ================================================================
# AI ANALYZE
# ================================================================
def ai_analyze(frame_index, grid_paths, transcript, spikes, memes, sfx, music):
    api_keys = get_api_keys()
    if not api_keys:
        raise Exception("No OPENROUTER_API_KEY found!")

    log_info(f"Found {len(api_keys)} API key(s)")

    images = []
    for p in grid_paths:
        with open(p, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        images.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
        })
    log_info(f"Prepared {len(images)} grid images")

    prompt = build_prompt(frame_index, len(grid_paths),
                          transcript, spikes, memes, sfx, music)
    log_info(f"Prompt: {len(prompt)} chars")

    last_error = None
    total_attempts = 0

    for key_idx, (key_name, key_val) in enumerate(api_keys, 1):
        for attempt in range(1, ATTEMPTS_PER_KEY + 1):
            total_attempts += 1
            print(f"\n   🔄 Attempt #{total_attempts}: Key #{key_idx} ({key_name}) try {attempt}/{ATTEMPTS_PER_KEY}")

            try:
                client = OpenAI(
                    api_key=key_val,
                    base_url=OPENROUTER_BASE_URL,
                    default_headers={
                        "HTTP-Referer": "https://github.com/Prembty12/premx-editor",
                        "X-Title": "Auto Video Editor",
                    }
                )

                t_start = time.time()
                response = client.chat.completions.create(
                    model=OPENROUTER_MODEL,
                    messages=[{
                        "role": "user",
                        "content": [{"type": "text", "text": prompt}] + images
                    }],
                    max_tokens=4000,
                    temperature=0.7
                )
                elapsed = time.time() - t_start

                text = response.choices[0].message.content
                log_ok(f"Response in {elapsed:.2f}s ({len(text)} chars)")

                result = extract_json(text)

                if result.get("aspect_ratio") not in ("9:16", "1:1", "4:5"):
                    result["aspect_ratio"] = ASPECT_RATIO

                meme_count = sum(1 for e in result.get("edits", []) if "insert_meme" in e)
                sfx_count = sum(1 for e in result.get("edits", []) if "sfx_mood" in e)
                keep_count = sum(1 for e in result.get("edits", [])
                                 if not e.get("remove") and "insert_meme" not in e)

                log_ok(f"Quality: {result.get('content_quality', '?')}")
                log_ok(f"Reasoning: {result.get('reasoning', '-')}")
                log_ok(f"Target: {result.get('target_duration')}s")
                log_ok(f"Edits: {len(result.get('edits', []))} "
                       f"[KEEP: {keep_count}, MEME: {meme_count}, SFX: {sfx_count}]")
                return result

            except (json.JSONDecodeError, ValueError) as e:
                last_error = str(e)
                log_warn(f"Parse failed: {e}")
                time.sleep(1)
                continue
            except Exception as e:
                last_error = str(e)
                err_str = str(e).lower()
                if any(x in err_str for x in ["rate", "quota", "limit", "auth", "401", "403", "429"]):
                    log_warn(f"Key issue → next key")
                    break
                log_warn(f"Error: {e}")
                time.sleep(2)
                continue

    raise Exception(f"All keys failed. Last: {last_error}")


# ================================================================
# VERIFY
# ================================================================
def verify_and_convert(ai_json, frame_index):
    fps_sampling = frame_index["fps_sampling"]
    total_frames = frame_index["total_frames"]

    if total_frames == 0:
        ai_json["edits"] = []
        return ai_json

    valid = set(range(total_frames))
    verified = []

    for edit in ai_json.get("edits", []):
        if "insert_meme" in edit:
            verified.append(edit)
            continue

        if "start_frame" in edit and "end_frame" in edit:
            sf = edit["start_frame"]
            ef = edit["end_frame"]

            if sf not in valid:
                sf = min(valid, key=lambda x: abs(x - sf))
            if ef not in valid:
                ef = min(valid, key=lambda x: abs(x - ef))

            if sf >= ef:
                sf, ef = min(sf, ef), max(sf, ef)

            edit["start_frame"] = sf
            edit["end_frame"] = ef
            edit["start"] = round(sf / fps_sampling, 3)
            edit["end"] = round(ef / fps_sampling, 3)

            if not edit.get("remove") and (edit["end"] - edit["start"]) < MIN_CLIP_DURATION:
                continue

        verified.append(edit)

    ai_json["edits"] = verified
    log_ok(f"{len(verified)} edits verified")
    return ai_json


# ================================================================
# DEBUG LOG
# ================================================================
def save_debug_log(ai_json, frame_index):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    with open(os.path.join(DEBUG_DIR, f"edits_{ts}.json"), "w") as f:
        json.dump(ai_json, f, indent=2)

    lines = ["=" * 70, f"AI DECISIONS - {ts}", "=" * 70]
    lines.append(f"Quality: {ai_json.get('content_quality')}")
    lines.append(f"Reasoning: {ai_json.get('reasoning')}")
    lines.append(f"Target: {ai_json.get('target_duration')}s")
    lines.append("")

    for i, edit in enumerate(ai_json.get("edits", []), 1):
        lines.append(f"--- EDIT #{i} ---")
        if "insert_meme" in edit:
            lines.append(f"  🎭 MEME | Mood: {edit.get('meme_mood')}")
        elif edit.get("remove"):
            lines.append(f"  ✂️  CUT | Frames: {edit['start_frame']}-{edit['end_frame']}")
        else:
            lines.append(f"  🎬 KEEP | Frames: {edit['start_frame']}-{edit['end_frame']} "
                         f"| Speed: {edit.get('speed', 1.0)}x")
            if "sfx_mood" in edit:
                lines.append(f"     🔊 SFX: {edit['sfx_mood']}")
        lines.append(f"  Reason: {edit.get('reason', '-')}")

    with open(os.path.join(DEBUG_DIR, f"debug_{ts}.txt"), "w") as f:
        f.write("\n".join(lines))

    print("\n" + "\n".join(lines))
    return ts


# ================================================================
# PICKERS
# ================================================================
def pick_meme(mood):
    mood_dir = os.path.join(MEME_DIR, mood)
    if os.path.exists(mood_dir):
        files = [f for f in os.listdir(mood_dir) if f.lower().endswith(MEME_ALLOWED_EXT)]
        if files:
            return os.path.join(mood_dir, random.choice(files))

    for root, dirs, files in os.walk(MEME_DIR):
        vids = [f for f in files if f.lower().endswith(MEME_ALLOWED_EXT)]
        if vids:
            return os.path.join(root, random.choice(vids))
    return None


def pick_sfx(mood):
    mood_dir = os.path.join(SFX_DIR, mood)
    if os.path.exists(mood_dir):
        files = [f for f in os.listdir(mood_dir)
                 if f.lower().endswith(('.mp3', '.wav', '.m4a', '.aac'))]
        if files:
            return os.path.join(mood_dir, random.choice(files))

    for root, dirs, files in os.walk(SFX_DIR):
        sfx = [f for f in files if f.lower().endswith(('.mp3', '.wav', '.m4a', '.aac'))]
        if sfx:
            return os.path.join(root, random.choice(sfx))
    return None


# ================================================================
# ASPECT (even dimensions)
# ================================================================
def apply_aspect(clip, ratio="9:16"):
    w, h = clip.size

    def make_even(n):
        n = int(n)
        return n if n % 2 == 0 else n - 1

    if ratio == "9:16":
        tw = h * (9 / 16)
        if tw <= w:
            return clip.fx(vfx.crop, x_center=w / 2, y_center=h / 2,
                          width=make_even(tw), height=make_even(h))
        th = w * (16 / 9)
        return clip.fx(vfx.crop, x_center=w / 2, y_center=h / 2,
                      width=make_even(w), height=make_even(th))
    elif ratio == "1:1":
        m = make_even(min(w, h))
        return clip.fx(vfx.crop, x_center=w / 2, y_center=h / 2, width=m, height=m)
    elif ratio == "4:5":
        tw = h * (4 / 5)
        if tw <= w:
            return clip.fx(vfx.crop, x_center=w / 2, y_center=h / 2,
                          width=make_even(tw), height=make_even(h))
        th = w * (5 / 4)
        return clip.fx(vfx.crop, x_center=w / 2, y_center=h / 2,
                      width=make_even(w), height=make_even(th))
    return clip


# ================================================================
# BUILD REEL
# ================================================================
def build_reel(video_path, ai_json, output_path):
    log_info("Building reel...")

    main = VideoFileClip(video_path)
    source_fps = main.fps if main.fps else 30
    source_duration = float(main.duration)
    aspect = ai_json.get("aspect_ratio", ASPECT_RATIO)

    clips = []
    sfx_data = []
    current_time = 0.0
    meme_count = 0
    sfx_count = 0

    log_info(f"Source: {source_duration:.2f}s @ {source_fps:.2f}fps")

    for edit in ai_json.get("edits", []):

        # ══════════════════════════════════════════════
        # MEME INSERT
        # ══════════════════════════════════════════════
        if "insert_meme" in edit:
            mood = edit.get("meme_mood", "funny")
            meme_path = pick_meme(mood)

            if meme_path:
                try:
                    meme = VideoFileClip(meme_path)
                    original_dur = meme.duration

                    target_d = min(max(original_dur, MEME_MIN_DURATION), MEME_MAX_DURATION)

                    if original_dur > target_d:
                        meme = meme.subclip(0, target_d)
                    elif original_dur < MEME_MIN_DURATION:
                        loops = int(MEME_MIN_DURATION / original_dur) + 1
                        meme = concatenate_videoclips([meme] * loops).subclip(0, MEME_MIN_DURATION)

                    meme = apply_aspect(meme, aspect)
                    clips.append(meme)
                    current_time += meme.duration
                    meme_count += 1

                    # Add SFX on meme
                    meme_sfx = pick_sfx("whoosh")
                    if meme_sfx:
                        sfx_data.append((current_time - meme.duration, meme_sfx, 0.5))
                        sfx_count += 1

                    log_ok(f"🎭 Meme #{meme_count} ({mood}) {meme.duration:.1f}s "
                           f"[orig={original_dur:.1f}s]")

                except Exception as e:
                    log_err(f"Meme error: {e}")
            else:
                log_warn(f"No meme for mood: {mood}")
            continue

        # ══════════════════════════════════════════════
        # CUT
        # ══════════════════════════════════════════════
        if edit.get("remove", False):
            log_info(f"✂️  Cut: frames {edit.get('start_frame')}-{edit.get('end_frame')}")
            continue

        # ══════════════════════════════════════════════
        # KEEP VIDEO
        # ══════════════════════════════════════════════
        start = edit.get("start")
        end = edit.get("end")
        if start is None or end is None:
            continue

        try:
            start = max(0.0, min(start, source_duration))
            end = max(start + 0.05, min(end, source_duration))

            seg = main.subclip(start, end)

            speed = edit.get("speed", DEFAULT_SPEED)
            speed = max(MIN_SPEED, min(MAX_SPEED, speed))
            if speed != 1.0:
                seg = seg.fx(vfx.speedx, speed)

            seg = apply_aspect(seg, aspect)

            # SFX attached to this segment
            sfx_mood = edit.get("sfx_mood")
            if sfx_mood:
                sfx_path = pick_sfx(sfx_mood)
                if sfx_path:
                    sfx_data.append((current_time, sfx_path, SFX_VOLUME))
                    sfx_count += 1
                    log_ok(f"🔊 SFX ({sfx_mood}) at {current_time:.2f}s")

            clips.append(seg)
            current_time += seg.duration
            log_ok(f"🎬 Keep: {start:.2f}-{end:.2f}s @ {speed}x")

        except Exception as e:
            log_err(f"Clip error: {e}")

    if not clips:
        log_err("No clips! Aborting.")
        return None

    # ══════════════════════════════════════════════════
    # CONCATENATE
    # ══════════════════════════════════════════════════
    final = concatenate_videoclips(clips, method="compose")
    video_duration = float(final.duration)
    log_info(f"Video duration: {video_duration:.2f}s")
    log_info(f"Total: {meme_count} memes, {sfx_count} SFX")

    # ══════════════════════════════════════════════════
    # AUDIO MIX
    # ══════════════════════════════════════════════════
    audio_tracks = []

    # 1. Original audio
    if final.audio:
        orig = final.audio.volumex(ORIGINAL_AUDIO_VOLUME)
        audio_tracks.append(orig)
        log_info(f"Original audio: {ORIGINAL_AUDIO_VOLUME}x")

    # 2. SFX
    for start_t, sfx_path, vol in sfx_data:
        try:
            sfx = AudioFileClip(sfx_path)
            remaining = video_duration - start_t
            if remaining <= 0.05:
                continue
            if sfx.duration > remaining:
                sfx = sfx.subclip(0, remaining)
            sfx = sfx.set_start(start_t).volumex(vol)
            audio_tracks.append(sfx)
        except Exception as e:
            log_warn(f"SFX error: {e}")

    # 3. Background music
    if "bg_music" in ai_json:
        mpath = os.path.join(MUSIC_DIR, ai_json["bg_music"])
        if os.path.exists(mpath):
            try:
                music = AudioFileClip(mpath).volumex(MUSIC_VOLUME)
                if music.duration > video_duration:
                    music = music.subclip(0, video_duration)
                else:
                    music = music.fx(vfx.loop, duration=video_duration)
                audio_tracks.append(music)
                log_ok(f"🎵 Music: {ai_json['bg_music']} @ {MUSIC_VOLUME}x")
            except Exception as e:
                log_warn(f"Music error: {e}")

    if audio_tracks:
        composite = CompositeAudioClip(audio_tracks)
        if composite.duration > video_duration:
            composite = composite.subclip(0, video_duration)
        final = final.set_audio(composite)
        log_ok(f"Audio mixed: {len(audio_tracks)} tracks")

    final = final.set_duration(video_duration)

    # ══════════════════════════════════════════════════
    # FORCE EVEN DIMENSIONS
    # ══════════════════════════════════════════════════
    try:
        w, h = final.size
        w_even = w if w % 2 == 0 else w - 1
        h_even = h if h % 2 == 0 else h - 1
        if w != w_even or h != h_even:
            log_warn(f"Resizing {w}x{h} → {w_even}x{h_even}")
            final = final.resize((w_even, h_even))
        else:
            log_info(f"Dimensions OK: {w}x{h}")
    except Exception as e:
        log_warn(f"Even-check error: {e}")

    # ══════════════════════════════════════════════════
    # WRITE
    # ══════════════════════════════════════════════════
    log_info(f"Writing: {VIDEO_BITRATE}, CRF={VIDEO_CRF}, preset={VIDEO_PRESET}")

    final.write_videofile(
        output_path,
        codec="libx264",
        audio_codec="aac",
        audio_bitrate=AUDIO_BITRATE,
        bitrate=VIDEO_BITRATE,
        fps=source_fps,
        preset=VIDEO_PRESET,
        threads=4,
        ffmpeg_params=[
            "-crf", str(VIDEO_CRF),
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart"
        ],
        verbose=False,
        logger=None
    )

    log_ok(f"Final: {output_path} ({final.duration:.2f}s)")
    return output_path


# ================================================================
# MAIN
# ================================================================
def main():
    parser = argparse.ArgumentParser(description="Auto Video Editor")
    parser.add_argument("--video", default=os.path.join(TEMP_DIR, "gameplay.mp4"))
    parser.add_argument("--fps", type=int, default=3)
    parser.add_argument("--grids", type=int, default=6)
    parser.add_argument("--whisper", default="true")
    args = parser.parse_args()

    print("\n")
    print("╔" + "═" * 68 + "╗")
    print("║" + " " * 12 + "🎬 AUTO EDITOR - VIRAL REEL MODE" + " " * 24 + "║")
    print("╚" + "═" * 68 + "╝")

    ensure_folders()
    git_commit_folders()

    log_info(f"Video: {args.video}")
    log_info(f"FPS: {args.fps} | Grids: {args.grids} | Whisper: {args.whisper}")

    if not os.path.exists(args.video):
        log_err(f"Video not found: {args.video}")
        sys.exit(1)

    api_keys = get_api_keys()
    if not api_keys:
        log_err("No API keys found!")
        sys.exit(1)
    log_info(f"API keys: {len(api_keys)}")

    use_whisper = str(args.whisper).lower() == "true"

    # STEP 1
    log_step("STEP 1: Video Info")
    info = get_video_info(args.video)
    log_ok(f"Duration: {info['duration']:.1f}s")
    log_ok(f"Resolution: {info['width']}x{info['height']}")
    log_ok(f"FPS: {info['fps']:.2f}")

    # STEP 2
    log_step("STEP 2: Frame Index")
    frame_index = create_frame_index(args.video, args.fps)
    log_ok(f"Total frames: {frame_index['total_frames']}")

    # STEP 3
    log_step("STEP 3: Grid Generation")
    grids = create_grids(args.video, frame_index, GRID_DIR, args.grids)
    log_ok(f"{len(grids)} grids created")

    # STEP 4
    log_step("STEP 4: Transcript")
    transcript = get_transcript(args.video, use_whisper)

    # STEP 5
    log_step("STEP 5: Spike Detection")
    spikes = get_spikes(args.video)

    # STEP 6
    log_step("STEP 6: Assets Scan")
    memes, sfx, music = get_available_moods()
    log_info(f"Memes: {list(memes.keys())}")
    log_info(f"SFX: {list(sfx.keys())}")
    log_info(f"Music: {len(music)} files")

    # STEP 7
    log_step("STEP 7: AI Analysis")
    ai_json = ai_analyze(frame_index, grids, transcript, spikes, memes, sfx, music)

    # STEP 8
    log_step("STEP 8: Verify")
    ai_json = verify_and_convert(ai_json, frame_index)

    # STEP 9
    log_step("STEP 9: Debug Log")
    save_debug_log(ai_json, frame_index)

    # STEP 10
    log_step("STEP 10: Build Reel")
    output = os.path.join(OUTPUT_DIR, "final_reel.mp4")
    build_reel(args.video, ai_json, output)

    log_step("🎉 DONE!")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log_err(f"FATAL: {e}")
        traceback.print_exc()
        sys.exit(1)
