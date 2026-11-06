#!/usr/bin/env python3
"""
🎮 MASTER AGENT v36.0 — EXACT DEFICIT BUFFER (USER MATH)
======================================================================
✅ Calculates EXACT buffer using: Source_Duration * (1 - CPU_Speed).
✅ Adds safety margin for heavy filter throttling.
✅ No full pre-encode. Streams simultaneously after precise buffer.
"""
import os
import sys
import json
import re
import time
import signal
import subprocess
import requests
import glob
import threading
import queue
from datetime import datetime, timedelta, timezone

# ═══════════════════════════════════════════════════════════
# CONFIG & UTILS
# ═══════════════════════════════════════════════════════════
def log(msg, end="\n"):
    sys.stderr.write(f"{msg}{end}")
    sys.stderr.flush()

INTERRUPTED = False
def _sigint_handler(signum, frame):
    global INTERRUPTED
    INTERRUPTED = True
    log("\n⚠️ Signal — stopping...")
signal.signal(signal.SIGINT, _sigint_handler)
signal.signal(signal.SIGTERM, _sigint_handler)

STREAM_ENABLED     = os.getenv("STREAM_ENABLED", "true").lower() == "true"
STREAM_MODE        = os.getenv("STREAM_MODE", "both").lower().strip()
if STREAM_MODE not in ("fb", "yt", "both"): STREAM_MODE = "both"

MANUAL_FB_KEY = os.getenv("MANUAL_FB_KEY", "").strip()
MANUAL_YT_KEY = os.getenv("MANUAL_YT_KEY", "").strip()
SECRET_FB_KEY = (os.getenv("FACEBOOK_STREAM_KEY") or "").strip()
SECRET_YT_KEY = (os.getenv("YOUTUBE_STREAM_KEY") or "").strip()

FACEBOOK_KEY = MANUAL_FB_KEY if MANUAL_FB_KEY else SECRET_FB_KEY
YOUTUBE_KEY  = MANUAL_YT_KEY if MANUAL_YT_KEY else SECRET_YT_KEY

USE_YT = STREAM_MODE in ("yt", "both") and bool(YOUTUBE_KEY)
USE_FB = STREAM_MODE in ("fb", "both") and bool(FACEBOOK_KEY)
STREAMING_ENABLED = STREAM_ENABLED and (USE_YT or USE_FB)

MANUAL_VIDEO_URL = os.getenv("MANUAL_VIDEO_URL", "").strip()
AUDIO_URL      = os.getenv("AUDIO_URL", "").strip()
RATIO          = os.getenv("RATIO", "3")
FILTER         = os.getenv("FILTER", "2")
SPEED_OPT      = os.getenv("SPEED", "1")  
FPS_OPT        = os.getenv("FPS", "1") 
BITRATE        = os.getenv("BITRATE", "8") 
STREAM_GAP_MIN = int(os.getenv("STREAM_GAP_MIN", "2"))
META_ARTIST    = os.getenv("META_ARTIST", "PremxGamer")

TARGET_FPS = "30" if FPS_OPT == "1" else "60"

LOOP_INPUT = os.getenv("LOOP_COUNT", "0").strip().lower()
LOOP_ARG = ""
MAX_RUN_SECONDS = 5 * 3600 + 30 * 60 

if LOOP_INPUT in ("24", "24h", "24h/24", "-1", "infinite", "inf"):
    LOOP_ARG = "-stream_loop -1 "
    MAX_RUN_SECONDS = 24 * 3600
else:
    try:
        plays = int(LOOP_INPUT)
        if plays > 1:
            LOOP_ARG = f"-stream_loop {plays - 1} "
    except ValueError:
        pass

try:
    from zoneinfo import ZoneInfo
    IST = ZoneInfo("Asia/Kolkata")
except Exception:
    IST = timezone(timedelta(hours=5, minutes=30))

def now_ist_ampm():
    return datetime.now(IST).strftime("%Y-%m-%d %I:%M:%S %p")

LOGS_DIR = "gaming_runtime_v8"
for d in [LOGS_DIR, "Manual_links", "game_links_livestream", "game_links_streamed"]:
    os.makedirs(d, exist_ok=True)

def _tee():
    o = []
    if USE_YT: o.append(f"[f=flv]rtmp://a.rtmp.youtube.com/live2/{YOUTUBE_KEY}")
    if USE_FB: o.append(f"[f=flv]rtmps://live-api-s.facebook.com:443/rtmp/{FACEBOOK_KEY}")
    return "|".join(o)

# ═══════════════════════════════════════════════════════════
# ⚡ GET SOURCE DURATION & SMART TEST
# ═══════════════════════════════════════════════════════════
def get_video_duration(url):
    log("⏱️ Probing source video duration...")
    cmd = f'ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{url}"'
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        duration_str = result.stdout.strip()
        if duration_str:
            dur = float(duration_str)
            log(f"   📏 Source Duration: {int(dur // 60)}m {int(dur % 60)}s ({int(dur)} seconds)")
            return dur
    except Exception as e:
        pass
    return 0

