"""
================================================================
AUTO EDITOR - OpenRouter Multi-Key Version (PRODUCTION FINAL)
================================================================
- Full manual control (all settings at top)
- 5 API keys with auto-retry
- Smart prompt: preserves good content
- High quality output (16 Mbps default)
- Duration lock (no freeze)
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


# ╔════════════════════════════════════════════════════════════════╗
# ║                                                                ║
# ║              🎛️  MASTER CONFIG — YAHAN EDIT KARO               ║
# ║                                                                ║
# ║  Ye saari settings ek jagah hain. Bas values change karo.     ║
# ║  Kuch bhi chhupа nahi hai. Har option ka comment hai.          ║
# ║                                                                ║
# ╚════════════════════════════════════════════════════════════════╝

CONFIG = {

    # ═══════════════════════════════════════════════════════════════
    # 📁 PATHS & FOLDERS
    # ═══════════════════════════════════════════════════════════════

    # Base folder jisme sab kuch hoga
    "base_dir": "FASTCUT",

    # Input video path (auto-set if None)
    # Default: {base_dir}/temp_frames/gameplay.mp4
    "video_path": None,

    # ═══════════════════════════════════════════════════════════════
    # 🤖 AI SETTINGS
    # ═══════════════════════════════════════════════════════════════

    # AI model (OpenRouter compatible)
    "ai_model": "openai/gpt-4o-mini",

    # Frame sampling rate (how many frames per second to sample)
    # Higher = more detail but slower
    # 2 = fast, 3 = balanced, 4-5 = detailed
    "frames_per_sec": 3,

    # Max grid images to send to AI
    # 4 = fast, 6 = balanced, 10 = detailed
    "max_grids": 6,

    # Use Whisper for transcription?
    # True = speech detection, False = faster
    "use_whisper": True,

    # AI creativity (0.0 = deterministic, 1.0 = creative)
    # 0.5 = safe, 0.7 = balanced, 0.9 = wild
    "ai_temperature": 0.7,

    # AI max response length
    "ai_max_tokens": 4000,

    # ═══════════════════════════════════════════════════════════════
    # 🎬 VIDEO OUTPUT SETTINGS
    # ═══════════════════════════════════════════════════════════════

    # Aspect ratio for output
    # Options: "9:16" (Reels/TikTok), "1:1" (square), "4:5" (Instagram)
    "aspect_ratio": "9:16",

    # Video bitrate — quality vs file size
    # "8000k"  = good,  small file
    # "12000k" = better, medium
    # "16000k" = great, large (DEFAULT)
    # "20000k" = near-lossless, very large
    "video_bitrate": "16000k",

    # Audio bitrate
    # "128k" = basic, "192k" = good, "256k" = great, "320k" = best
    "audio_bitrate": "320k",

    # CRF (Constant Rate Factor) — quality setting
    # 0 = lossless (huge), 18 = near-lossless (DEFAULT), 23 = good, 28 = meh
    # Lower = better quality + bigger file
    "crf": 18,

    # Encoding preset
    # "ultrafast" (fast, low quality) → "slow" (better quality, slower)
    # Options: ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, veryslow
    "preset": "slow",

    # Output FPS (None = use source FPS)
    "output_fps": None,

    # ═══════════════════════════════════════════════════════════════
    # 🔊 AUDIO VOLUME CONTROL (0.0 to 1.0+)
    # ═══════════════════════════════════════════════════════════════

    # Background music volume
    # 0.0 = mute, 0.25 = subtle (DEFAULT), 0.5 = prominent, 1.0 = loud
    "music_volume": 0.25,

    # SFX (sound effects) volume
    # 0.0 = mute, 0.5 = subtle, 0.8 = clear (DEFAULT), 1.0 = loud
    "sfx_volume": 0.8,

    # Original video audio volume
    # 0.0 = mute, 0.5 = quiet, 1.0 = normal (DEFAULT), 1.5 = boosted
    "original_audio_volume": 1.0,

    # ═══════════════════════════════════════════════════════════════
    # 🎭 MEME CONTROL
    # ═══════════════════════════════════════════════════════════════

    # Minimum seconds a meme stays on screen
    # 0.5 = very short, 1.5 = short (DEFAULT), 3.0 = long
    "meme_min_duration": 1.5,

    # Maximum seconds a meme stays on screen
    # 2.0 = quick, 4.0 = normal (DEFAULT), 8.0 = very long
    "meme_max_duration": 4.0,

    # Meme scale (1.0 = original size)
    # 0.8 = smaller, 1.0 = normal (DEFAULT), 1.2 = bigger
    "meme_scale": 1.0,

    # Allowed meme file formats
    # Add/remove as needed
    "meme_allowed_ext": [".mp4", ".mov", ".gif", ".webm"],

    # ═══════════════════════════════════════════════════════════════
    # ⚡ SPEED CONTROL
    # ═══════════════════════════════════════════════════════════════

    # Default playback speed for normal clips
    # 1.0 = normal (DEFAULT), 1.2 = slightly faster, 0.8 = slower
    "default_speed": 1.0,

    # Maximum speedup allowed
    # 2.0 = double speed (DEFAULT), 3.0 = 3x, 1.5 = max 1.5x
    "max_speed": 2.0,

    # Minimum slowdown allowed (for slow-mo)
    # 0.5 = half speed (DEFAULT), 0.3 = very slow, 0.7 = slight slow-mo
    "min_speed": 0.5,

    # ═══════════════════════════════════════════════════════════════
    # ✂️ CUT CONTROL
    # ═══════════════════════════════════════════════════════════════

    # Allow AI to cut boring parts?
    # True = AI can remove boring (DEFAULT)
    # False = keep full video (no cuts)
    "allow_cuts": True,

    # Preserve good content (don't over-cut)?
    # True = preserve exciting moments (DEFAULT)
    # False = aggressive editing
    "preserve_good_content": True,

    # Minimum clip duration (skip shorter clips)
    # 0.5 = skip tiny clips (DEFAULT), 1.0 = skip short clips
    "min_clip_duration": 0.5,

    # Target output duration range (soft target)
    # AI will try to hit this range
    "target_min_sec": 30,
    "target_max_sec": 90,

    # ═══════════════════════════════════════════════════════════════
    # 🎨 VISUAL EFFECTS
    # ═══════════════════════════════════════════════════════════════

    # Default text settings (if AI inserts text)
    "text_font_size": 70,
    "text_color": "white",
    "text_stroke_color": "black",
    "text_stroke_width": 3,
    "text_font": "DejaVu-Sans-Bold",
    "text_position": ("center", "top"),

    # ═══════════════════════════════════════════════════════════════
    # 🔑 API KEYS (from environment)
    # ═══════════════════════════════════════════════════════════════

    # These are read from GitHub Secrets / environment
    # DO NOT put API keys here directly!
    "api_key_names": [
        "OPENROUTER_API_KEY",
        "OPENROUTER_API_KEY_2",
        "OPENROUTER_API_KEY_3",
        "OPENROUTER_API_KEY_4",
        "OPENROUTER_API_KEY_5",
    ],

    # Attempts per key (before moving to next)
    "attempts_per_key": 2,

    # ═══════════════════════════════════════════════════════════════
    # 🖼️ GRID HISTORY (for analysis)
    # ═══════════════════════════════════════════════════════════════

    # Save grids to GitHub for analysis?
    # True = save latest grids + debug logs (DEFAULT)
    # False = delete everything after run
    "save_grid_history": True,

    # Auto-commit to git (in GitHub Actions)?
    "auto_git_commit": True,
}

# ╔════════════════════════════════════════════════════════════════╗
# ║                                                                ║
# ║                  ✅ CONFIG ENDS HERE                           ║
# ║                                                                ║
# ║  Ab iske neeche sirf code hai, kuch edit karne ki zaroorat    ║
# ║  nahi hai. Bas upar config change karo.                        ║
# ║                                                                ║
# ╚════════════════════════════════════════════════════════════════╝


# ================================================================
# DERIVED PATHS (auto-calculated from CONFIG)
# ================================================================
def get_paths():
    base = CONFIG["base_dir"]
    return {
        "base":       base,
        "input":      os.path.join(base, "input"),
        "temp":       os.path.join(base, "temp_frames"),
        "memes":      os.path.join(base, "memes"),
        "sfx":        os.path.join(base, "sfx"),
        "music":      os.path.join(base, "music"),
        "grids":      os.path.join(base, "grids"),
        "debug":      os.path.join(base, "debug"),
        "output":     os.path.join(base, "output"),
        "history":    os.path.join(base, "grid_history"),
    }

PATHS = get_paths()


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


def print_config():
    """Print current config — verify karo kya use ho raha hai."""
    log_step("🎛️  ACTIVE CONFIG")
    groups = {
        "📁 Paths":      ["base_dir", "video_path"],
        "🤖 AI":         ["ai_model", "frames_per_sec", "max_grids",
                          "use_whisper", "ai_temperature"],
        "🎬 Video":      ["aspect_ratio", "video_bitrate", "audio_bitrate",
                          "crf", "preset", "output_fps"],
        "🔊 Audio":      ["music_volume", "sfx_volume", "original_audio_volume"],
        "🎭 Meme":       ["meme_min_duration", "meme_max_duration", "meme_scale"],
        "⚡ Speed":      ["default_speed", "max_speed", "min_speed"],
        "✂️  Cuts":      ["allow_cuts", "preserve_good_content",
                          "min_clip_duration", "target_min_sec", "target_max_sec"],
    }
    for group, keys in groups.items():
        print(f"\n   {group}")
        for k in keys:
            print(f"      {k:28s} = {CONFIG[k]}")


# ================================================================
# FOLDERS
# ================================================================
def ensure_folders():
    folders = [
        PATHS["base"], PATHS["input"], PATHS["temp"],
        PATHS["grids"], PATHS["debug"], PATHS["output"], PATHS["history"],
        PATHS["memes"],
        os.path.join(PATHS["memes"], "shocked"),
        os.path.join(PATHS["memes"], "funny"),
        os.path.join(PATHS["memes"], "sad"),
        os.path.join(PATHS["memes"], "victory"),
        os.path.join(PATHS["memes"], "reaction"),
        os.path.join(PATHS["memes"], "hype"),
        os.path.join(PATHS["memes"], "fail"),
        os.path.join(PATHS["memes"], "win"),
        PATHS["sfx"],
        os.path.join(PATHS["sfx"], "hype"),
        os.path.join(PATHS["sfx"], "dramatic"),
        os.path.join(PATHS["sfx"], "funny"),
        os.path.join(PATHS["sfx"], "victory"),
        os.path.join(PATHS["sfx"], "whoosh"),
        os.path.join(PATHS["sfx"], "impact"),
        os.path.join(PATHS["sfx"], "notification"),
        PATHS["music"],
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

    # Drop .gitkeep
    for f in folders:
        if f == PATHS["base"]:
            continue
        gitkeep = os.path.join(f, ".gitkeep")
        if not os.path.exists(gitkeep):
            try:
                with open(gitkeep, "w") as fh:
                    fh.write("")
            except Exception:
                pass


# ================================================================
# GIT COMMIT
# ================================================================
def git_commit_folders():
    if not CONFIG["auto_git_commit"]:
        return
    if not os.getenv("GITHUB_ACTIONS"):
        return

    log_info("Committing FASTCUT structure to git...")
    try:
        subprocess.run(["git", "config", "user.email", "actions@github.com"],
                       check=True, timeout=10)
        subprocess.run(["git", "config", "user.name", "github-actions[bot]"],
                       check=True, timeout=10)
        subprocess.run(["git", "add", f"{PATHS['base']}/"], check=True, timeout=30)

        diff = subprocess.run(["git", "diff", "--cached", "--quiet"], timeout=30)
        if diff.returncode == 0:
            log_info("No changes to commit")
            return

        subprocess.run(["git", "commit", "-m",
                        "📁 Auto: Update FASTCUT structure [skip ci]"],
                       check=True, timeout=30)
        push = subprocess.run(["git", "push"], capture_output=True,
                              text=True, timeout=60)
        if push.returncode == 0:
            log_ok("Structure pushed ✅")
        else:
            log_warn(f"Push failed: {push.stderr[:200]}")
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
def create_frame_index(video_path):
    info = get_video_info(video_path)
    fps = CONFIG["frames_per_sec"]
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
def create_grids(video_path, frame_index):
    total_frames = frame_index["total_frames"]
    max_images = CONFIG["max_grids"]
    output_dir = PATHS["grids"]

    if total_frames == 0:
        return []

    num_grids = min(max_images, math.ceil(total_frames / 45))
    frames_per_grid = math.ceil(total_frames / num_grids)
    cols = math.ceil(math.sqrt(frames_per_grid * 1.15))
    rows = math.ceil(frames_per_grid / cols)
    thumb_size = max(150, min(2000 // cols, 300))

    log_info(f"Grids: {num_grids} | Frames/grid: {frames_per_grid} | Layout: {cols}x{rows}")

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
        log_ok(f"{os.path.basename(out)} ({grid.shape[1]}x{grid.shape[0]}px)")

    cap.release()
    return paths


# ================================================================
# TRANSCRIPT
# ================================================================
_WHISPER_MODEL = None

def get_whisper_model():
    global _WHISPER_MODEL
    if _WHISPER_MODEL is None:
        from faster_whisper import WhisperModel
        log_info("Loading whisper model...")
        _WHISPER_MODEL = WhisperModel("base", device="cpu", compute_type="int8")
    return _WHISPER_MODEL


def get_transcript(video_path):
    if not CONFIG["use_whisper"]:
        log_info("Whisper skipped")
        return "No transcript"
    try:
        model = get_whisper_model()
        log_info("Transcribing...")
        segments, info = model.transcribe(video_path)
        lines = [f"[{s.start:6.1f}s] {s.text.strip()}"
                 for s in segments if s.text.strip()]
        if not lines:
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
        threshold = float(np.percentile(per_sec, 80))
        spikes = [f"[{i:6.1f}s] RMS={v:.3f}" for i, v in enumerate(per_sec) if v > threshold]
        if not spikes:
            return "No spikes"
        log_ok(f"{len(spikes)} spikes")
        return "\n".join(spikes)
    except Exception as e:
        log_err(f"Spike error: {e}")
        return "No spikes"


# ================================================================
# MOODS
# ================================================================
def get_available_moods():
    exts = tuple(CONFIG["meme_allowed_ext"])
    memes, sfx, music = {}, {}, []

    if os.path.exists(PATHS["memes"]):
        for mood in os.listdir(PATHS["memes"]):
            p = os.path.join(PATHS["memes"], mood)
            if os.path.isdir(p):
                files = [f for f in os.listdir(p) if f.lower().endswith(exts)]
                if files:
                    memes[mood] = files

    if os.path.exists(PATHS["sfx"]):
        for mood in os.listdir(PATHS["sfx"]):
            p = os.path.join(PATHS["sfx"], mood)
            if os.path.isdir(p):
                files = [f for f in os.listdir(p)
                         if f.lower().endswith(('.mp3', '.wav', '.m4a', '.aac'))]
                if files:
                    sfx[mood] = files

    if os.path.exists(PATHS["music"]):
        music = [f for f in os.listdir(PATHS["music"])
                 if f.lower().endswith(('.mp3', '.wav', '.m4a', '.aac'))]

    return memes, sfx, music


# ================================================================
# BUILD PROMPT
# ================================================================
def build_prompt(frame_index, grid_count, transcript, spikes, memes, sfx, music):
    frame_lines = [f"#{f['idx']}={f['t']}s" for f in frame_index["frames"][::3]]
    frame_list = "\n".join(frame_lines)
    source_dur = frame_index['video_duration']

    allow_cuts = CONFIG["allow_cuts"]
    preserve = CONFIG["preserve_good_content"]

    cut_rule = "3. Cut ONLY boring parts (menus, loading, idle, walking). KEEP all action." if allow_cuts else "3. DO NOT cut anything — keep FULL video"
    preserve_rule = "KEEP all exciting content at 1.0x speed. Preserve good moments." if preserve else "Aggressive editing allowed"

    prompt = f"""You are a PROFESSIONAL viral gaming editor.

