"""
AUTO EDITOR — GitHub Action Compatible
========================================
Auto-creates folders if missing.
Supports CLI arguments.
"""

import os
import sys
import json
import math
import random
import base64
import argparse
import cv2
import numpy as np
import librosa
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

from moviepy.editor import (
    VideoFileClip, AudioFileClip, CompositeVideoClip,
    CompositeAudioClip, concatenate_videoclips, TextClip
)
import moviepy.video.fx.all as vfx
from openai import OpenAI


# ==========================================
# AUTO-CREATE FOLDERS
# ==========================================
def ensure_folders():
    """Saare required folders auto-create karta hai."""
    folders = [
        "input",
        "memes/shocked", "memes/funny", "memes/sad", "memes/victory",
        "sfx/hype", "sfx/dramatic", "sfx/funny", "sfx/victory",
        "music",
        "grids",
        "debug",
        "output",
    ]
    for f in folders:
        os.makedirs(f, exist_ok=True)
    print("✅ Folders ready")


# ==========================================
# CONFIG
# ==========================================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
AI_MODEL = "gpt-4o"

MEME_DIR = "./memes"
SFX_DIR = "./sfx"
MUSIC_DIR = "./music"
GRID_DIR = "./grids"
DEBUG_DIR = "./debug"
OUTPUT_DIR = "./output"


# ==========================================
# 1. VIDEO INFO
# ==========================================
def get_video_info(video_path):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise Exception(f"❌ Video open nahi hua: {video_path}")
    
    fps = cap.get(cv2.CAP_PROP_FPS)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total / fps
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    
    return {
        "duration": duration, "fps": fps,
        "width": w, "height": h, "total_frames": total
    }


# ==========================================
# 2. FRAME INDEX
# ==========================================
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


