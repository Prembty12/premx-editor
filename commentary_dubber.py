#!/usr/bin/env python3
"""
🎙️ AI Commentary Dubber — v3.9 (Slot Range Fix)
===============================================================
FIXES:
  ✅ Timing LOCK — GPT segment = SLOT time (no drift)
  ✅ Slot-locked audio delay (exact match)
  ✅ Variable atempo — 1.0 se 1.20 ke beech
  ✅ Voice natural (VOICE_SPEED_MAX = 1.17)
  ✅ SLOT-ALIGNED GRID — frames slot ke range se match (FIXED)
===============================================================
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
# 🔑 MULTI-KEY CONFIG
# ============================================================
def _collect_keys(*env_names):
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
ANALYSIS_GRID_PATH = "analysis/last_analysis.jpg"
SEGMENTS_DIR       = "segments"

MIN_SLOTS_HARD = 6
MAX_SLOTS_HARD = 20
DUCK_VOLUME = 0.25

# 90 frames — 8K portrait canvas (9x10 grid)
ANALYSIS_FRAMES = 90
GRID_COLS = 9
GRID_ROWS = 10
CANVAS_W = 4320
CANVAS_H = 7680

# Voice speed limits — NATURAL
VOICE_SPEED_MIN = 1.00
VOICE_SPEED_MAX = 1.17

# ✅ Variable atempo — 1.0 se 1.20 ke beech
ATEMPO_MIN = 1.00
ATEMPO_MAX = 1.17

SPEED_ACTION = 1.17
SPEED_DIALOG = 1.05
SPEED_CALM   = 1.00

VOL_ACTION = 1.7
VOL_OTHER  = 1.4

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
    if slot_type == "action":
        return SPEED_ACTION
    elif slot_type == "dialog":
        return SPEED_DIALOG
    else:
        return SPEED_CALM


# ============================================================
# MOTION SCORE
# ============================================================
def get_motion_score(video_path, start, end):
    try:
        duration = max(end - start, 0.5)
        cmd = (
            f'ffmpeg -ss {start:.2f} -t {duration:.2f} -i {video_path} '
            f'-vf "select=\'gt(scene,0.1)\',metadata=print" '
            f'-f null - 2>&1'
        )
        out = subprocess.run(cmd, shell=True, capture_output=True, text=True).stderr
        motion_events = len(re.findall(r"pts_time", out))
        return motion_events
    except Exception:
        return 0


# ============================================================
# GIT PUSH
# ============================================================
def commit_analysis_to_github():
    print("📤 [10] Pushing analysis image to GitHub...")

    if not os.path.exists(ANALYSIS_GRID_PATH):
        print("   ⚠️ No analysis image found, skipping git commit.")
        return

    try:
        subprocess.run("git config --global user.name 'GitHub Action'", shell=True, check=False)
        subprocess.run("git config --global user.email 'action@github.com'", shell=True, check=False)

        print("   🔄 Fetching latest from remote...")
        subprocess.run("git fetch origin", shell=True, check=False)

        print("   🔄 Rebasing with autostash...")
        rebase_res = subprocess.run(
            "git pull --rebase --autostash origin main",
            shell=True, capture_output=True, text=True
        )
        if rebase_res.returncode != 0:
            print(f"   ⚠️ Rebase on main failed, trying master...")
            subprocess.run(
                "git pull --rebase --autostash origin master",
                shell=True, check=False
            )

        subprocess.run(f"git add {ANALYSIS_GRID_PATH}", shell=True, check=False)
        print(f"   📎 Staged: {ANALYSIS_GRID_PATH}")

        commit_res = subprocess.run(
            "git commit -m 'Update analysis image [skip ci]'",
            shell=True, capture_output=True, text=True
        )
        if commit_res.returncode == 0:
            print("   ✅ Committed analysis image.")
        else:
            print("   ℹ️ No changes to commit.")

        push_res = subprocess.run(
            "git push origin HEAD --force-with-lease",
            shell=True, capture_output=True, text=True
        )
        if push_res.returncode == 0:
            print("   🚀 Pushed to GitHub successfully.")
        else:
            print(f"   ⚠️ Force-with-lease failed, trying normal push...")
            push_res2 = subprocess.run(
                "git push origin HEAD",
                shell=True, capture_output=True, text=True
            )
            if push_res2.returncode == 0:
                print("   🚀 Pushed (normal) to GitHub successfully.")
            else:
                print(f"   ❌ Push failed: {push_res2.stderr.strip()[:200]}")

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
# STEP 2 — Transcribe
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
                print(f"   ✅ Key {key_idx} worked! SRT saved\n")
                success = True
                break

            elif r.status_code in (401, 403):
                print(f"   ❌ Key {key_idx} invalid — trying next...")
                time.sleep(1)
                continue
            elif r.status_code == 429:
                print(f"   ⚠️ Key {key_idx} rate-limited — trying next...")
                time.sleep(2)
                continue
            else:
                print(f"   ⚠️ Key {key_idx} error {r.status_code}")
                time.sleep(2)
                continue

        except Exception as e:
            print(f"   ⚠️ Key {key_idx} exception: {e}")
            time.sleep(2)
            continue

    if not success:
        print("   ❌ All Groq keys failed\n")

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
            "voice_speed": 1.0,
            "motion_score": 0,
            "gpt_type": None,
            "final_type": None,
            "speed_boost_log": []
        })
        t = end

        if t >= vid_duration - 0.1:
            break

    if slots and slots[-1]["end"] < vid_duration - 0.1:
        slots[-1]["end"] = round(vid_duration, 2)

    print(f"   ✅ Built {len(slots)} slots\n")
    return slots


# ============================================================
# STEP 4 — SIGNAL-BASED CLASSIFY
# ============================================================
def classify_slots_combined(video_path, slots, srt_content):
    print("🔍 [4] Classifying slots (signal + motion score)...")

    scene_times = get_scene_timeline(video_path)
    loud_timeline = get_loudness_timeline(video_path)
    srt_entries = parse_srt(srt_content)

    print(f"   🎬 Scene cuts: {len(scene_times)}")
    print(f"   🔊 Loudness samples: {len(loud_timeline)}")
    print(f"   📝 SRT entries: {len(srt_entries)}\n")

    ACTION_WORDS = {"shoot","fire","hit","run","kill","die","attack",
                    "grenade","boom","jump","dodge","cover","reload",
                    "go","move","watch","left","right","down","up","quick",
                    "destroy","target","lock","bang","drop","danger",
                    "whoa","oh","yeah","nice","sick","cook","big","fast"}
    DIALOG_WORDS = {"you","me","we","what","why","how","hey","listen",
                    "wait","okay","yeah","know","think","feel","want",
                    "need","can","will"}

    for slot in slots:
        motion = get_motion_score(video_path, slot["start"], slot["end"])
        slot["motion_score"] = motion

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

        orig_action_ratio = action_ratio
        orig_calm_ratio = calm_ratio
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

        slot["scene_count"] = sum(
            1 for st in scene_times if slot["start"] <= st < slot["end"]
        )
        slot["avg_loud"] = round(
            slot_loudness(loud_timeline, slot["start"], slot["end"]), 1
        )
        slot["sub_analysis"] = {
            "action_ratio": round(action_ratio, 2),
            "action_ratio_raw": round(orig_action_ratio, 2),
            "dialog_ratio": round(dialog_ratio, 2),
            "calm_ratio": round(calm_ratio, 2),
            "calm_ratio_raw": round(orig_calm_ratio, 2),
            "total_subs": total,
            "motion_score": motion
        }

        voice_speed = speed_for_type(slot["type"])
        slot["speed_boost_log"] = [f"base_{slot['type']}={voice_speed:.2f}"]

        if slot["type"] == "action":
            if slot["scene_count"] >= 3:
                voice_speed += 0.03
                slot["speed_boost_log"].append("+0.03 (scenes>=3)")
            if slot["avg_loud"] > -12:
                voice_speed += 0.03
                slot["speed_boost_log"].append("+0.03 (loud>-12)")
            if motion >= 5:
                voice_speed += 0.02
                slot["speed_boost_log"].append("+0.02 (motion>=5)")

        final_speed = round(max(VOICE_SPEED_MIN, min(VOICE_SPEED_MAX, voice_speed)), 2)
        if final_speed != round(voice_speed, 2):
            slot["speed_boost_log"].append(f"capped_to_{final_speed}")
        slot["voice_speed"] = final_speed

    speeds = [s["voice_speed"] for s in slots]
    print(f"✅ Slots classified: {len(slots)}")
    print(f"🎮 Voice speeds: min={min(speeds):.2f} max={max(speeds):.2f} "
          f"avg={sum(speeds)/len(speeds):.2f}\n")
    return slots


# ============================================================
# STEP 5 — 8K PORTRAIT ANALYSIS GRID (SLOT-ALIGNED — FIXED) ✅
# ============================================================
def build_analysis_grid(video_path, vid_duration, slots, num_frames=ANALYSIS_FRAMES):
    print(f"🖼️ [5] Building 8K PORTRAIT grid (SLOT-ALIGNED) — {num_frames} frames...")

    if os.path.exists(ANALYSIS_GRID_PATH):
        try:
            os.remove(ANALYSIS_GRID_PATH)
        except Exception as e:
            print(f"   ⚠️  Could not delete: {e}")

    # ✅ SLOT-ALIGNED FRAME TIMES
    # Har slot ke andar evenly frames distribute karo
    frame_specs = []  # list of (frame_time, slot_start, slot_end, slot_idx)

    if slots:
        # Har slot ko kitne frames milenge (proportional to duration)
        total_dur = sum(s["end"] - s["start"] for s in slots)
        for slot_idx, slot in enumerate(slots):
            slot_dur = slot["end"] - slot["start"]
            n_frames = max(1, round(num_frames * (slot_dur / total_dur)))
            for k in range(n_frames):
                frac = (k + 0.5) / n_frames
                t = slot["start"] + (slot_dur * frac)
                frame_specs.append((t, slot["start"], slot["end"], slot_idx))

    # ✅ Agar num_frames se kam bane toh extra frames add karo
    # ✅ FIX: Frame time ko slot ke RANGE se match karo (nearest nahi)
    if len(frame_specs) < num_frames and slots:
        interval = vid_duration / num_frames
        existing_times = [f[0] for f in frame_specs]
        for i in range(num_frames):
            t = i * interval
            if not any(abs(t - et) < 0.3 for et in existing_times):
                # ✅ FIX: Frame time ko slot ke range se check karo
                matched_slot = None
                matched_idx = None
                for si, s in enumerate(slots):
                    if s["start"] <= t < s["end"]:
                        matched_slot = s
                        matched_idx = si
                        break

                if matched_slot is not None:
                    frame_specs.append((t, matched_slot["start"], matched_slot["end"], matched_idx))
                else:
                    # Fallback: nearest slot by center
                    nearest_slot = min(
                        slots,
                        key=lambda s: abs((s["start"] + s["end"]) / 2 - t)
                    )
                    nearest_idx = slots.index(nearest_slot)
                    frame_specs.append((t, nearest_slot["start"], nearest_slot["end"], nearest_idx))

    # Sort by frame time
    frame_specs = sorted(frame_specs, key=lambda x: x[0])

    # Trim to exact num_frames
    if len(frame_specs) > num_frames:
        step = len(frame_specs) / num_frames
        frame_specs = [frame_specs[int(i * step)] for i in range(num_frames)]

    print(f"   📋 Slot-aligned frames: {len(frame_specs)}")

    # Extract frames
    frame_paths = []
    for i, (t, slot_start, slot_end, slot_idx) in enumerate(frame_specs):
        fp = f"temp_analysis_{i:03d}.jpg"
        subprocess.run(
            f"ffmpeg -y -ss {t:.2f} -i {video_path} -vframes 1 -q:v 1 {fp}",
            shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        if os.path.exists(fp):
            frame_paths.append((fp, t, slot_start, slot_end, slot_idx))

    cell_w = CANVAS_W // GRID_COLS
    cell_h = CANVAS_H // GRID_ROWS

    grid = Image.new("RGB", (CANVAS_W, CANVAS_H), (0, 0, 0))
    draw = ImageDraw.Draw(grid)

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", max(28, cell_w // 16))
        small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", max(20, cell_w // 24))
    except:
        try:
            font = ImageFont.truetype("/system/fonts/Roboto-Bold.ttf", max(28, cell_w // 16))
            small_font = ImageFont.truetype("/system/fonts/Roboto-Bold.ttf", max(20, cell_w // 24))
        except:
            font = ImageFont.load_default()
            small_font = font

    for idx, (fp, t, slot_start, slot_end, slot_idx) in enumerate(frame_paths):
        if idx >= GRID_COLS * GRID_ROWS:
            break
        try:
            img = Image.open(fp)
            img = ImageOps.fit(img, (cell_w, cell_h), method=Image.LANCZOS, centering=(0.5, 0.5))
        except:
            continue

        x = (idx % GRID_COLS) * cell_w
        y = (idx // GRID_COLS) * cell_h
        grid.paste(img, (x, y))

        # ✅ SLOT time label (yellow) + frame time (cyan)
        slot_label = f"SLOT {slot_idx+1}: {slot_start:.1f}-{slot_end:.1f}s"
        frame_label = f"frame@{t:.2f}s"

        # Black background for readability
        draw.rectangle([x + 6, y + 6, x + 420, y + 100], fill="black")
        draw.text((x + 14, y + 12), slot_label, fill="yellow", font=font)
        draw.text((x + 14, y + 58), frame_label, fill="cyan", font=small_font)

    grid.save(ANALYSIS_GRID_PATH, quality=92, optimize=True, subsampling=2)
    size_8k = os.path.getsize(ANALYSIS_GRID_PATH) / (1024 * 1024)
    print(f"✅ 8K Full Quality: {grid.size[0]}x{grid.size[1]} ({size_8k:.2f} MB)")
    print(f"💾 Saved: {ANALYSIS_GRID_PATH}\n")

    for fp, _, _, _, _ in frame_paths:
        if os.path.exists(fp):
            os.remove(fp)


# ============================================================
# STEP 6 — GPT Call (TIMING LOCK)
# ============================================================
def generate_full_script(slots, srt_content, analysis_grid_path):
    print(f"🤖 [6] Generating FULL script (OpenRouter — {len(OPENROUTER_KEYS)} keys)...")

    slot_lines = []
    for i, s in enumerate(slots, 1):
        sa = s.get("sub_analysis", {})
        slot_lines.append(
            f"- Slot {i}: {s['start']:.1f}s → {s['end']:.1f}s "
            f"[{s['type'].upper()}] "
            f"(scenes={s['scene_count']}, loud={s['avg_loud']}dB, "
            f"action={sa.get('action_ratio', 0)}, dialog={sa.get('dialog_ratio', 0)}, "
            f"motion={sa.get('motion_score', 0)}) "
            f"SRT: \"{s['srt_text'][:70]}\""
        )

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
- Start with reactions: "YO!", "BRO!", "WAIT!", "NAH!", "AYY!", "OHHHH! WOW!"

**REACTION PATTERNS (use 10-14 varied):**
1. BIG ACTION: "OHHHH! He's GONE!", "BRO! That was NASTY!"
2. PREDICTIONS — Predict what's about to happen next.
3. SMART MOVES: "Okay, big brain play right there.", "He's playing this so smart."
4. ENEMY ROAST — Only at the right moment, not every time.
5. EPIC MOMENTS — React when something truly epic or jaw-dropping happens.
6. FULL FREEDOM — Explore the game with suspense and curiosity.
7. HYPE — Start with "okay okay okay", "wait wait wait", "Ayyy", or "Ooo" style phrases.
8. WEIRD — React when something strange or unusual shows up.
9. CLOSE CALL
10. FOLLOW REQUEST (2-3 total): "Ayy if you're vibing, hit that follow yo."
11. FREESTYLE — "React naturally to whatever stands out in the moment."
12. ENVIRONMENT
13. SOUND — React to gunfire, explosions, sound effects, or music at the right moment.
14. CINEMATIC SHOT — React when a shot looks cinematic.
15. FLIRTY/FUNNY "BABY" (1-2 times only): "Let's go baby!"
16. LIKE + BELL CTA (2-3 times only): "Smash that like Button!"
17. SWEARING — Max 5-7 times, only at the right moment. Censor with asterisks. Examples: "Holy sh*t!", "What the f*ck!", "That's bullsh*t!", "What the hell!", "Damn!", "Oh sh*t!", "Motherf*cker!"
18. HMM / THINKING — 2-3 times, only in dialog/calm scenes. Examples: "Hmm interesting...", "Hmm okay...", "Wait a sec...", "Let me think...", "Something's off...", "That's strange..."
19. HYPE INTRO (2-3 times, opening + dialog/calm only)
20. COMMENT CTA — Ask viewers to drop their thoughts or reactions in the comments.
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

**🎯 VISUAL CLASSIFICATION RULES**

**⚠️⚠️⚠️ AGGRESSIVE ACTION DETECTION ⚠️⚠️⚠️**
If you see ANY of these → visual_type = "action":
- 🔥 FIRE, FLAMES, EXPLOSIONS, BLAST
- 💥 SMOKE, SPARKS, DUST
- 🩸 BLOOD, GORE, DAMAGE
- 🔫 WEAPONS FIRING, MUZZLE FLASH
- ⚔️ COMBAT STANCE, FISTS UP, MID-ATTACK
- 👥 MULTIPLE CHARACTERS CLOSE
- 🏃 RUNNING, JUMPING, DODGING
- 💢 CHARACTER BEING HIT, KNOCKED BACK
- 📊 HEALTH BARS, HIT MARKERS
- 🎯 AIMING DOWN SIGHTS
- 🎬 CINEMATIC ACTION, SHAKY CAM
- 3+ CONSECUTIVE frames show above → ACTION

**visual_type = "dialog" ONLY if:**
- Close-up of face while speaking
- Character standing still, facing camera
- Conversation scene

**visual_type = "calm" for EVERYTHING ELSE:**
- Slow camera panning
- City skyline / scenery
- Drone flying in sky
- Menu / UI screens
- Walking slowly
- Environment only shots

**⚠️ BE HONEST. If slow motion/sitting/walking/scenery → "calm".**
**🔴 Two characters CLOSE and ENGAGED → ACTION.**
**🔥 FIRE/EXPLOSIONS/MANY ENEMIES → ACTION.**

**PACING:**
- "action" → 3-5 words, HIGH energy, CAPS
- "dialog" → 5-7 words, conversational
- "calm" → 6-7 words, chill

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

Return ONLY valid JSON:
{{
  "story_summary": "Brief one-line summary.",
  "segments": [
    {{
      "slot": 1,
      "start": 0.0,
      "end": 3.5,
      "text": "...",
      "visual_type": "calm"
    }}
  ]
}}
"""

    or_url = "https://openrouter.ai/api/v1/chat/completions"
    analysis_b64 = encode_image(analysis_grid_path)

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

                    # ✅✅✅ TIMING LOCK — GPT ka start/end ko SLOT se force match karo
                    print(f"   🔒 Locking segment timing to slots...")
                    locked_count = 0
                    for seg in segments:
                        slot_num = seg.get("slot")

                        if slot_num and 1 <= slot_num <= len(slots):
                            exact_slot = slots[slot_num - 1]
                            old_start = seg.get("start")
                            old_end = seg.get("end")
                            if old_start != exact_slot["start"] or old_end != exact_slot["end"]:
                                print(f"      🔒 Slot {slot_num}: {old_start}→{old_end} "
                                      f"⇒ {exact_slot['start']}→{exact_slot['end']}")
                                locked_count += 1
                            seg["start"] = exact_slot["start"]
                            seg["end"] = exact_slot["end"]
                            seg["slot"] = slot_num
                        else:
                            best_slot = None
                            best_diff = 999
                            for s in slots:
                                diff = abs(s["start"] - seg.get("start", 0))
                                if diff < best_diff:
                                    best_diff = diff
                                    best_slot = s
                            if best_slot and best_diff < 3.0:
                                seg["start"] = best_slot["start"]
                                seg["end"] = best_slot["end"]
                                seg["slot"] = slots.index(best_slot) + 1
                                locked_count += 1

                    print(f"   ✅ Locked {locked_count} segments to slot timing")

                    updated_count = 0
                    override_count = 0
                    dialog_protected = 0

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
                            motion = sa.get("motion_score", 0)
                            srt_word_count = len(best_slot.get("srt_text", "").split())

                            best_slot["gpt_type"] = vt

                            signal_says_action_strong = (
                                (signal_type == "action" and action_ratio >= 0.25)
                                or (motion >= 3)
                                or (action_ratio >= 0.30)
                                or (scene_count >= 3 and avg_loud > -18)
                                or (action_ratio > 0.20 and avg_loud > -20)
                            )

                            has_strong_dialog = (
                                srt_word_count >= 8 and action_ratio < 0.40 and motion < 3
                            )

                            is_likely_scenery = (
                                avg_loud < -30 and scene_count == 0 and motion < 2
                            )

                            if (
                                vt == "calm"
                                and signal_says_action_strong
                                and not has_strong_dialog
                                and not is_likely_scenery
                            ):
                                final_type = "action"
                                override_count += 1
                            elif (
                                vt == "calm"
                                and signal_says_action_strong
                                and has_strong_dialog
                            ):
                                final_type = "dialog"
                                dialog_protected += 1
                            else:
                                final_type = vt

                            if (
                                final_type != best_slot.get("type")
                                and final_type == "action"
                            ):
                                best_slot["voice_speed"] = speed_for_type("action")
                                if scene_count >= 3:
                                    best_slot["voice_speed"] = min(
                                        VOICE_SPEED_MAX,
                                        best_slot["voice_speed"] + 0.03
                                    )
                                if avg_loud > -12:
                                    best_slot["voice_speed"] = min(
                                        VOICE_SPEED_MAX,
                                        best_slot["voice_speed"] + 0.03
                                    )
                                if motion >= 5:
                                    best_slot["voice_speed"] = min(
                                        VOICE_SPEED_MAX,
                                        best_slot["voice_speed"] + 0.02
                                    )
                            elif final_type != best_slot.get("type"):
                                best_slot["voice_speed"] = speed_for_type(final_type)

                            best_slot["visual_type"] = final_type
                            best_slot["type"] = final_type
                            best_slot["final_type"] = final_type
                            updated_count += 1

                    print(f"   ✅ Key {key_idx} worked! {len(segments)} segments")
                    print(f"   🎯 Applied to {updated_count}/{len(slots)} slots")
                    print(f"   🔄 Signal overrides: {override_count}")
                    print(f"   🛡️  Dialog protected: {dialog_protected}\n")
                    return segments

                elif r.status_code in (401, 403):
                    print(f"      ❌ Key {key_idx} invalid")
                    break
                elif r.status_code == 429:
                    print(f"      ⚠️ Key {key_idx} rate-limited")
                    time.sleep(2)
                    continue
                elif r.status_code == 402:
                    print(f"      💰 Key {key_idx} — credits khatam")
                    break
                else:
                    print(f"      ⚠️ Error {r.status_code}: {r.text[:200]}")
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

    print("⚠️ All OpenRouter keys failed — using fallback\n")
    FALLBACK = {
        "action": ["Ohh things are heating up!", "He's in the middle of it!",
                   "Chaos everywhere!", "Let him cook!"],
        "dialog": ["Wait, what did he say?", "Hmm interesting...",
                   "He's talking to someone!", "What's the plan here?"],
        "calm":   ["Just vibing here, chilling.", "Too quiet... sus.",
                   "Taking in the view...", "Chill vibes here..."]
    }
    return [
        {"slot": i+1, "start": s["start"], "end": s["end"],
         "text": FALLBACK[s["type"]][i % 4],
         "visual_type": s["type"]}
        for i, s in enumerate(slots)
    ]