VIDEO: {source_dur:.1f}s | Sampling: {frame_index['fps_sampling']}fps | Frames: {frame_index['total_frames']}
TARGET OUTPUT: {CONFIG['target_min_sec']}-{CONFIG['target_max_sec']} seconds (soft target)

FRAME INDEX (use ONLY these):
{frame_list}

GRIDS: {grid_count} images with "#idx | MM:SS.S" labels.

TRANSCRIPT:
{transcript}

AUDIO SPIKES:
{spikes}

AVAILABLE ASSETS:
- Meme moods: {list(memes.keys())}
- SFX moods: {list(sfx.keys())}
- Music: {music}

RULES:
1. USE FRAME NUMBERS (not timestamps)
2. Hook in first 2-3 sec
{cut_rule}
4. Speed range: {CONFIG['min_speed']}x to {CONFIG['max_speed']}x
5. {preserve_rule}
6. aspect_ratio MUST be: "{CONFIG['aspect_ratio']}"
7. Every edit MUST have a "reason"

Return ONLY valid JSON:
{{
  "content_quality": "good|mixed|boring",
  "reasoning": "One sentence",
  "target_duration": <number between {CONFIG['target_min_sec']} and {CONFIG['target_max_sec']}>,
  "aspect_ratio": "{CONFIG['aspect_ratio']}",
  "bg_music": "<filename from AVAILABLE music>",
  "edits": [
    {{"start_frame": 0, "end_frame": 15, "remove": true, "reason": "Loading"}},
    {{"start_frame": 15, "end_frame": 120, "speed": 1.0, "reason": "Keep full gameplay"}},
    {{"insert_meme": "auto", "meme_mood": "shocked", "reason": "Reaction"}}
  ]
}}
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
    for name in CONFIG["api_key_names"]:
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

    prompt = build_prompt(frame_index, len(grid_paths),
                          transcript, spikes, memes, sfx, music)

    last_error = None
    total_attempts = 0
    attempts_per_key = CONFIG["attempts_per_key"]

    for key_idx, (key_name, key_val) in enumerate(api_keys, 1):
        for attempt in range(1, attempts_per_key + 1):
            total_attempts += 1
            print(f"\n   🔄 Attempt #{total_attempts}: Key #{key_idx} ({key_name}) try {attempt}/{attempts_per_key}")

            try:
                client = OpenAI(
                    api_key=key_val,
                    base_url="https://openrouter.ai/api/v1",
                    default_headers={
                        "HTTP-Referer": "https://github.com/Prembty12/premx-editor",
                        "X-Title": "Auto Video Editor",
                    }
                )

                t_start = time.time()
                response = client.chat.completions.create(
                    model=CONFIG["ai_model"],
                    messages=[{
                        "role": "user",
                        "content": [{"type": "text", "text": prompt}] + images
                    }],
                    max_tokens=CONFIG["ai_max_tokens"],
                    temperature=CONFIG["ai_temperature"]
                )
                elapsed = time.time() - t_start

                text = response.choices[0].message.content
                log_ok(f"Response in {elapsed:.2f}s ({len(text)} chars)")

                if response.usage:
                    log_info(f"Tokens: {response.usage.total_tokens}")

                result = extract_json(text)

                if result.get("aspect_ratio") not in ("9:16", "1:1", "4:5"):
                    result["aspect_ratio"] = CONFIG["aspect_ratio"]

                log_ok(f"Quality: {result.get('content_quality', '?')}")
                log_ok(f"Target: {result.get('target_duration')}s")
                log_ok(f"Edits: {len(result.get('edits', []))}")
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
    min_dur = CONFIG["min_clip_duration"]

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

            if not edit.get("remove") and (edit["end"] - edit["start"]) < min_dur:
                log_warn(f"Skipping tiny clip: {edit['start']:.2f}-{edit['end']:.2f}s")
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

    with open(os.path.join(PATHS["debug"], f"edits_{ts}.json"), "w") as f:
        json.dump(ai_json, f, indent=2)

    lines = ["=" * 70, f"AI DECISIONS - {ts}", "=" * 70]
    lines.append(f"Quality: {ai_json.get('content_quality')}")
    lines.append(f"Reasoning: {ai_json.get('reasoning')}")
    lines.append(f"Target: {ai_json.get('target_duration')}s")
    lines.append("")

    for i, edit in enumerate(ai_json.get("edits", []), 1):
        lines.append(f"--- EDIT #{i} ---")
        if "insert_meme" in edit:
            lines.append(f"  MEME | {edit.get('meme_mood')}")
        elif edit.get("remove"):
            lines.append(f"  CUT | {edit['start_frame']}-{edit['end_frame']}")
        else:
            lines.append(f"  KEEP | {edit['start_frame']}-{edit['end_frame']} @ {edit.get('speed', 1.0)}x")
        lines.append(f"  Reason: {edit.get('reason', '-')}")

    with open(os.path.join(PATHS["debug"], f"debug_{ts}.txt"), "w") as f:
        f.write("\n".join(lines))

    print("\n" + "\n".join(lines))
    return ts


