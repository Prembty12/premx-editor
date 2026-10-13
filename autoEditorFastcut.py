"""
================================================================
AUTO EDITOR - OpenRouter Version (PRODUCTION READY)
================================================================
- MoviePy 1.0.3 compatible
- Whisper model cached (fast)
- Empty data protected
- Aspect ratio enforced
- Music loop fixed
- Font fallback added
- Full error handling
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
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = "openai/gpt-4o-mini"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

MEME_DIR = "./memes"
SFX_DIR = "./sfx"
MUSIC_DIR = "./music"
GRID_DIR = "./grids"
DEBUG_DIR = "./debug"
OUTPUT_DIR = "./output"


# ================================================================
# GLOBAL CACHE
# ================================================================
_WHISPER_MODEL = None


# ================================================================
# LOGGING HELPERS
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
# AUTO-CREATE FOLDERS
# ================================================================
def ensure_folders():
    folders = [
        "input",
        "memes/shocked", "memes/funny", "memes/sad", "memes/victory",
        "sfx/hype", "sfx/dramatic", "sfx/funny", "sfx/victory",
        "music", "grids", "debug", "output",
    ]
    for f in folders:
        os.makedirs(f, exist_ok=True)
    log_ok(f"Created {len(folders)} folders")


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

    return {
        "duration": duration,
        "fps": fps,
        "width": w,
        "height": h,
        "total_frames": total
    }


# ================================================================
# 2. FRAME INDEX
# ================================================================
def create_frame_index(video_path, frames_per_sec=3):
    info = get_video_info(video_path)
    duration = info["duration"]
    total_frames = int(duration * frames_per_sec)
    frames = [
        {"idx": i, "t": round(i / frames_per_sec, 3)}
        for i in range(total_frames)
    ]
    return {
        "video_duration": duration,
        "fps_sampling": frames_per_sec,
        "total_frames": total_frames,
        "frames": frames,
        "info": info
    }


# ================================================================
# 3. GRID GENERATOR
# ================================================================
def create_grids(video_path, frame_index, output_dir="grids", max_images=6):
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
    log_info(f"Thumb size: {thumb_size}px")

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
            draw.rectangle(
                [pad, pad, 2 * pad + bbox[2], 2 * pad + bbox[3]],
                fill="black"
            )
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
# 4. TRANSCRIPT - faster-whisper (CACHED)
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
        log_info("Transcribing with faster-whisper...")
        segments, info = model.transcribe(video_path)
        lines = [
            f"[{s.start:6.1f}s] {s.text.strip()}"
            for s in segments if s.text.strip()
        ]
        if not lines:
            log_warn("No speech detected")
            return "No speech"
        log_ok(f"{len(lines)} segments (lang: {info.language})")
        return "\n".join(lines)
    except Exception as e:
        log_err(f"Whisper error: {e}")
        return "No transcript"


# ================================================================
# 5. SPIKE DETECTION
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
            log_warn("No audio frames")
            return "No spikes"

        threshold = float(np.percentile(per_sec, 80))
        spikes = [
            f"[{i:6.1f}s] RMS={v:.3f}"
            for i, v in enumerate(per_sec) if v > threshold
        ]

        if not spikes:
            log_warn("No spikes above threshold")
            return "No spikes"

        log_ok(f"{len(spikes)} spikes detected")
        return "\n".join(spikes)
    except Exception as e:
        log_err(f"Spike error: {e}")
        return "No spikes"


# ================================================================
# 6. AVAILABLE ASSETS
# ================================================================
def get_available_moods():
    memes, sfx, music = {}, {}, []

    if os.path.exists(MEME_DIR):
        for mood in os.listdir(MEME_DIR):
            p = os.path.join(MEME_DIR, mood)
            if os.path.isdir(p):
                files = [
                    f for f in os.listdir(p)
                    if f.lower().endswith(('.mp4', '.mov', '.gif', '.webm'))
                ]
                if files:
                    memes[mood] = files

    if os.path.exists(SFX_DIR):
        for mood in os.listdir(SFX_DIR):
            p = os.path.join(SFX_DIR, mood)
            if os.path.isdir(p):
                files = [
                    f for f in os.listdir(p)
                    if f.lower().endswith(('.mp3', '.wav', '.m4a', '.aac'))
                ]
                if files:
                    sfx[mood] = files

    if os.path.exists(MUSIC_DIR):
        music = [
            f for f in os.listdir(MUSIC_DIR)
            if f.lower().endswith(('.mp3', '.wav', '.m4a', '.aac'))
        ]

    return memes, sfx, music


# ================================================================
# 7. AI ANALYSIS - OPENROUTER
# ================================================================
def ai_analyze(frame_index, grid_paths, transcript, spikes, memes, sfx, music):
    if not OPENROUTER_API_KEY:
        raise Exception("OPENROUTER_API_KEY missing!")

    log_info(f"Sending to OpenRouter ({OPENROUTER_MODEL})...")

    client = OpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url=OPENROUTER_BASE_URL,
        default_headers={
            "HTTP-Referer": "https://github.com/Prembty12/premx-editor",
            "X-Title": "Auto Video Editor",
        }
    )

    images = []
    for p in grid_paths:
        with open(p, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        images.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
        })

    frame_lines = [
        f"#{f['idx']}={f['t']}s"
        for f in frame_index["frames"][::3]
    ]
    frame_list = "\n".join(frame_lines)

    prompt = f"""You are a PROFESSIONAL viral gaming editor with FULL CREATIVE FREEDOM.
