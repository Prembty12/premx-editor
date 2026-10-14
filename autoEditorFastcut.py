"""
================================================================
AUTO EDITOR - OpenRouter Multi-Key Version (PRODUCTION FINAL)
================================================================
- 5 API keys with auto-retry (2 attempts each = 10 total)
- Smart prompt: preserves good content, only cuts boring
- High quality output (16 Mbps, CRF 18, near-lossless)
- Duration lock — no freeze
- Detailed terminal debugging (JSON, retry, API)
- MoviePy 1.0.3 compatible
- Whisper cached
- All folders inside FASTCUT/
- Auto git-commit FASTCUT structure (in GitHub Actions)
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
OPENROUTER_MODEL = "openai/gpt-4o-mini"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# ---- BASE WORK DIR (sab kuch iske andar) ----
BASE_DIR    = "FASTCUT"
INPUT_DIR   = os.path.join(BASE_DIR, "input")
TEMP_DIR    = os.path.join(BASE_DIR, "temp_frames")
MEME_DIR    = os.path.join(BASE_DIR, "memes")
SFX_DIR     = os.path.join(BASE_DIR, "sfx")
MUSIC_DIR   = os.path.join(BASE_DIR, "music")
GRID_DIR    = os.path.join(BASE_DIR, "grids")
DEBUG_DIR   = os.path.join(BASE_DIR, "debug")
OUTPUT_DIR  = os.path.join(BASE_DIR, "output")


# ================================================================
# MULTI API KEYS
# ================================================================
def get_api_keys():
    keys = []
    for i in range(1, 6):
        env_name = "OPENROUTER_API_KEY" if i == 1 else f"OPENROUTER_API_KEY_{i}"
        val = os.getenv(env_name, "").strip()
        if val:
            keys.append((env_name, val))
    return keys


# ================================================================
# GLOBAL CACHE
# ================================================================
_WHISPER_MODEL = None


# ================================================================
# LOGGING
# ================================================================
def log_step(title):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def log_ok(msg):
    print(f"   ✅ {msg}")


def log_warn(msg):
    print(f"   ⚠️  {msg}")


def log_err(msg):
    print(f"   ❌ {msg}")


def log_info(msg):
    print(f"   ℹ️  {msg}")


# ================================================================
# AUTO-CREATE FOLDERS (INSIDE FASTCUT/)
# ================================================================
def ensure_folders():
    """Sab folders FASTCUT/ ke andar auto-create karo."""
    folders = [
        BASE_DIR, INPUT_DIR, TEMP_DIR, GRID_DIR, DEBUG_DIR, OUTPUT_DIR,
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

    created, existed = [], []
    for f in folders:
        if os.path.exists(f):
            existed.append(f)
        else:
            os.makedirs(f, exist_ok=True)
            created.append(f)

    if created:
        log_ok(f"Created {len(created)} new folders inside '{BASE_DIR}/':")
        for f in created:
            print(f"      📁 {f}")
    else:
        log_ok(f"All {len(folders)} folders already exist inside '{BASE_DIR}/'")

    if existed:
        log_info(f"{len(existed)} folders already existed")

    _drop_gitkeep_files(folders)
    _drop_folder_readmes()


def _drop_gitkeep_files(folders):
    count = 0
    for folder in folders:
        if not os.path.isdir(folder) or folder == BASE_DIR:
            continue
        path = os.path.join(folder, ".gitkeep")
        if not os.path.exists(path):
            try:
                with open(path, "w") as f:
                    f.write("")
                count += 1
            except Exception:
                pass
    if count > 0:
        log_ok(f"Dropped {count} .gitkeep files (for git tracking)")


def _drop_folder_readmes():
    readmes = {
        os.path.join(MEME_DIR, "shocked"):  "Shocked reaction memes\nFormats: .mp4, .mov, .gif, .webm",
        os.path.join(MEME_DIR, "funny"):    "Funny memes\nFormats: .mp4, .mov, .gif, .webm",
        os.path.join(MEME_DIR, "sad"):      "Sad memes\nFormats: .mp4, .mov, .gif, .webm",
        os.path.join(MEME_DIR, "victory"):  "Victory memes\nFormats: .mp4, .mov, .gif, .webm",
        os.path.join(MEME_DIR, "reaction"): "General reaction memes\nFormats: .mp4, .mov, .gif, .webm",
        os.path.join(MEME_DIR, "hype"):     "Hype memes\nFormats: .mp4, .mov, .gif, .webm",
        os.path.join(MEME_DIR, "fail"):     "Fail memes\nFormats: .mp4, .mov, .gif, .webm",
        os.path.join(MEME_DIR, "win"):      "Win memes\nFormats: .mp4, .mov, .gif, .webm",
        os.path.join(SFX_DIR, "hype"):         "Hype SFX\nFormats: .mp3, .wav, .m4a, .aac",
        os.path.join(SFX_DIR, "dramatic"):     "Dramatic SFX\nFormats: .mp3, .wav, .m4a, .aac",
        os.path.join(SFX_DIR, "funny"):        "Funny SFX\nFormats: .mp3, .wav, .m4a, .aac",
        os.path.join(SFX_DIR, "victory"):      "Victory SFX\nFormats: .mp3, .wav, .m4a, .aac",
        os.path.join(SFX_DIR, "whoosh"):       "Whoosh SFX\nFormats: .mp3, .wav, .m4a, .aac",
        os.path.join(SFX_DIR, "impact"):       "Impact SFX\nFormats: .mp3, .wav, .m4a, .aac",
        os.path.join(SFX_DIR, "notification"): "Notification SFX\nFormats: .mp3, .wav, .m4a, .aac",
        MUSIC_DIR:  "Background music",
        INPUT_DIR:  "Raw input videos",
        OUTPUT_DIR: "Final reels",
        GRID_DIR:   "Frame grid images",
        DEBUG_DIR:  "AI decision logs",
        TEMP_DIR:   "Temp working directory",
    }
    for folder, text in readmes.items():
        if not os.path.exists(folder):
            continue
        items = [f for f in os.listdir(folder) if f not in ("README.txt", ".gitkeep")]
        if items:
            continue
        path = os.path.join(folder, "README.txt")
        if os.path.exists(path):
            continue
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"📁 {folder}\n\n{text}\n\nAuto-managed folder.\n")
        except Exception:
            pass


# ================================================================
# AUTO-COMMIT FASTCUT STRUCTURE TO GIT
# ================================================================
def git_commit_folders():
    if not os.getenv("GITHUB_ACTIONS"):
        log_info("Not in GitHub Actions — skipping git commit")
        return

    log_info("Committing FASTCUT structure to git...")
    try:
        subprocess.run(["git", "config", "user.email", "actions@github.com"], check=True, timeout=10)
        subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True, timeout=10)
        subprocess.run(["git", "add", f"{BASE_DIR}/"], check=True, timeout=30)

        diff = subprocess.run(["git", "diff", "--cached", "--quiet"], timeout=30)
        if diff.returncode == 0:
            log_info("No changes to commit (folders already tracked)")
            return

        subprocess.run(
            ["git", "commit", "-m", "📁 Auto: Update FASTCUT folder structure [skip ci]"],
            check=True, timeout=30
        )
        push = subprocess.run(["git", "push"], capture_output=True, text=True, timeout=60)
        if push.returncode == 0:
            log_ok("FASTCUT structure committed & pushed ✅")
        else:
            log_warn(f"Push failed: {push.stderr[:200]}")
    except Exception as e:
        log_warn(f"Git commit error: {e}")


# ================================================================
# 1. VIDEO INFO
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
# 2. FRAME INDEX
# ================================================================
def create_frame_index(video_path, frames_per_sec=3):
    info = get_video_info(video_path)
    duration = info["duration"]
    total_frames = int(duration * frames_per_sec)
    frames = [{"idx": i, "t": round(i / frames_per_sec, 3)} for i in range(total_frames)]
    return {
        "video_duration": duration,
        "fps_sampling": frames_per_sec,
        "total_frames": total_frames,
        "frames": frames,
        "info": info
    }


# ================================================================
# 3. GRIDS
# ================================================================
def create_grids(video_path, frame_index, output_dir, max_images=6):
    total_frames = frame_index["total_frames"]
    if total_frames == 0:
        log_warn("No frames to grid")
        return []

    num_grids = min(max_images, math.ceil(total_frames / 45))
    frames_per_grid = math.ceil(total_frames / num_grids)
    cols = math.ceil(math.sqrt(frames_per_grid * 1.15))
    rows = math.ceil(frames_per_grid / cols)
    thumb_size = max(150, min(2000 // cols, 300))

    log_info(f"Total frames: {total_frames}")
    log_info(f"Grids: {num_grids}")
    log_info(f"Frames/grid: {frames_per_grid}")
    log_info(f"Layout: {cols}x{rows}")

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
            frame = cv2.resize(frame, (thumb_size, thumb_h))
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
        log_ok(f"{out} ({grid.shape[1]}x{grid.shape[0]}px)")

    cap.release()
    return paths


# ================================================================
# 4. TRANSCRIPT
# ================================================================
def get_whisper_model():
    global _WHISPER_MODEL
    if _WHISPER_MODEL is None:
        from faster_whisper import WhisperModel
        log_info("Loading whisper model (first time)...")
        _WHISPER_MODEL = WhisperModel("base", device="cpu", compute_type="int8")
    return _WHISPER_MODEL


def get_transcript(video_path, use_whisper=True):
    if not use_whisper:
        log_info("Whisper skipped")
        return "No transcript"
    try:
        model = get_whisper_model()
        log_info("Transcribing...")
        segments, info = model.transcribe(video_path)
        lines = [f"[{s.start:6.1f}s] {s.text.strip()}" for s in segments if s.text.strip()]
        if not lines:
            log_warn("No speech detected")
            return "No speech"
        log_ok(f"{len(lines)} segments (lang: {info.language})")
        return "\n".join(lines)
    except Exception as e:
        log_err(f"Whisper error: {e}")
        return "No transcript"


# ================================================================
# 5. SPIKES
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
        threshold = float(np.percentile(per_sec, 80))
        spikes = [f"[{i:6.1f}s] RMS={v:.3f}" for i, v in enumerate(per_sec) if v > threshold]
        if not spikes:
            return "No spikes"
        log_ok(f"{len(spikes)} spikes detected")
        return "\n".join(spikes)
    except Exception as e:
        log_err(f"Spike error: {e}")
        return "No spikes"


# ================================================================
# 6. MOODS
# ================================================================
def get_available_moods():
    memes, sfx, music = {}, {}, []

    if os.path.exists(MEME_DIR):
        for mood in os.listdir(MEME_DIR):
            p = os.path.join(MEME_DIR, mood)
            if os.path.isdir(p):
                files = [f for f in os.listdir(p)
                         if f.lower().endswith(('.mp4', '.mov', '.gif', '.webm'))]
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
# 7. BUILD PROMPT (SMART LENGTH DECISION)
# ================================================================
def build_prompt(frame_index, grid_count, transcript, spikes, memes, sfx, music):
    frame_lines = [f"#{f['idx']}={f['t']}s" for f in frame_index["frames"][::3]]
    frame_list = "\n".join(frame_lines)
    source_dur = frame_index['video_duration']

    prompt = f"""You are a PROFESSIONAL viral gaming editor. Your job is to make the video BETTER, not shorter.