# ==========================================
# 3. GRID GENERATOR
# ==========================================
def create_grids(video_path, frame_index, output_dir="grids", max_images=6):
    duration = frame_index["video_duration"]
    total_frames = frame_index["total_frames"]
    
    num_grids = min(max_images, math.ceil(total_frames / 45))
    frames_per_grid = math.ceil(total_frames / num_grids)
    
    cols = math.ceil(math.sqrt(frames_per_grid * 1.15))
    rows = math.ceil(frames_per_grid / cols)
    thumb_size = min(2000 // cols, 300)
    
    print(f"\n📊 GRID PLAN")
    print(f"   Total frames: {total_frames}")
    print(f"   Grids: {num_grids}")
    print(f"   Frames/grid: {frames_per_grid}")
    print(f"   Layout: {cols}×{rows}")
    print(f"   Thumb size: {thumb_size}px")
    
    cap = cv2.VideoCapture(video_path)
    paths = []
    
    for g in range(num_grids):
        start_idx = g * frames_per_grid
        end_idx = min(start_idx + frames_per_grid, total_frames)
        
        frames = []
        for i in range(start_idx, end_idx):
            f = frame_index["frames"][i]
            t = f["t"]
            idx = f["idx"]
            
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
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
            except:
                font = ImageFont.load_default()
            
            ts = f"{int(t//60):02d}:{t%60:04.1f}"
            label = f"#{idx} | {ts}"
            
            bbox = draw.textbbox((0, 0), label, font=font)
            pad = max(2, thumb_size // 50)
            draw.rectangle([pad, pad, 2*pad + bbox[2], 2*pad + bbox[3]], fill="black")
            draw.text((pad + 2, pad + 1), label, fill="yellow", font=font)
            
            frames.append(np.array(img))
        
        if not frames:
            continue
        
        th, tw = frames[0].shape[:2]
        grid = np.zeros((rows * th, cols * tw, 3), dtype=np.uint8)
        
        for i, f in enumerate(frames):
            r, c = i // cols, i % cols
            if r < rows:
                grid[r*th:(r+1)*th, c*tw:(c+1)*tw] = f
        
        out = os.path.join(output_dir, f"grid_{g+1}.jpg")
        Image.fromarray(grid).save(out, quality=92)
        paths.append(out)
        print(f"   ✅ {out} ({grid.shape[1]}×{grid.shape[0]}px)")
    
    cap.release()
    return paths


# ==========================================
# 4. TRANSCRIPT
# ==========================================
def get_transcript(video_path, use_whisper=True):
    if not use_whisper:
        print("\n⏭️  Whisper skipped")
        return "No transcript"
    
    try:
        import whisper
        print("\n🎙️ Transcribing...")
        model = whisper.load_model("base")
        result = model.transcribe(video_path)
        
        lines = [f"[{s['start']:6.1f}s] {s['text'].strip()}"
                 for s in result["segments"] if s["text"].strip()]
        
        return "\n".join(lines) if lines else "No speech detected"
    except Exception as e:
        print(f"   ⚠️ Whisper error: {e}")
        return "No transcript"


# ==========================================
# 5. SPIKES
# ==========================================
def get_spikes(video_path):
    print("\n🔊 Detecting spikes...")
    try:
        y, sr = librosa.load(video_path, sr=16000, mono=True)
        rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=512)[0]
        hop_sec = 512 / sr
        
        per_sec = []
        for i in range(0, len(rms), int(1/hop_sec)):
            chunk = rms[i:i+int(1/hop_sec)]
            if len(chunk) > 0:
                per_sec.append(float(chunk.max()))
        
        threshold = np.percentile(per_sec, 80)
        spikes = [f"[{i:6.1f}s] 🔊 RMS={v:.3f}"
                  for i, v in enumerate(per_sec) if v > threshold]
        
        return "\n".join(spikes) if spikes else "No spikes"
    except Exception as e:
        print(f"   ⚠️ Spike error: {e}")
        return "No spikes"


# ==========================================
# 6. MOODS
# ==========================================
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


# ==========================================
# 7. AI ANALYSIS
# ==========================================
def ai_analyze(frame_index, grid_paths, transcript, spikes, memes, sfx, music):
    print("\n🤖 Sending to AI...")
    client = OpenAI(api_key=OPENAI_API_KEY)
    
    images = []
    for p in grid_paths:
        with open(p, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        images.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "high"}
        })
    
    frame_lines = [f"#{f['idx']}={f['t']}s" for f in frame_index["frames"][::3]]
    frame_list = "\n".join(frame_lines)
    
    prompt = f"""You are a PROFESSIONAL viral gaming editor with FULL CREATIVE FREEDOM.
Game doesn't matter — works with ANY game.

VIDEO: {frame_index['video_duration']:.1f}s | Sampling: {frame_index['fps_sampling']}fps | Total frames: {frame_index['total_frames']}

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

Return JSON:
{{
  "target_duration": 60,
  "aspect_ratio": "9:16",
  "bg_music": "hype_track.mp3",
  "music_volume": 0.3,
  "edits": [
    {{"start_frame": 0, "end_frame": 15, "remove": true, "reason": "Boring intro"}},
    {{"start_frame": 30, "end_frame": 45, "speed": 1.5, "sfx_mood": "hype", "reason": "Kill moment"}},
    {{"insert_meme": "auto", "meme_mood": "shocked", "reason": "Reaction"}},
    {{"start_frame": 135, "end_frame": 150, "speed": 0.6, "sfx_mood": "dramatic", "zoom": 1.2, "text": "CLUTCH!", "reason": "Clutch 1v3"}}
  ]
}}
"""
    
    response = client.chat.completions.create(
        model=AI_MODEL,
        messages=[{"role": "user", "content": [{"type": "text", "text": prompt}] + images}],
        response_format={"type": "json_object"},
        max_tokens=4000
    )
    
    result = json.loads(response.choices[0].message.content)
    print("   ✅ AI responded")
    return result


# ==========================================
# 8. VERIFY + CONVERT
# ==========================================
def verify_and_convert(ai_json, frame_index):
    print("\n🔍 Verifying...")
    fps_sampling = frame_index["fps_sampling"]
    total_frames = frame_index["total_frames"]
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
    print(f"   ✅ {len(verified)} edits verified")
    return ai_json