Game doesn't matter - works with ANY game.

VIDEO: {frame_index['video_duration']:.1f}s | Sampling: {frame_index['fps_sampling']}fps | Total: {frame_index['total_frames']}

FRAME INDEX (use ONLY these):
{frame_list}

GRIDS: {len(grid_paths)} images. Each frame has "#idx | MM:SS.S" label.

TRANSCRIPT:
{transcript}

AUDIO SPIKES:
{spikes}

AVAILABLE:
- Meme moods: {list(memes.keys())}
- SFX moods: {list(sfx.keys())}
- Music: {music}

TASK: Create a PROFESSIONAL 30-90 sec viral reel.

RULES:
- USE FRAME NUMBERS (not timestamps)
- Hook in first 2-3 sec
- CUT ALL boring
- Speed: hype=1.3-1.5x, clutch=0.5-0.7x
- Total 30-90 sec
- Every edit MUST have a "reason"
- aspect_ratio MUST be exactly one of: "9:16", "1:1", "4:5" (default 9:16)

Return ONLY valid JSON (no markdown):
{{
  "target_duration": 60,
  "aspect_ratio": "9:16",
  "bg_music": "hype_track.mp3",
  "music_volume": 0.3,
  "edits": [
    {{"start_frame": 0, "end_frame": 15, "remove": true, "reason": "Boring intro"}},
    {{"start_frame": 30, "end_frame": 45, "speed": 1.5, "sfx_mood": "hype", "reason": "Kill moment"}},
    {{"insert_meme": "auto", "meme_mood": "shocked", "reason": "Reaction"}}
  ]
}}
"""

    response = client.chat.completions.create(
        model=OPENROUTER_MODEL,
        messages=[{
            "role": "user",
            "content": [{"type": "text", "text": prompt}] + images
        }],
        max_tokens=4000
    )

    text = response.choices[0].message.content.strip()

    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    result = json.loads(text)

    if result.get("aspect_ratio") not in ("9:16", "1:1", "4:5"):
        result["aspect_ratio"] = "9:16"

    log_ok("OpenRouter responded")
    return result


# ================================================================
# 8. VERIFY + CONVERT
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
# 9. DEBUG LOG
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
            lines.append(
                f"  🎬 KEEP | Frames: {edit['start_frame']}-{edit['end_frame']} "
                f"| Speed: {edit.get('speed', 1.0)}x"
            )
        lines.append(f"  Reason: {edit.get('reason', '-')}")

    log_path = os.path.join(DEBUG_DIR, f"debug_{timestamp}.txt")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print("\n" + "\n".join(lines))
    log_ok(f"Debug saved: {log_path}")
    return log_path


# ================================================================
# 10. MOOD PICKERS
# ================================================================
def pick_meme(mood):
    mood_dir = os.path.join(MEME_DIR, mood)
    if os.path.exists(mood_dir):
        files = [
            f for f in os.listdir(mood_dir)
            if f.lower().endswith(('.mp4', '.mov', '.gif', '.webm'))
        ]
        if files:
            return os.path.join(mood_dir, random.choice(files))

    for root, dirs, files in os.walk(MEME_DIR):
        vids = [
            f for f in files
            if f.lower().endswith(('.mp4', '.mov', '.gif', '.webm'))
        ]
        if vids:
            return os.path.join(root, random.choice(vids))
    return None


def pick_sfx(mood):
    mood_dir = os.path.join(SFX_DIR, mood)
    if os.path.exists(mood_dir):
        files = [
            f for f in os.listdir(mood_dir)
            if f.lower().endswith(('.mp3', '.wav', '.m4a', '.aac'))
        ]
        if files:
            return os.path.join(mood_dir, random.choice(files))

    for root, dirs, files in os.walk(SFX_DIR):
        sfx = [
            f for f in files
            if f.lower().endswith(('.mp3', '.wav', '.m4a', '.aac'))
        ]
        if sfx:
            return os.path.join(root, random.choice(sfx))
    return None


# ================================================================
# 11. ASPECT + FILTER
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
# 12. BUILD REEL
# ================================================================
def build_reel(video_path, ai_json, output_path):
    log_info("Building reel...")

    main = VideoFileClip(video_path)
    aspect = ai_json.get("aspect_ratio", "9:16")
    clips = []
    sfx_tracks = []
    current_time = 0.0

    for edit in ai_json.get("edits", []):

        # ---- INSERT MEME ----
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

        # ---- REMOVE ----
        if edit.get("remove", False):
            log_info(f"Cut: {edit.get('start_frame')}-{edit.get('end_frame')}")
            continue

        # ---- KEEP SEGMENT ----
        start = edit.get("start")
        end = edit.get("end")
        if start is None or end is None:
            continue

        try:
            start = max(0.0, min(start, main.duration))
            end = max(start + 0.05, min(end, main.duration))

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
                    try:
                        sfx = AudioFileClip(sfx_path).set_start(current_time)
                        sfx_tracks.append(sfx)
                        log_ok(f"SFX ({sfx_mood})")
                    except Exception as e:
                        log_warn(f"SFX error: {e}")

            clips.append(seg)
            current_time += seg.duration
            log_ok(f"Keep: {start:.2f}-{end:.2f}s @ {speed}x")

        except Exception as e:
            log_err(f"Clip error: {e}")

    if not clips:
        log_err("No clips! Aborting.")
        return None

    final = concatenate_videoclips(clips, method="compose")

    # ---- AUDIO MIX ----
    audio = []
    if final.audio:
        audio.append(final.audio)
    audio.extend(sfx_tracks)

    if "bg_music" in ai_json:
        mpath = os.path.join(MUSIC_DIR, ai_json["bg_music"])
        if os.path.exists(mpath):
            try:
                vol = ai_json.get("music_volume", 0.3)
                music = AudioFileClip(mpath).volumex(vol)
                if music.duration > final.duration:
                    music = music.subclip(0, final.duration)
                else:
                    music = music.fx(vfx.loop, duration=final.duration)
                audio.append(music)
                log_ok(f"Music: {ai_json['bg_music']}")
            except Exception as e:
                log_warn(f"Music error: {e}")
        else:
            log_warn(f"Music not found: {mpath}")

    if audio:
        final = final.set_audio(CompositeAudioClip(audio))

    # ---- WRITE ----
    log_info("Writing video (this may take 1-3 min)...")
    final.write_videofile(
        output_path,
        codec="libx264",
        audio_codec="aac",
        fps=30,
        preset="medium",
        threads=4,
        verbose=False,
        logger=None
    )
    log_ok(f"Final: {output_path} ({final.duration:.1f}s)")
    return output_path


# ================================================================
# 13. MAIN
# ================================================================
def main():
    parser = argparse.ArgumentParser(description="Auto Video Editor")
    parser.add_argument("--video", default="input/gameplay.mp4")
    parser.add_argument("--fps", type=int, default=3)
    parser.add_argument("--grids", type=int, default=6)
    parser.add_argument("--whisper", default="true")
    args = parser.parse_args()

    ensure_folders()

    log_step("🎬 AUTO EDITOR - OpenRouter Version")
    log_info(f"Video: {args.video}")
    log_info(f"FPS: {args.fps}")
    log_info(f"Grids: {args.grids}")
    log_info(f"Whisper: {args.whisper}")

    if not os.path.exists(args.video):
        log_err(f"Video nahi mila: {args.video}")
        sys.exit(1)

    if not OPENROUTER_API_KEY:
        log_err("OPENROUTER_API_KEY set nahi hai!")
        log_info("GitHub Secrets me daalo: Settings → Secrets → Actions")
        sys.exit(1)

    use_whisper = str(args.whisper).lower() == "true"

    # STEP 1: Video info
    log_step("STEP 1: Video Info")
    info = get_video_info(args.video)
    log_ok(f"Duration: {info['duration']:.1f}s")
    log_ok(f"Resolution: {info['width']}x{info['height']}")
    log_ok(f"FPS: {info['fps']:.2f}")

    # STEP 2: Frame index
    log_step("STEP 2: Frame Index")
    frame_index = create_frame_index(args.video, args.fps)
    log_ok(f"Total frames: {frame_index['total_frames']}")

    # STEP 3: Grids
    log_step("STEP 3: Grid Generation")
    grids = create_grids(args.video, frame_index, GRID_DIR, args.grids)
    log_ok(f"{len(grids)} grids created")

    # STEP 4: Transcript
    log_step("STEP 4: Transcript")
    transcript = get_transcript(args.video, use_whisper)

    # STEP 5: Spikes
    log_step("STEP 5: Spike Detection")
    spikes = get_spikes(args.video)

    # STEP 6: Assets
    log_step("STEP 6: Assets Scan")
    memes, sfx, music = get_available_moods()
    log_info(f"Memes: {list(memes.keys())}")
    log_info(f"SFX: {list(sfx.keys())}")
    log_info(f"Music: {len(music)} files")

    # STEP 7: AI Analysis
    log_step("STEP 7: AI Analysis")
    ai_json = ai_analyze(frame_index, grids, transcript, spikes, memes, sfx, music)

    # STEP 8: Verify
    log_step("STEP 8: Verify Edits")
    ai_json = verify_and_convert(ai_json, frame_index)

    # STEP 9: Debug log
    log_step("STEP 9: Debug Log")
    save_debug_log(ai_json, frame_index)

    # STEP 10: Build reel
    log_step("STEP 10: Build Reel")
    output = os.path.join(OUTPUT_DIR, "final_reel.mp4")
    build_reel(args.video, ai_json, output)

    log_step("🎉 DONE!")


# ================================================================
# ENTRY
# ================================================================
if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log_err(f"FATAL ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)