VIDEO INFO:
- Duration: {source_dur:.1f}s
- Sampling: {frame_index['fps_sampling']}fps | Total frames: {frame_index['total_frames']}

FRAME INDEX (use ONLY these):
{frame_list}

GRIDS: {grid_count} images with "#idx | MM:SS.S" labels.

TRANSCRIPT:
{transcript}

AUDIO SPIKES (loud moments = hype):
{spikes}

AVAILABLE:
- Meme moods: {list(memes.keys())}
- SFX moods: {list(sfx.keys())}
- Music: {music}

============================================================
🎯 YOUR PRIMARY DECISION: ANALYZE CONTENT QUALITY
============================================================

Step 1: Watch the frames/grids carefully.
Step 2: Classify EVERY second of the video into 2 buckets:

  🟢 GOOD CONTENT (KEEP AT 1.0x speed):
     - Fights, action, kills, clutch moments
     - Funny reactions, rage, hype moments
     - Big plays, skill shots, close calls
     - Any moment with audio spike
     - Any moment with emotion or speech

  🔴 BORING CONTENT (REMOVE or SPEED UP):
     - Loading screens, menus, settings
     - Idle standing, walking, waiting
     - Silent dead-time (no speech, no action)
     - Repeated grinding, inventory, crafting
     - Tutorial text, "Press X to continue"