def run_smart_test(url, vf_chain, base_enc_flags):
    log("🔍 Pre-Flight Test: Checking CPU & Network...")
    cmd = f'ffmpeg -hide_banner -loglevel info -t 10 -rtbufsize 512M -thread_queue_size 8192 -i "{url}" -filter_complex "[0:v]{vf_chain}[vid]" -map "[vid]" {base_enc_flags} -f null -'
    cpu_speed = 0.0
    try:
        p = subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        start = time.time()
        while p.poll() is None:
            if time.time() - start > 15:
                p.kill()
                break
            line = p.stderr.readline()
            if not line: continue
            match = re.search(r"speed=\s*([\d\.]+)x", line)
            if match:
                cpu_speed = max(cpu_speed, float(match.group(1)))
    except Exception:
        cpu_speed = 0.0

    log(f"   🖥️ CPU Speed: {cpu_speed}x")
    return cpu_speed

# ═══════════════════════════════════════════════════════════
# STREAMING (User Math + Safety Margin)
# ═══════════════════════════════════════════════════════════
def stream_direct(url, game_name):
    n = int(USE_YT) + int(USE_FB)
    if n == 0: return False

    source_duration = get_video_duration(url)

    CROP = ""
    if RATIO == "1": CROP = "scale=1080:1080:force_original_aspect_ratio=increase,crop=1080:1080,"
    elif RATIO == "2": CROP = "scale=1080:1350:force_original_aspect_ratio=increase,crop=1080:1350,"
    elif RATIO == "3": CROP = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
    elif RATIO == "4": CROP = "scale=1080:1440:force_original_aspect_ratio=increase,crop=1080:1440,"
    elif RATIO == "5": CROP = "scale=1440:1080:force_original_aspect_ratio=increase,crop=1440:1080,"

    GAME = ""
    if FILTER == "1": GAME = "eq=brightness=0.02:contrast=1.18:saturation=1.25,hqdn3d=1.5:1.5:6:6,unsharp=3:3:0.75:3:3:0.0,"
    elif FILTER == "2": GAME = "eq=brightness=0.02:contrast=1.20:saturation=1.22:gamma=1.11,vibrance=intensity=0.20,hqdn3d=1.5:1.5:6:6,cas=0.3,noise=alls=3:allf=t+u,unsharp=3:3:0.75:3:3:0.0,"
    elif FILTER == "3": GAME = "scale=flags=lanczos+accurate_rnd:param0=3.0,eq=brightness=0.02:contrast=1.10:saturation=1.10:gamma=1.10,vibrance=intensity=0.10,hqdn3d=1.0:1.0:3:3,cas=0.15,noise=alls=2:allf=t+u,unsharp=3:3:0.2:3:3:0.0,"
    elif FILTER == "4": GAME = "eq=brightness=0.15:contrast=1.20:gamma=1.25,unsharp=5:5:1.0:5:5:0.0,"
    elif FILTER == "5": GAME = "eq=contrast=1.25:saturation=1.20,colorbalance=rs=0.08:gs=0.02:bs=-0.08,unsharp=5:5:1.2:5:5:0.0,"
    elif FILTER == "6": GAME = "eq=contrast=1.35:saturation=1.55:gamma=1.05,unsharp=7:7:2.5:7:7:0.0,"

    vf_chain = f"{CROP}{GAME}fps={TARGET_FPS}:round=near,scale=trunc(iw/2)*2:trunc(ih/2)*2"
    B_V = f"{BITRATE}M"
    BUF = f"{int(BITRATE)*2}M"

    base_enc_flags = (
        f"-c:v libx264 -preset ultrafast -threads 0 -profile:v high -level:v 4.2 "
        f"-pix_fmt yuv420p -b:v {B_V} -maxrate {B_V} -bufsize {BUF} "
        f"-r {TARGET_FPS} -fps_mode cfr -vsync cfr "
        f"-g {TARGET_FPS} -keyint_min {TARGET_FPS} -sc_threshold 0 "
        f"-c:a aac -b:a 128k -ar 44100 -ac 2 "
        f"-max_muxing_queue_size 16384 "
    )

    cpu_speed = run_smart_test(url, vf_chain, base_enc_flags)
    
    if cpu_speed <= 0: cpu_speed = 0.3 # Default safety

    # 🔥 USER'S EXACT MATH + 15% SAFETY MARGIN
    if source_duration > 0:
        # Deficit = Total Time * (1 - CPU Speed)
        deficit_secs = int(source_duration * (1.0 - cpu_speed))
        
        # Add 15% safety margin because CPU drops speed during heavy load
        safety_margin = int(deficit_secs * 0.15)
        auto_buffer_secs = deficit_secs + safety_margin
        
        log(f"📐 User Math Applied: Deficit={deficit_secs}s, +15% Safety Margin={safety_margin}s.")
        log(f"⚙️ Final Buffer Required: {auto_buffer_secs} seconds ({auto_buffer_secs/60:.1f} mins)")
    else:
        auto_buffer_secs = 300 # 5 mins fallback
        
    log(f"   Pre-buffering {auto_buffer_secs}s of RE-ENCODED video in RAM...")

    inputs = f'{LOOP_ARG}-re -rtbufsize 2G -thread_queue_size 16384 -rw_timeout 120000000 -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -i "{url}" '
    
    filter_complex = f'[0:v]{vf_chain}[vid]'
    video_map = "-map \"[vid]\" "
    audio_map = f'-map 0:a? -af "aresample=48000" '

    if n == 1:
        target = f"rtmp://a.rtmp.youtube.com/live2/{YOUTUBE_KEY}" if USE_YT else f"rtmps://live-api-s.facebook.com:443/rtmp/{FACEBOOK_KEY}"
        out_format = f'-f flv "{target}"'
    else:
        tee = _tee()
        out_format = f'-f tee "{tee}"'

    cmd1 = f'ffmpeg -hide_banner -loglevel error -stats {inputs} -filter_complex "{filter_complex}" {video_map}{audio_map} {base_enc_flags} -flush_packets 1 -f mpegts pipe:1'
    
    # 🔥 Added -re in p2 so FB data is received at 1x speed
    cmd2 = f'ffmpeg -hide_banner -loglevel info -stats -re -f mpegts -i pipe:0 -c copy -flvflags no_duration_filesize {out_format}'

    p1 = subprocess.Popen(cmd1, shell=True, stdout=subprocess.PIPE)
    p2 = subprocess.Popen(cmd2, shell=True, stdin=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=False)

    def read_p2_logs():
        try:
            for line_bytes in iter(p2.stderr.readline, b''):
                safe = line_bytes.decode('utf-8', errors='ignore').strip()
                if "frame=" in safe or "speed=" in safe or "error" in safe.lower():
                    log(f"      [Sending] {safe[:150]}")
        except Exception: pass

    threading.Thread(target=read_p2_logs, daemon=True).start()

    target_buffer_bytes = int(BITRATE) * 1000000 // 8 * auto_buffer_secs
    buffer = bytearray()
    
    log(f"   $ Buffering Data (Target: {target_buffer_bytes / (1024*1024):.1f} MB)...")
    
    try:
        while len(buffer) < target_buffer_bytes:
            chunk = p1.stdout.read(1024 * 1024) 
            if not chunk:
                break
            
            buffer.extend(chunk)
            percent = (len(buffer) / target_buffer_bytes) * 100
            if len(buffer) % (10 * 1024 * 1024) < (1024*1024):
                log(f"      📦 Buffering: {percent:.1f}% complete...")
        
        if len(buffer) > 0:
            log(f"\n✅ Buffer FULL ({len(buffer)/(1024*1024):.1f} MB)! Starting Stream to FB...")
            
            stream_queue = queue.Queue(maxsize=50)
            
            def writer_thread_func():
                try:
                    chunk_sz = 1024 * 1024
                    for i in range(0, len(buffer), chunk_sz):
                        if INTERRUPTED: break
                        stream_queue.put(buffer[i:i+chunk_sz])
                    
                    while True:
                        chunk = p1.stdout.read(chunk_sz)
                        if not chunk:
                            break
                        stream_queue.put(chunk)
                except Exception:
                    pass
                finally:
                    stream_queue.put(None)

            threading.Thread(target=writer_thread_func, daemon=True).start()

            while True:
                try:
                    q_chunk = stream_queue.get(timeout=1)
                    if q_chunk is None:
                        break
                    p2.stdin.write(q_chunk)
                    p2.stdin.flush()
                except queue.Empty:
                    if p1.poll() is not None:
                        break
                except Exception as e:
                    log(f"❌ Stream Write Error: {e}")
                    break
            
            log("✅ Stream processing finished.")
                
    except Exception as e:
        log(f"❌ Pipeline Error: {e}")
    finally:
        p1.terminate()
        p2.terminate()
        
    return True

def main():
    log("=" * 62)
    log("🎮 MASTER AGENT v36.0 — EXACT DEFICIT BUFFER")
    log("=" * 62)

    if MANUAL_VIDEO_URL:
        game = "Manual_Game"
        url = MANUAL_VIDEO_URL
    else:
        log("❌ No Manual URL. Provide URL.")
        return

    gap_seconds = STREAM_GAP_MIN * 60
    if gap_seconds > 0:
        log(f"⏳ Waiting for {STREAM_GAP_MIN} minutes...")
        time.sleep(gap_seconds)

    log(f"\n📡 Initializing Stream...")
    ok = stream_direct(url, game)
    
    log("\n" + "=" * 62)
    log(f"{'✅ Complete' if ok else '❌ Failed'}")
    log("=" * 62)

if __name__ == "__main__":
    main()