# ============================================================
# STEP 7 — ElevenLabs TTS (SLOT-LOCKED + VARIABLE ATEMPO)
# ============================================================
def generate_audio(segments, slots):
    print("🔊 [7] Generating TTS (slot-locked + variable atempo 1.0-1.20)...")
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
        matched_slot = None

        if slot_num and 1 <= slot_num <= len(slots):
            matched_slot = slots[slot_num - 1]
        else:
            best_diff = 999
            for s in slots:
                diff = abs(s["start"] - seg.get("start", 0))
                if diff < best_diff:
                    best_diff = diff
                    matched_slot = s

        if not matched_slot:
            print(f"   ⚠️ seg {idx}: no slot match, skipping")
            continue

        slot_start = matched_slot["start"]
        slot_end = matched_slot["end"]
        target_dur = slot_end - slot_start
        voice_speed = matched_slot.get("voice_speed", 1.0)
        visual_type = (matched_slot.get("type") or "calm").lower().strip()

        seg_file = f"{SEGMENTS_DIR}/seg_{idx:03d}.mp3"
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
                atempo_used = "none"

                if actual > 0 and target_dur > 0:
                    # ✅ VARIABLE ATEMPO — 1.0 se 1.20 ke beech
                    needed_tempo = actual / target_dur
                    tempo = max(ATEMPO_MIN, min(ATEMPO_MAX, needed_tempo))

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
                        atempo_used = f"{tempo:.3f}"
                    else:
                        final = seg_file
                else:
                    final = seg_file

                audio_files.append({
                    "file": final,
                    "start": slot_start,
                    "end": slot_end,
                    "text": text,
                    "visual_type": visual_type
                })

                print(f"   ✅ [{slot_start:5.1f}s] speed={voice_speed:.2f} "
                      f"atempo={atempo_used} ({visual_type or 'signal'}) | {text}")

            elif r.status_code == 401:
                print("   ❌ 401 — ElevenLabs key galat!")
                break
            elif r.status_code == 429:
                print("   ⚠️ 429 — rate limit")
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
# STEP 9 — Final Merge
# ============================================================
def merge_final(video_path, commentary_audio, out_path, audio_files):
    print("🎬 [9] Merging (duck + dynamic volume)...")

    action_times = []
    other_times = []

    for a in audio_files:
        vt = (a.get("visual_type") or "").lower().strip()
        if vt == "action":
            action_times.append(f"between(t,{a['start']:.2f},{a['end']:.2f})")
        else:
            other_times.append(f"between(t,{a['start']:.2f},{a['end']:.2f})")

    all_times = action_times + other_times
    all_conditions = "+".join(all_times) if all_times else "0"
    volume_expr = f"if({all_conditions},{DUCK_VOLUME},1.0)"

    if action_times:
        action_condition = "+".join(action_times)
        vo_volume_expr = f"if({action_condition},{VOL_ACTION},{VOL_OTHER})"
    else:
        vo_volume_expr = f"{VOL_OTHER}"

    filter_complex = (
        f"[0:a]volume='{volume_expr}':eval=frame[bg];"
        f"[1:a]volume='{vo_volume_expr}':eval=frame[vo];"
        f"[bg][vo]amix=inputs=2:duration=first:dropout_transition=0:"
        f"normalize=0,alimiter=limit=0.95[aout]"
    )

    cmd = (
        f'ffmpeg -y -i {video_path} -i {commentary_audio} '
        f'-filter_complex "{filter_complex}" '
        f'-map 0:v:0 -map "[aout]" -c:v copy -shortest {out_path}'
    )
    subprocess.run(cmd, shell=True, check=True)
    print(f"🔥 Final video ready: {out_path}")
    print(f"   🔊 Action volume: {VOL_ACTION}x | Other volume: {VOL_OTHER}x\n")