============================================================
📏 OUTPUT LENGTH RULES (VERY IMPORTANT)
============================================================

CASE A: Content is GOOD (mostly exciting)
  → PRESERVE the full length. Do NOT cut exciting parts.
  → Target: 90-100% of source duration
  → Example: 42s source → 38-42s output

CASE B: Content is MIXED (some boring, some good)
  → Cut ONLY the boring parts
  → Target: 60-85% of source duration
  → Example: 42s source → 26-36s output

CASE C: Content is BAD (mostly boring)
  → Cut aggressively, keep only best moments
  → Target: 30-50% of source duration
  → Example: 42s source → 13-21s output

⚠️ DEFAULT: Prefer CASE A or B. Only use CASE C if truly necessary.

============================================================
✂️ EDITING RULES
============================================================

1. USE FRAME NUMBERS (not timestamps)
2. Hook in first 2-3 sec — if first 3 sec are boring, CUT THEM
3. Speed changes:
   - Normal good content: 1.0x (keep as is)
   - Slightly slow: 1.2-1.3x
   - Very slow/boring but needed: 1.5-2.0x
   - Clutch/slow-mo moments: 0.5-0.7x
4. aspect_ratio MUST be: "9:16", "1:1", or "4:5" (default 9:16)
5. Every edit MUST have a clear "reason"
6. DO NOT remove more than 50% of good content
7. If content is good, KEEP IT ALL at 1.0x