# ==========================================
# 9. DEBUG LOG
# ==========================================
def save_debug_log(ai_json, frame_index):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    json_path = os.path.join(DEBUG_DIR, f"edits_{timestamp}.json")
    with open(json_path, "w") as f:
        json.dump(ai_json, f, indent=2)
    
    lines = []
    lines.append("=" * 70)
    lines.append(f"AI EDIT DECISIONS — {timestamp}")
    lines.append("=" * 70)
    lines.append(f"Video: {frame_index['video_duration']:.1f}s | "
                 f"Frames: {frame_index['total_frames']} | "
                 f"Target: {ai_json.get('target_duration')}s | "
                 f"Aspect: {ai_json.get('aspect_ratio')}")
    lines.append("")
    
    for i, edit in enumerate(ai_json.get("edits", []), 1):
        lines.append(f"--- EDIT #{i} ---")
        if "insert_meme" in edit:
            lines.append(f"  TYPE: MEME | Mood: {edit.get('meme_mood')}")
            lines.append(f"  Reason: {edit.get('reason', '-')}")
        elif edit.get("remove"):
            lines.append(f"  TYPE: CUT | Frames: {edit['start_frame']}-{edit['end_frame']} "
                         f"({edit['start']:.1f}s-{edit['end']:.1f}s)")
            lines.append(f"  Reason: {edit.get('reason', '-')}")
        else:
            lines.append(f"  TYPE: KEEP | Frames: {edit['start_frame']}-{edit['end_frame']} "
                         f"({edit['start']:.1f}s-{edit['end']:.1f}s) | Speed: {edit.get('speed', 1.0)}x")
            if "sfx_mood" in edit:
                lines.append(f"  SFX: {edit['sfx_mood']}")
            if "text" in edit:
                lines.append(f"  Text: {edit['text']}")
            lines.append(f"  Reason: {edit.get('reason', '-')}")
        lines.append("")
    
    log_path = os.path.join(DEBUG_DIR, f"debug_{timestamp}.txt")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    
    print("\n" + "\n".join(lines))
    print(f"\n💾 Debug: {log_path}")
    return log_path


# ==========================================
# 10. MOOD PICKERS
# ==========================================
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


# ==========================================
# 11. ASPECT + FILTER
# ==========================================
def apply_aspect(clip, ratio="9:16"):
    w, h = clip.size
    if ratio == "9:16":
        tw = h * (9/16)
        if tw <= w:
            return clip.fx(vfx.crop, x_center=w/2, y_center=h/2, width=tw, height=h)
        th = w * (16/9)
        return clip.fx(vfx.crop, x_center=w/2, y_center=h/2, width=w, height=th)
    elif ratio == "1:1":
        m = min(w, h)
        return clip.fx(vfx.crop, x_center=w/2, y_center=h/2, width=m, height=m)
    elif ratio == "4:5":
        tw = h * (4/5)
        if tw <= w:
            return clip.fx(vfx.crop, x_center=w/2, y_center=h/2, width=tw, height=h)
        th = w * (5/4)
        return clip.fx(vfx.crop, x_center=w/2, y_center=h/2, width=w, height=th)
    return clip


def apply_filter(clip, name):
    try:
        if name == "cinematic":
            clip = clip.fx(vfx.colorx, 0.9).fx(vfx.lum_contrast, contrast=20)
        elif name == "vivid":
            clip = clip.fx(vfx.colorx, 1.3)
        elif name == "cold":
            clip = clip.fx(vfx.colorx, 0.9)
        elif name == "vintage":
            clip = clip.fx(vfx.colorx, 0.8)
    except:
        pass
    return clip