# ============================================================
# FALLBACK
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
# MAIN
# ============================================================
def main():
    print("=" * 60)
    print("🎙️ AI COMMENTARY DUBBER — v3.9 (Slot Range Fix)")
    print("=" * 60)
    print(f"📹 Input : {FINAL_CLIP_PATH}")
    print(f"📤 Output: {FINAL_DUBBED_VIDEO}")
    print(f"🎤 Voice : {VOICE_ID}")
    print(f"🎛️  Switch: COMMENTARY_ENABLED = {COMMENTARY_ENABLED}")
    print(f"🎮 Speed : {VOICE_SPEED_MIN} - {VOICE_SPEED_MAX}")
    print(f"🎵 atempo: {ATEMPO_MIN} - {ATEMPO_MAX} (variable)")
    print(f"🔊 Volume: Action={VOL_ACTION}x | Other={VOL_OTHER}x")
    print(f"🖼️  Frames: {ANALYSIS_FRAMES} ({GRID_COLS}x{GRID_ROWS}, {CANVAS_W}x{CANVAS_H} 8K)")
    print(f"🤖 Model : openai/gpt-4o-mini (Free)")
    print("=" * 60 + "\n")

    if not COMMENTARY_ENABLED:
        print("🚫 Commentary is OFF — copying original clip...")
        if fallback_copy_original():
            sys.exit(0)
        else:
            sys.exit(1)

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

        # ✅ SLOT-ALIGNED GRID
        build_analysis_grid(FINAL_CLIP_PATH, vid_dur, slots, num_frames=ANALYSIS_FRAMES)

        segments = generate_full_script(slots, srt_content, ANALYSIS_GRID_PATH)

        if not segments:
            raise Exception("No segments generated")

        # ✅ DEBUG: Timing verification
        print("🔍 TIMING VERIFICATION:")
        print(f"   Slots: {len(slots)} | Segments: {len(segments)}")
        for i, seg in enumerate(segments, 1):
            slot_num = seg.get("slot", "?")
            print(f"   Seg {i}: slot={slot_num} | "
                  f"start={seg.get('start'):.2f}s end={seg.get('end'):.2f}s")
        print()

        speeds = [s["voice_speed"] for s in slots]
        print(f"🎮 Final voice speeds: "
              f"min={min(speeds):.2f} max={max(speeds):.2f} "
              f"avg={sum(speeds)/len(speeds):.2f}\n")

        audio_files = generate_audio(segments, slots)
        if not audio_files:
            raise Exception("No audio files generated")

        final_audio = build_timed_audio(audio_files, vid_dur)
        merge_final(FINAL_CLIP_PATH, final_audio, FINAL_DUBBED_VIDEO, audio_files)

        print("=" * 60)
        print(f"🔥🔥 DONE! {FINAL_DUBBED_VIDEO}")
        print(f"📊 Slots: {len(slots)} | Segments: {len(audio_files)}")
        print("=" * 60)

        commit_analysis_to_github()
        sys.exit(0)

    except Exception as e:
        print(f"\n❌ Commentary pipeline failed: {e}")
        print("⚠️ Falling back to original clip...")
        commit_analysis_to_github()
        if fallback_copy_original():
            sys.exit(0)
        else:
            sys.exit(1)


if __name__ == "__main__":
    main()