# ================================================================
# PICKERS
# ================================================================
def pick_meme(mood):
    exts = tuple(CONFIG["meme_allowed_ext"])
    mood_dir = os.path.join(PATHS["memes"], mood)

    if os.path.exists(mood_dir):
        files = [f for f in os.listdir(mood_dir) if f.lower().endswith(exts)]
        if files:
            return os.path.join(mood_dir, random.choice(files))

    for root, dirs, files in os.walk(PATHS["memes"]):
        vids = [f for f in files if f.lower().endswith(exts)]
        if vids:
            return os.path.join(root, random.choice(vids))
    return None


def pick_sfx(mood):
    mood_dir = os.path.join(PATHS["sfx"], mood)
    if os.path.exists(mood_dir):
        files = [f for f in os.listdir(mood_dir)
                 if f.lower().endswith(('.mp3', '.wav', '.m4a', '.aac'))]
        if files:
            return os.path.join(mood_dir, random.choice(files))

    for root, dirs, files in os.walk(PATHS["sfx"]):
        sfx = [f for f in files if f.lower().endswith(('.mp3', '.wav', '.m4a', '.aac'))]
        if sfx:
            return os.path.join(root, random.choice(sfx))
    return None


# ================================================================
# ASPECT + FILTER
# ================================================================
def apply_aspect(clip, ratio):
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
        log_warn(f"Filter error: {e}")
    return clip