Return ONLY valid JSON (no markdown, no code fences, no explanation):
{{
  "content_quality": "good|mixed|boring",
  "reasoning": "One sentence about what you observed",
  "target_duration": <number>,
  "aspect_ratio": "9:16",
  "bg_music": "<filename from AVAILABLE music>",
  "music_volume": 0.25,
  "edits": [
    {{"start_frame": 0, "end_frame": 6, "remove": true, "reason": "Loading screen"}},
    {{"start_frame": 6, "end_frame": 120, "speed": 1.0, "reason": "Keep full gameplay"}}
  ]
}}
"""
    return prompt


# ================================================================
# 8. JSON EXTRACTOR (DETAILED DEBUG)
# ================================================================
def extract_json(text):
    print("\n   " + "─" * 60)
    print("   🔍 JSON EXTRACTION DEBUG")
    print("   " + "─" * 60)

    if not text:
        print("   ❌ Empty AI response")
        raise ValueError("Empty AI response")

    print(f"   📏 Raw response length: {len(text)} chars")
    print(f"   📄 First 200: {repr(text[:200])}")
    print(f"   📄 Last 200:  {repr(text[-200:])}")

    text = text.strip()

    if text.startswith("```"):
        print("   🔧 Detected markdown fence — stripping...")
        parts = text.split("```")
        if len(parts) >= 2:
            text = parts[1]
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
        print(f"   ✅ After strip: {len(text)} chars")

    start = text.find("{")
    end = text.rfind("}")

    if start == -1:
        print("   ❌ No opening '{' found!")
        print(f"   📄 Full response:\n{text[:1000]}")
        raise ValueError("No JSON object found (missing '{')")

    if end == -1:
        print("   ❌ No closing '}' found!")
        print(f"   📄 Full response:\n{text[:1000]}")
        raise ValueError("No JSON object found (missing '}')")

    if end <= start:
        print(f"   ❌ Invalid boundaries: start={start}, end={end}")
        raise ValueError("Invalid JSON boundaries")

    json_str = text[start:end + 1]
    print(f"   ✅ JSON extracted: {len(json_str)} chars")

    try:
        result = json.loads(json_str)
        print(f"   ✅ JSON parsed successfully!")
        print(f"   🔑 Keys: {list(result.keys())}")
        print(f"   🎬 Edits count: {len(result.get('edits', []))}")
        print("   " + "─" * 60 + "\n")
        return result

    except json.JSONDecodeError as e:
        print(f"   ❌ JSON parse failed!")
        print(f"   📌 Error: {e}")
        print(f"   📌 Line {e.lineno}, Col {e.colno}, Pos {e.pos}")
        if e.pos < len(json_str):
            print(f"   📌 Around: ...{repr(json_str[max(0, e.pos-80):e.pos+80])}...")

        print("   🔧 Attempting cleanup (single → double quotes)...")
        cleaned = json_str.replace("'", '"')
        try:
            result = json.loads(cleaned)
            print("   ✅ Cleanup succeeded!")
            print("   " + "─" * 60 + "\n")
            return result
        except Exception as e2:
            print(f"   ❌ Cleanup failed: {e2}")
            print("   " + "─" * 60 + "\n")
            raise ValueError(f"JSON parse failed: {e}")


# ================================================================
# 9. AI ANALYZE — MULTI KEY + RETRY (DETAILED DEBUG)
# ================================================================
def ai_analyze(frame_index, grid_paths, transcript, spikes, memes, sfx, music):
    api_keys = get_api_keys()
    if not api_keys:
        raise Exception("No OPENROUTER_API_KEY found in environment!")

    print(f"\n   🔑 Total API keys available: {len(api_keys)}")
    for i, (name, val) in enumerate(api_keys, 1):
        masked = val[:8] + "..." + val[-4:] if len(val) > 12 else "***"
        print(f"      {i}. {name} = {masked}")

    print(f"\n   📸 Preparing {len(grid_paths)} grid images for AI...")
    images = []
    for i, p in enumerate(grid_paths, 1):
        try:
            with open(p, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            size_kb = len(b64) / 1024
            images.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
            })
            print(f"      ✅ {os.path.basename(p)} ({size_kb:.0f} KB)")
        except Exception as e:
            print(f"      ❌ Failed to load {p}: {e}")

    prompt = build_prompt(frame_index, len(grid_paths), transcript, spikes, memes, sfx, music)
    print(f"   📝 Prompt length: {len(prompt)} chars\n")

    last_error = None
    total_attempts = 0

    for key_idx, (key_name, key_val) in enumerate(api_keys, 1):
        for attempt in range(1, 3):
            total_attempts += 1

            print("\n" + "=" * 60)
            print(f"   🔄 ATTEMPT #{total_attempts}")
            print(f"   🔑 Key #{key_idx} ({key_name}) — Try {attempt}/2")
            print("=" * 60)

            try:
                client = OpenAI(
                    api_key=key_val,
                    base_url=OPENROUTER_BASE_URL,
                    default_headers={
                        "HTTP-Referer": "https://github.com/Prembty12/premx-editor",
                        "X-Title": "Auto Video Editor",
                    }
                )

                print(f"   📡 Sending request to OpenRouter...")
                print(f"   🤖 Model: {OPENROUTER_MODEL}")

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

                print(f"   ✅ Response received in {elapsed:.2f}s")

                if hasattr(response, "usage") and response.usage:
                    print(f"   📊 Tokens: {response.usage.total_tokens} "
                          f"(prompt: {response.usage.prompt_tokens}, "
                          f"completion: {response.usage.completion_tokens})")

                text = response.choices[0].message.content
                if not text:
                    print("   ❌ Empty response from API!")
                    last_error = "Empty response"
                    time.sleep(1)
                    continue

                print(f"   📄 Response: {len(text)} chars")

                result = extract_json(text)

                if result.get("aspect_ratio") not in ("9:16", "1:1", "4:5"):
                    print(f"   ⚠️  Invalid aspect: {result.get('aspect_ratio')} → forcing '9:16'")
                    result["aspect_ratio"] = "9:16"

                print("\n   " + "─" * 60)
                print("   🎯 AI DECISION SUMMARY")
                print("   " + "─" * 60)
                print(f"   Content quality: {result.get('content_quality', 'unknown')}")
                print(f"   Reasoning: {result.get('reasoning', '-')}")
                print(f"   Target duration: {result.get('target_duration', '?')}s")
                print(f"   Aspect ratio: {result.get('aspect_ratio')}")
                print(f"   Total edits: {len(result.get('edits', []))}")
                print("   " + "─" * 60 + "\n")

                print(f"   🎉 SUCCESS with key #{key_idx} (attempt {attempt})")
                print("=" * 60 + "\n")
                return result

            except json.JSONDecodeError as e:
                last_error = f"JSONDecodeError: {e}"
                print(f"\n   ❌ JSON DECODE ERROR: {e}")
                print(f"   🔄 Retrying same key...\n")
                time.sleep(1)
                continue

            except ValueError as e:
                last_error = f"ValueError: {e}"
                print(f"\n   ❌ PARSE ERROR: {e}")
                print(f"   🔄 Retrying same key...\n")
                time.sleep(1)
                continue

            except Exception as e:
                last_error = str(e)
                err_str = str(e).lower()
                err_type = type(e).__name__

                print(f"\n   ❌ API ERROR")
                print(f"   📌 Type: {err_type}")
                print(f"   📌 Message: {e}")

                if any(x in err_str for x in ["rate", "quota", "limit", "auth", "401", "403", "429"]):
                    print(f"   🔑 Key issue → moving to NEXT key")
                    print("=" * 60 + "\n")
                    break

                print(f"   🔄 Retrying same key in 2s...")
                time.sleep(2)
                continue

        print(f"\n   ⚠️  Key #{key_idx} ({key_name}) exhausted")
        if key_idx < len(api_keys):
            print(f"   ➡️  Moving to key #{key_idx + 1}...\n")

    print("\n" + "=" * 60)
    print("   ❌ ALL KEYS FAILED")
    print("=" * 60)
    print(f"   Total attempts: {total_attempts}")
    print(f"   Keys tried: {len(api_keys)}")
    print(f"   Last error: {last_error}")
    print("=" * 60 + "\n")

    raise Exception(
        f"All {len(api_keys)} keys failed after {total_attempts} attempts. "
        f"Last error: {last_error}"
    )


# ================================================================
# 10. VERIFY
# ================================================================
def verify_and_convert(ai_json, frame_index):
    log_info("Verifying AI output...")
    fps_sampling = frame_index["fps_sampling"]
    total_frames = frame_index["total_frames"]

    if total_frames == 0:
        ai_json["edits"] = []
        return ai_json

    valid_frames = set(range(total_frames))
    verified = []

    for edit in ai_json.get("edits", []):
        if "insert_meme" in edit:
            verified.append(edit)
            continue

        if "start_frame" in edit and "end_frame" in edit:
            sf = edit["start_frame"]
            ef = edit["end_frame"]

            if sf not in valid_frames:
                sf = min(valid_frames, key=lambda x: abs(x - sf))
            if ef not in valid_frames:
                ef = min(valid_frames, key=lambda x: abs(x - ef))

            if sf >= ef:
                sf, ef = min(sf, ef), max(sf, ef)
                if sf == ef:
                    ef = min(sf + 1, total_frames - 1)

            edit["start_frame"] = sf
            edit["end_frame"] = ef
            edit["start"] = round(sf / fps_sampling, 3)
            edit["end"] = round(ef / fps_sampling, 3)

        verified.append(edit)

    ai_json["edits"] = verified
    log_ok(f"{len(verified)} edits verified")
    return ai_json


# ================================================================
# 11. DEBUG LOG
# ================================================================
def save_debug_log(ai_json, frame_index):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    json_path = os.path.join(DEBUG_DIR, f"edits_{timestamp}.json")
    with open(json_path, "w") as f:
        json.dump(ai_json, f, indent=2)

    lines = [
        "=" * 70,
        f"AI DECISIONS - {timestamp}",
        "=" * 70,
        f"Video: {frame_index['video_duration']:.1f}s | Frames: {frame_index['total_frames']}",
        f"Content Quality: {ai_json.get('content_quality', 'unknown')}",
        f"AI Reasoning: {ai_json.get('reasoning', '-')}",
        f"Target: {ai_json.get('target_duration')}s | Aspect: {ai_json.get('aspect_ratio')}",
        ""
    ]

    for i, edit in enumerate(ai_json.get("edits", []), 1):
        lines.append(f"--- EDIT #{i} ---")
        if "insert_meme" in edit:
            lines.append(f"  🎭 MEME | Mood: {edit.get('meme_mood')}")
        elif edit.get("remove"):
            lines.append(f"  ✂️  CUT | Frames: {edit['start_frame']}-{edit['end_frame']}")
        else:
            lines.append(f"  🎬 KEEP | Frames: {edit['start_frame']}-{edit['end_frame']} "
                         f"| Speed: {edit.get('speed', 1.0)}x")
        lines.append(f"  Reason: {edit.get('reason', '-')}")

    log_path = os.path.join(DEBUG_DIR, f"debug_{timestamp}.txt")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print("\n" + "\n".join(lines))
    log_ok(f"Debug saved: {log_path}")
    return log_path


# ================================================================
# 12. MOOD PICKERS
# ================================================================
def pick_meme(mood):
    mood_dir = os.path.join(MEME_DIR, mood)
    if os.path.exists(mood_dir):
        files = [f for f in os.listdir(mood_dir)
                 if f.lower().endswith(('.mp4', '.mov', '.gif', '.webm'))]
        if files:
            return os.path.join(mood_dir, random.choice(files))

    for root, dirs, files in os.walk(MEME_DIR):
        vids = [f for f in files if f.lower().endswith(('.mp4', '.mov', '.gif', '.webm'))]
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
# 13. ASPECT + FILTER
# ================================================================
def apply_aspect(clip, ratio="9:16"):
    w, h = clip.size
    if ratio == "9:16":
        tw = h * (9 / 16)
        if tw <= w:
            return clip.fx(vfx.crop, x_center=w / 2, y_center=h / 2, width=tw, height=h)
        th = w * (16 / 9)
        return clip.fx(vfx.crop, x_center=w / 2, y_center=h / 2, width=w, height=th)
    elif ratio == "1:1":
        m = min(w, h)
        return clip.fx(vfx.crop, x_center=w / 2, y_center=h / 2, width=m, height=m)
    elif ratio == "4:5":
        tw = h * (4 / 5)
        if tw <= w:
            return clip.fx(vfx.crop, x_center=w / 2, y_center=h / 2, width=tw, height=h)
        th = w * (5 / 4)
        return clip.fx(vfx.crop, x_center=w / 2, y_center=h / 2, width=w, height=th)
    return clip


def apply_filter(clip, name):
    try:
        if name == "cinematic":
            clip = clip.fx(vfx.colorx, 0.9).fx(vfx.lum_contrast, lum=0, contrast=20)
        elif name == "vivid":
            clip = clip.fx(vfx.colorx, 1.3)
        elif name == "cold":
            clip = clip.fx(vfx.colorx, 0.9)
        elif name == "vintage":
            clip = clip.fx(vfx.colorx, 0.8)
    except Exception as e:
        log_warn(f"Filter error ({name}): {e}")
    return clip


# ================================================================
# 14. BUILD REEL (16 Mbps + DURATION LOCK)
# ================================================================
def build_reel(video_path, ai_json, output_path):
    print("\n" + "=" * 60)
    print("   🎬 BUILD REEL — DEBUG")
    print("=" * 60)
    log_info(f"Source: {video_path}")
    log_info(f"Aspect: {ai_json.get('aspect_ratio')}")
    log_info(f"Music: {ai_json.get('bg_music', 'none')}")
    log_info(f"Volume: {ai_json.get('music_volume', 0.3)}")
    log_info(f"Total edits: {len(ai_json.get('edits', []))}")
    print("=" * 60)

    main = VideoFileClip(video_path)
    source_fps = main.fps if main.fps else 30
    source_duration = float(main.duration)
    aspect = ai_json.get("aspect_ratio", "9:16")

    clips = []
    sfx_data = []
    current_time = 0.0

    log_info(f"Source: {source_duration:.2f}s @ {source_fps:.2f}fps")

    for edit in ai_json.get("edits", []):

        if "insert_meme" in edit:
            mood = edit.get("meme_mood", "funny")
            meme_path = pick_meme(mood)
            if meme_path:
                try:
                    meme = VideoFileClip(meme_path)
                    meme = apply_aspect(meme, aspect)
                    clips.append(meme)
                    current_time += meme.duration
                    log_ok(f"Meme ({mood}) — {meme.duration:.1f}s")
                except Exception as e:
                    log_err(f"Meme error: {e}")
            else:
                log_warn(f"No meme found for mood: {mood}")
            continue

        if edit.get("remove", False):
            log_info(f"Cut: {edit.get('start_frame')}-{edit.get('end_frame')}")
            continue

        start = edit.get("start")
        end = edit.get("end")
        if start is None or end is None:
            continue

        try:
            start = max(0.0, min(start, source_duration))
            end = max(start + 0.05, min(end, source_duration))

            seg = main.subclip(start, end)

            speed = edit.get("speed", 1.0)
            if speed and speed != 1.0:
                seg = seg.fx(vfx.speedx, speed)

            zoom = edit.get("zoom")
            if zoom:
                try:
                    seg = seg.fx(vfx.resize, zoom)
                except Exception:
                    pass

            seg = apply_aspect(seg, aspect)

            if "filter" in edit:
                seg = apply_filter(seg, edit["filter"])

            if "text" in edit:
                try:
                    txt = TextClip(
                        edit["text"], fontsize=70, color="white",
                        stroke_color="black", stroke_width=3,
                        font="DejaVu-Sans-Bold", method="caption"
                    ).set_position(("center", "top")).set_duration(seg.duration)
                    seg = CompositeVideoClip([seg, txt])
                except Exception:
                    try:
                        txt = TextClip(
                            edit["text"], fontsize=70, color="white",
                            stroke_color="black", stroke_width=3,
                            method="caption"
                        ).set_position(("center", "top")).set_duration(seg.duration)
                        seg = CompositeVideoClip([seg, txt])
                    except Exception as e2:
                        log_warn(f"Text error: {e2}")

            sfx_mood = edit.get("sfx_mood")
            if sfx_mood:
                sfx_path = pick_sfx(sfx_mood)
                if sfx_path:
                    sfx_data.append((current_time, sfx_path))
                    log_ok(f"SFX ({sfx_mood}) recorded")

            clips.append(seg)
            current_time += seg.duration
            log_ok(f"Keep: {start:.2f}-{end:.2f}s @ {speed}x")

        except Exception as e:
            log_err(f"Clip error: {e}")

    if not clips:
        log_err("No clips! Aborting.")
        return None

    final = concatenate_videoclips(clips, method="compose")
    video_duration = float(final.duration)
    log_info(f"Video duration locked: {video_duration:.2f}s")

    # Audio
    audio = []
    if final.audio:
        audio.append(final.audio)

    for start_t, sfx_path in sfx_data:
        try:
            sfx = AudioFileClip(sfx_path)
            remaining = video_duration - start_t
            if remaining <= 0.05:
                continue
            if sfx.duration > remaining:
                sfx = sfx.subclip(0, remaining)
            sfx = sfx.set_start(start_t)
            audio.append(sfx)
        except Exception as e:
            log_warn(f"SFX error: {e}")

    if "bg_music" in ai_json:
        mpath = os.path.join(MUSIC_DIR, ai_json["bg_music"])
        if os.path.exists(mpath):
            try:
                vol = ai_json.get("music_volume", 0.3)
                music = AudioFileClip(mpath).volumex(vol)
                if music.duration > video_duration:
                    music = music.subclip(0, video_duration)
                else:
                    music = music.fx(vfx.loop, duration=video_duration)
                audio.append(music)
                log_ok(f"Music: {ai_json['bg_music']}")
            except Exception as e:
                log_warn(f"Music error: {e}")

    if audio:
        composite_audio = CompositeAudioClip(audio)
        if composite_audio.duration > video_duration:
            composite_audio = composite_audio.subclip(0, video_duration)
        final = final.set_audio(composite_audio)

    final = final.set_duration(video_duration)

    log_info("Writing video at 16 Mbps (high quality)...")
    final.write_videofile(
        output_path,
        codec="libx264",
        audio_codec="aac",
        audio_bitrate="320k",
        bitrate="16000k",
        fps=source_fps,
        preset="slow",
        threads=4,
        ffmpeg_params=["-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart"],
        verbose=False,
        logger=None
    )

    log_ok(f"Final: {output_path} ({final.duration:.2f}s)")
    return output_path


# ================================================================
# 15. MAIN
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
    print("║" + " " * 15 + "🎬 AUTO EDITOR - OpenRouter" + " " * 26 + "║")
    print("║" + " " * 10 + "Smart Content Mode + Multi-Key Retry" + " " * 22 + "║")
    print("╚" + "═" * 68 + "╝")

    ensure_folders()
    git_commit_folders()

    log_step("🎬 AUTO EDITOR - Smart Content Mode (16 Mbps)")
    log_info(f"Base dir: {BASE_DIR}/")
    log_info(f"Video: {args.video}")
    log_info(f"FPS: {args.fps}")
    log_info(f"Grids: {args.grids}")
    log_info(f"Whisper: {args.whisper}")

    if not os.path.exists(args.video):
        log_err(f"Video not found: {args.video}")
        sys.exit(1)

    api_keys = get_api_keys()
    if not api_keys:
        log_err("No OPENROUTER_API_KEY found!")
        sys.exit(1)

    log_info(f"API Keys loaded: {len(api_keys)}")

    use_whisper = str(args.whisper).lower() == "true"

    log_step("STEP 1: Video Info")
    info = get_video_info(args.video)
    log_ok(f"Duration: {info['duration']:.1f}s")
    log_ok(f"Resolution: {info['width']}x{info['height']}")
    log_ok(f"FPS: {info['fps']:.2f}")

    log_step("STEP 2: Frame Index")
    frame_index = create_frame_index(args.video, args.fps)
    log_ok(f"Total frames: {frame_index['total_frames']}")

    log_step("STEP 3: Grid Generation")
    grids = create_grids(args.video, frame_index, GRID_DIR, args.grids)
    log_ok(f"{len(grids)} grids created")

    log_step("STEP 4: Transcript")
    transcript = get_transcript(args.video, use_whisper)

    log_step("STEP 5: Spike Detection")
    spikes = get_spikes(args.video)

    log_step("STEP 6: Assets Scan")
    memes, sfx, music = get_available_moods()
    log_info(f"Memes: {list(memes.keys())}")
    log_info(f"SFX: {list(sfx.keys())}")
    log_info(f"Music: {len(music)} files")

    log_step("STEP 7: AI Analysis (Smart Content Decision)")
    ai_json = ai_analyze(frame_index, grids, transcript, spikes, memes, sfx, music)

    log_step("STEP 8: Verify Edits")
    ai_json = verify_and_convert(ai_json, frame_index)

    log_step("STEP 9: Debug Log")
    save_debug_log(ai_json, frame_index)

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