# ==========================================
# 12. BUILD REEL
# ==========================================
def build_reel(video_path, ai_json, output_path):
    print("\n🎬 Building reel...")
    
    main = VideoFileClip(video_path)
    aspect = ai_json.get("aspect_ratio", "9:16")
    clips = []
    sfx_tracks = []
    current_time = 0.0
    
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
                    print(f"   ✅ Meme ({mood}): {os.path.basename(meme_path)}")
                except Exception as e:
                    print(f"   ⚠️ Meme error: {e}")
            continue
        
        if edit.get("remove", False):
            print(f"   ✂️ Cut: frames {edit.get('start_frame')}-{edit.get('end_frame')}")
            continue
        
        start = edit.get("start")
        end = edit.get("end")
        if start is None or end is None:
            continue
        
        try:
            seg = main.subclip(start, end)
            
            speed = edit.get("speed", 1.0)
            if speed != 1.0:
                seg = seg.fx(vfx.speedx, speed)
            
            zoom = edit.get("zoom")
            if zoom:
                seg = seg.fx(vfx.resize, zoom)
            
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
                except Exception as e:
                    print(f"   ⚠️ Text error: {e}")
            
            sfx_mood = edit.get("sfx_mood")
            if sfx_mood:
                sfx_path = pick_sfx(sfx_mood)
                if sfx_path:
                    try:
                        sfx = AudioFileClip(sfx_path).set_start(current_time)
                        sfx_tracks.append(sfx)
                        print(f"   🔊 SFX ({sfx_mood})")
                    except Exception as e:
                        print(f"   ⚠️ SFX error: {e}")
            
            clips.append(seg)
            current_time += seg.duration
            print(f"   ✅ Keep: {start}-{end}s @ {speed}x")
        except Exception as e:
            print(f"   ⚠️ Clip error: {e}")
    
    if not clips:
        print("❌ No clips!")
        return None
    
    final = concatenate_videoclips(clips, method="compose")
    
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
                    music = music.loop(duration=final.duration)
                audio.append(music)
                print(f"   🎵 Music: {ai_json['bg_music']}")
            except Exception as e:
                print(f"   ⚠️ Music error: {e}")
    
    if audio:
        final = final.set_audio(CompositeAudioClip(audio))
    
    final.write_videofile(
        output_path, codec="libx264", audio_codec="aac",
        fps=30, preset="medium", threads=4,
        verbose=False, logger=None
    )
    
    print(f"\n🎬 Final: {output_path} ({final.duration:.1f}s)")
    return output_path


# ==========================================
# 13. MAIN
# ==========================================
def main():
    parser = argparse.ArgumentParser(description="Auto Video Editor")
    parser.add_argument("--video", default="input/gameplay.mp4", help="Input video")
    parser.add_argument("--fps", type=int, default=3, help="Frames per second")
    parser.add_argument("--grids", type=int, default=6, help="Max grids")
    parser.add_argument("--whisper", default="true", help="Use Whisper")
    args = parser.parse_args()
    
    # Auto-create folders
    ensure_folders()
    
    print("=" * 70)
    print("🎬 AUTO EDITOR — GitHub Action Mode")
    print("=" * 70)
    
    if not os.path.exists(args.video):
        print(f"❌ Video nahi mila: {args.video}")
        sys.exit(1)
    
    if not OPENAI_API_KEY:
        print("❌ OPENAI_API_KEY set nahi hai!")
        sys.exit(1)
    
    use_whisper = str(args.whisper).lower() == "true"
    
    # 1. Info
    print(f"\n📹 Video: {args.video}")
    info = get_video_info(args.video)
    print(f"   Duration: {info['duration']:.1f}s")
    print(f"   Resolution: {info['width']}×{info['height']}")
    
    # 2. Frame index
    frame_index = create_frame_index(args.video, args.fps)
    print(f"\n📊 Frames: {frame_index['total_frames']}")
    
    # 3. Grids
    grids = create_grids(args.video, frame_index, GRID_DIR, args.grids)
    
    # 4. Transcript
    transcript = get_transcript(args.video, use_whisper)
    
    # 5. Spikes
    spikes = get_spikes(args.video)
    
    # 6. Moods
    memes, sfx, music = get_available_moods()
    print(f"\n📦 Memes: {list(memes.keys())}")
    print(f"📦 SFX: {list(sfx.keys())}")
    print(f"📦 Music: {len(music)}")
    
    # 7. AI
    ai_json = ai_analyze(frame_index, grids, transcript, spikes, memes, sfx, music)
    
    # 8. Verify
    ai_json = verify_and_convert(ai_json, frame_index)
    
    # 9. Debug
    save_debug_log(ai_json, frame_index)
    
    # 10. Build
    output = os.path.join(OUTPUT_DIR, "final_reel.mp4")
    build_reel(args.video, ai_json, output)
    
    print("\n" + "=" * 70)
    print("✅ DONE!")
    print("=" * 70)


if __name__ == "__main__":
    main()