# ================================================================
# BUILD REEL
# ================================================================
def build_reel(video_path, ai_json, output_path):
    log_info("Building reel...")

    main = VideoFileClip(video_path)
    source_fps = main.fps if main.fps else 30
    source_duration = float(main.duration)
    aspect = ai_json.get("aspect_ratio", CONFIG["aspect_ratio"])

    clips = []
    sfx_data = []
    current_time = 0.0

    log_info(f"Source: {source_duration:.2f}s @ {source_fps:.2f}fps")

    for edit in ai_json.get("edits", []):

        # ---- MEME ----
        if "insert_meme" in edit:
            mood = edit.get("meme_mood", "funny")
            meme_path = pick_meme(mood)
            if meme_path:
                try:
                    meme = VideoFileClip(meme_path)
                    original_dur = meme.duration

                    min_d = CONFIG["meme_min_duration"]
                    max_d = CONFIG["meme_max_duration"]
                    target_d = min(max(original_dur, min_d), max_d)

                    if original_dur > target_d:
                        meme = meme.subclip(0, target_d)
                    elif original_dur < min_d:
                        loops = int(min_d / original_dur) + 1
                        meme = concatenate_videoclips([meme] * loops).subclip(0, min_d)

                    if CONFIG["meme_scale"] != 1.0:
                        meme = meme.fx(vfx.resize, CONFIG["meme_scale"])

                    meme = apply_aspect(meme, aspect)
                    clips.append(meme)
                    current_time += meme.duration
                    log_ok(f"Meme ({mood}) {meme.duration:.1f}s [orig={original_dur:.1f}s]")
                except Exception as e:
                    log_err(f"Meme error: {e}")
            else:
                log_warn(f"No meme for mood: {mood}")
            continue

        # ---- REMOVE ----
        if edit.get("remove", False):
            log_info(f"Cut: {edit.get('start_frame')}-{edit.get('end_frame')}")
            continue

        # ---- KEEP ----
        start = edit.get("start")
        end = edit.get("end")
        if start is None or end is None:
            continue

        try:
            start = max(0.0, min(start, source_duration))
            end = max(start + 0.05, min(end, source_duration))

            seg = main.subclip(start, end)

            speed = edit.get("speed", CONFIG["default_speed"])
            speed = max(CONFIG["min_speed"], min(CONFIG["max_speed"], speed))
            if speed != 1.0:
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
                        edit["text"],
                        fontsize=CONFIG["text_font_size"],
                        color=CONFIG["text_color"],
                        stroke_color=CONFIG["text_stroke_color"],
                        stroke_width=CONFIG["text_stroke_width"],
                        font=CONFIG["text_font"],
                        method="caption"
                    ).set_position(CONFIG["text_position"]).set_duration(seg.duration)
                    seg = CompositeVideoClip([seg, txt])
                except Exception as e:
                    log_warn(f"Text error: {e}")

            sfx_mood = edit.get("sfx_mood")
            if sfx_mood:
                sfx_path = pick_sfx(sfx_mood)
                if sfx_path:
                    sfx_data.append((current_time, sfx_path))
                    log_ok(f"SFX ({sfx_mood})")

            clips.append(seg)
            current_time += seg.duration
            log_ok(f"Keep: {start:.2f}-{end:.2f}s @ {speed}x")

        except Exception as e:
            log_err(f"Clip error: {e}")

    if not clips:
        log_err("No clips!")
        return None

    final = concatenate_videoclips(clips, method="compose")
    video_duration = float(final.duration)
    log_info(f"Video duration locked: {video_duration:.2f}s")

    # ============================================================
    # AUDIO MIX (FULL CONTROL)
    # ============================================================
    audio_tracks = []

    # 1. Original audio
    if final.audio:
        orig = final.audio.volumex(CONFIG["original_audio_volume"])
        audio_tracks.append(orig)
        log_info(f"Original audio: {CONFIG['original_audio_volume']}x")

    # 2. SFX
    for start_t, sfx_path in sfx_data:
        try:
            sfx = AudioFileClip(sfx_path)
            remaining = video_duration - start_t
            if remaining <= 0.05:
                continue
            if sfx.duration > remaining:
                sfx = sfx.subclip(0, remaining)
            sfx = sfx.set_start(start_t).volumex(CONFIG["sfx_volume"])
            audio_tracks.append(sfx)
            log_info(f"SFX @ {start_t:.2f}s: {CONFIG['sfx_volume']}x")
        except Exception as e:
            log_warn(f"SFX error: {e}")

    # 3. Music
    if "bg_music" in ai_json:
        mpath = os.path.join(PATHS["music"], ai_json["bg_music"])
        if os.path.exists(mpath):
            try:
                music = AudioFileClip(mpath).volumex(CONFIG["music_volume"])
                if music.duration > video_duration:
                    music = music.subclip(0, video_duration)
                else:
                    music = music.fx(vfx.loop, duration=video_duration)
                audio_tracks.append(music)
                log_ok(f"Music: {ai_json['bg_music']} @ {CONFIG['music_volume']}x")
            except Exception as e:
                log_warn(f"Music error: {e}")

    if audio_tracks:
        composite = CompositeAudioClip(audio_tracks)
        if composite.duration > video_duration:
            composite = composite.subclip(0, video_duration)
        final = final.set_audio(composite)

    final = final.set_duration(video_duration)

    # ============================================================
    # WRITE
    # ============================================================
    output_fps = CONFIG["output_fps"] if CONFIG["output_fps"] else source_fps

    log_info(f"Writing: {CONFIG['video_bitrate']}, CRF={CONFIG['crf']}, "
             f"preset={CONFIG['preset']}, fps={output_fps}")

    final.write_videofile(
        output_path,
        codec="libx264",
        audio_codec="aac",
        audio_bitrate=CONFIG["audio_bitrate"],
        bitrate=CONFIG["video_bitrate"],
        fps=output_fps,
        preset=CONFIG["preset"],
        threads=4,
        ffmpeg_params=[
            "-crf", str(CONFIG["crf"]),
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
    print("\n")
    print("╔" + "═" * 68 + "╗")
    print("║" + " " * 12 + "🎬 AUTO EDITOR — FULL CONTROL" + " " * 26 + "║")
    print("╚" + "═" * 68 + "╝")

    # Auto-set video path
    if not CONFIG["video_path"]:
        CONFIG["video_path"] = os.path.join(PATHS["temp"], "gameplay.mp4")

    ensure_folders()
    git_commit_folders()

    print_config()

    video_path = CONFIG["video_path"]
    if not os.path.exists(video_path):
        log_err(f"Video not found: {video_path}")
        sys.exit(1)

    api_keys = get_api_keys()
    if not api_keys:
        log_err("No API keys found!")
        sys.exit(1)
    log_info(f"API keys: {len(api_keys)}")

    # STEP 1
    log_step("STEP 1: Video Info")
    info = get_video_info(video_path)
    log_ok(f"Duration: {info['duration']:.1f}s | Res: {info['width']}x{info['height']} | FPS: {info['fps']:.2f}")

    # STEP 2
    log_step("STEP 2: Frame Index")
    frame_index = create_frame_index(video_path)
    log_ok(f"Total frames: {frame_index['total_frames']}")

    # STEP 3
    log_step("STEP 3: Grids")
    grids = create_grids(video_path, frame_index)
    log_ok(f"{len(grids)} grids created")

    # STEP 4
    log_step("STEP 4: Transcript")
    transcript = get_transcript(video_path)

    # STEP 5
    log_step("STEP 5: Spike Detection")
    spikes = get_spikes(video_path)

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
    output = os.path.join(PATHS["output"], "final_reel.mp4")
    build_reel(video_path, ai_json, output)

    log_step("🎉 DONE!")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log_err(f"FATAL: {e}")
        traceback.print_exc()
        sys.exit(1)
