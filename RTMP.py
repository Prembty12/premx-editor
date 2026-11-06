#!/usr/bin/env python3
"""
🎮 MASTER AGENT v33.0 — PERFECT SMOOTH BUFFER (RTMP SAFE)
======================================================================
✅ Fixes "Stream stops after 5 seconds" bug (RTMP Pacing)
✅ Uses Threaded Queue to feed Facebook at real-time speed
✅ Prevents CPU/Buffer starvation
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

MAX_STREAM_RETRIES = int(os.getenv("MAX_STREAM_RETRIES", "3"))
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
    LOOP_MSG = "Infinite (24 Hours)"
else:
    try:
        plays = int(LOOP_INPUT)
        if plays > 1:
            LOOP_ARG = f"-stream_loop {plays - 1} "
            LOOP_MSG = f"{plays} Times"
        else:
            LOOP_MSG = "Once (No Loop)"
    except ValueError:
        LOOP_MSG = "Once (Default)"

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

def _extract_game(fpath):
    base = os.path.basename(fpath)
    for suf in ["_manual.txt", "_links_livestream.txt", "_livestream.txt", ".txt"]:
        if base.endswith(suf): return base[:-len(suf)].strip()
    return base.replace(".txt", "").strip()

def get_source_file(game, g2m, g2a):
    mf = g2m.get(game)
    if mf and os.path.exists(mf):
        try:
            with open(mf, 'r', encoding='utf-8', errors='ignore') as fh:
                if re.findall(r'https?://', fh.read()): return mf, "manual"
        except Exception: pass
    af = g2a.get(game)
    if af and os.path.exists(af):
        try:
            with open(af, 'r', encoding='utf-8', errors='ignore') as fh:
                if re.findall(r'https?://', fh.read()): return af, "livestream"
        except Exception: pass
    return None, None

def run_brain():
    log("🧠 Brain: rotation...")
    mf = glob.glob(os.path.join(MANUAL_DIR, "*.txt"))
    af = glob.glob(os.path.join(AUTO_DIR, "*.txt"))
    g2m, g2a = {}, {}
    for f in mf:
        g = _extract_game(f)
        if g: g2m[g] = f
    for f in af:
        g = _extract_game(f)
        if g: g2a[g] = f
    
    game_list = sorted(g2a.keys())
    if not game_list: return None

    mem_file = f"{LOGS_DIR}/agent_memory.json"
    memory = {"last_played_game": ""}
    if os.path.exists(mem_file):
        try:
            with open(mem_file, 'r', encoding='utf-8') as f:
                d = json.load(f)
                if isinstance(d, dict): memory.update(d)
        except Exception: pass

    last = memory.get("last_played_game", "")
    chosen = game_list[(game_list.index(last) + 1) % len(game_list)] if last in game_list else game_list[0]

    source_file, source_kind = None, None
    attempts = 0
    while attempts < len(game_list):
        sf, kind = get_source_file(chosen, g2m, g2a)
        if sf:
            source_file, source_kind = sf, kind
            log(f"✅ Pick: {chosen} [{kind}]")
            break
        ci = game_list.index(chosen)
        chosen = game_list[(ci + 1) % len(game_list)]
        attempts += 1

    if not source_file: return None

    try:
        with open(source_file, 'r', encoding='utf-8', errors='ignore') as f: content = f.read()
        pipe = [u.rstrip('.,;)\']"') for u in re.findall(r'\|\s*Link:\s*(https?://[^\s\n\r\)\]\'"<>,;]+)', content)]
        all_urls = pipe if pipe else re.findall(r'https?://[^\s\n\r\)\]\'"<>,;]+', content)
        source_url = all_urls[0] if all_urls else ""
    except Exception: source_url = ""

    if not source_url: return None

    memory["last_played_game"] = chosen
    try:
        with open(mem_file, 'w', encoding='utf-8') as f: json.dump(memory, f, indent=2)
    except Exception: pass
    
    return {"game_name": chosen, "source_url": source_url, "source_file": source_file}

def _tee():
    o = []
    if USE_YT: o.append(f"[f=flv]rtmp://a.rtmp.youtube.com/live2/{YOUTUBE_KEY}")
    if USE_FB: o.append(f"[f=flv]rtmps://live-api-s.facebook.com:443/rtmp/{FACEBOOK_KEY}")
    return "|".join(o)

# ═══════════════════════════════════════════════════════════
# ⚡ GET SOURCE DURATION
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
        log(f"   ⚠️ Could not probe duration: {e}")
    return 0

# ═══════════════════════════════════════════════════════════
# ⚡ SMART DUAL-TEST (CPU + NETWORK DOWN/UP)
# ═══════════════════════════════════════════════════════════
def get_network_speeds():
    log("🌐 Checking Network Download & Upload Speed...")
    try:
        import speedtest
        st = speedtest.Speedtest()
        st.get_best_server()
        download_mbps = st.download() / 1_000_000
        upload_mbps = st.upload() / 1_000_000
        return download_mbps, upload_mbps
    except Exception as e:
        log(f"   ⚠️ Speedtest error: {e}. Defaulting to 0.")
        return 0, 0

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
    except Exception as e:
        log(f"   ❌ CPU Test error: {e}")
        cpu_speed = 0.0

    log(f"   🖥️ CPU Speed: {cpu_speed}x")
    download_speed, upload_speed = get_network_speeds()
    log(f"   ⬇️ Download Speed: {download_speed:.2f} Mbps")
    log(f"   ⬆️ Upload Speed: {upload_speed:.2f} Mbps")
    
    required_net = int(BITRATE) * 1.5 
    
    if cpu_speed >= 0.95 and download_speed >= required_net and upload_speed >= required_net:
        log(f"   ✅ SYSTEM IS FAST.")
        return True, cpu_speed
    else:
        log(f"   ⚠️ SYSTEM IS SLOW/BOTTLENECKED.")
        return False, cpu_speed

# ═══════════════════════════════════════════════════════════
# STREAMING (Threaded Queue System)
# ═══════════════════════════════════════════════════════════
def stream_direct(url, game_name):
    if not STREAMING_ENABLED: return False
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

    V_SPEED, A_SPEED = "", ""
    if SPEED_OPT == "2": V_SPEED, A_SPEED = "setpts=0.9523*PTS,", "atempo=1.05,"
    elif SPEED_OPT == "3": V_SPEED, A_SPEED = "setpts=0.9090*PTS,", "atempo=1.10,"
    elif SPEED_OPT == "4": V_SPEED, A_SPEED = "setpts=0.8*PTS,", "atempo=1.25,"
    elif SPEED_OPT == "5": V_SPEED, A_SPEED = "setpts=0.6666*PTS,", "atempo=1.5,"
    elif SPEED_OPT == "6": V_SPEED, A_SPEED = "setpts=1.25*PTS,", "atempo=0.8,"

    B_V = f"{BITRATE}M"
    BUF = f"{int(BITRATE)*2}M"

    vf_chain = f"{V_SPEED}{CROP}{GAME}fps={TARGET_FPS}:round=near,scale=trunc(iw/2)*2:trunc(ih/2)*2"
    af_chain = f"{A_SPEED}aresample=48000"
    META_TITLE = f"{game_name} Gameplay"
    
    base_enc_flags = (
        f"-c:v libx264 -preset ultrafast -threads 0 -profile:v high -level:v 4.2 "
        f"-pix_fmt yuv420p -b:v {B_V} -maxrate {B_V} -bufsize {BUF} "
        f"-r {TARGET_FPS} -fps_mode cfr -vsync cfr "
        f"-g {TARGET_FPS} -keyint_min {TARGET_FPS} -sc_threshold 0 "
        f"-c:a aac -b:a 128k -ar 44100 -ac 2 "
        f"-metadata title=\"{META_TITLE}\" -metadata artist=\"{META_ARTIST}\" "
        f"-max_muxing_queue_size 16384 "
    )

    is_fast_system, cpu_speed = run_smart_test(url, vf_chain, base_enc_flags)

    inputs = f'{LOOP_ARG}-re -rtbufsize 2G -thread_queue_size 16384 -rw_timeout 120000000 -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -i "{url}" '
    
    filter_complex = ""
    audio_map = ""
    video_map = ""
    
    audio_file_exists = False
    if AUDIO_URL:
        log("🎵 Fetching optional audio...")
        subprocess.run(f'yt-dlp --extract-audio --audio-format mp3 "{AUDIO_URL}" -o "optional_audio.mp3"', shell=True)
        if os.path.exists("optional_audio.mp3"):
            audio_file_exists = True
            inputs += '-thread_queue_size 4096 -i "optional_audio.mp3" '
            filter_complex = f'[0:v]{vf_chain}[vid];[1:a]{af_chain}[a_out]'
            audio_map = "-map \"[a_out]\" "

    if os.path.exists("logo.png"):
        inputs += '-i "logo.png" '
        logo_idx = 2 if audio_file_exists else 1
        if audio_file_exists:
            filter_complex += f';[{logo_idx}:v]scale=160:-1[logo];[vid][logo]overlay=30:H-h-20[v_out]'
        else:
            filter_complex = f'[0:v]{vf_chain}[vid];[{logo_idx}:v]scale=160:-1[logo];[vid][logo]overlay=30:H-h-20[v_out]'
        log("🏷️ Watermark applied.")
        video_map = "-map \"[v_out]\" "
    else:
        if not audio_file_exists:
            filter_complex = f'[0:v]{vf_chain}[vid]'
        video_map = "-map \"[vid]\" "

    if not audio_file_exists:
        audio_map = f'-map 0:a? -af "{af_chain}" '

    if n == 1:
        target = f"rtmp://a.rtmp.youtube.com/live2/{YOUTUBE_KEY}" if USE_YT else f"rtmps://live-api-s.facebook.com:443/rtmp/{FACEBOOK_KEY}"
        out_format = f'-f flv "{target}"'
    else:
        tee = _tee()
        out_format = f'-f tee "{tee}"'

    if is_fast_system:
        log("🚀 System is FAST! Streaming Immediately.")
        cmd = f'ffmpeg -hide_banner -loglevel info -stats {inputs} -filter_complex "{filter_complex}" {video_map}{audio_map} {base_enc_flags} -rtmp_buffer 30000 -flvflags no_duration_filesize {out_format}'
        try:
            p = subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, universal_newlines=True)
            start = time.time()
            while p.poll() is None:
                if INTERRUPTED: p.terminate(); return False
                if MAX_RUN_SECONDS and (time.time() - start) > MAX_RUN_SECONDS: p.terminate(); return True
                line = p.stderr.readline()
                if line and ("frame=" in line or "speed=" in line):
                    log(f"      ⏳ {line.strip()[:120]}")
            return p.returncode == 0
        except Exception:
            return False
    
    else:
        if cpu_speed <= 0: cpu_speed = 0.5 
        
        if source_duration > 0:
            deficit_ratio = 1.0 - cpu_speed
            calc_buffer = int(source_duration * deficit_ratio) + 15
            auto_buffer_secs = max(30, min(int(source_duration - 10), calc_buffer))
        else:
            f_load = {"1": 1.0, "2": 1.5, "3": 2.0, "4": 1.2, "5": 1.1, "6": 1.4}.get(FILTER, 1.5)
            b_load = int(BITRATE) / 8.0
            calc_buffer = int((60 / cpu_speed) * f_load * b_load)
            auto_buffer_secs = max(60, min(600, calc_buffer))

        log(f"🐢 System is SLOW (CPU: {cpu_speed}x | Filter: {FILTER} | Bitrate: {BITRATE}M).")
        log(f"⚙️ Smart Auto-Adjusted Buffer: {auto_buffer_secs} seconds ({auto_buffer_secs/60:.1f} mins)")
        log(f"   Pre-buffering {auto_buffer_secs}s of RE-ENCODED video in RAM...")
        
        # 🔥 Add -flush_packets 1 to p1 so it sends data immediately
        cmd1 = f'ffmpeg -hide_banner -loglevel error -stats {inputs} -filter_complex "{filter_complex}" {video_map}{audio_map} {base_enc_flags} -flush_packets 1 -f mpegts pipe:1'
        
        # 🔥 ADDED -re to p2 so Facebook gets data at real-time (Fixes 3-sec drop)
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
            
            # Buffer is full, now start streaming
            if len(buffer) > 0:
                log(f"\n✅ Buffer FULL ({len(buffer)/(1024*1024):.1f} MB)! Starting Stream to FB...")
                
                # Create Queue for real-time pacing
                stream_queue = queue.Queue(maxsize=50) # 50MB max RAM queue
                
                def writer_thread_func():
                    try:
                        # Write the initial buffer to queue in 1MB chunks
                        chunk_sz = 1024 * 1024
                        for i in range(0, len(buffer), chunk_sz):
                            if INTERRUPTED: break
                            stream_queue.put(buffer[i:i+chunk_sz])
                        
                        # Keep passing data from p1 to queue
                        while True:
                            chunk = p1.stdout.read(chunk_sz)
                            if not chunk:
                                break
                            stream_queue.put(chunk)
                    except Exception:
                        pass
                    finally:
                        stream_queue.put(None) # Sentinel to stop writer

                # Start P1 -> Queue thread
                threading.Thread(target=writer_thread_func, daemon=True).start()

                # Main thread reads from Queue and writes to P2
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
                    
                if INTERRUPTED:
                    p1.terminate(); p2.terminate(); return False
                    
        except Exception as e:
            log(f"❌ Pipeline Error: {e}")
        finally:
            p1.terminate()
            p2.terminate()
            if os.path.exists("optional_audio.mp3"): os.remove("optional_audio.mp3")
            
        return True

def move_link(game, url, src_file, ok):
    if src_file == "manual_url": return True
    if not ok: return False
    dst = os.path.join(STREAMED_DIR, f"{game}_streamed.txt")
    try:
        with open(src_file, 'r', encoding='utf-8', errors='ignore') as f: lines = f.readlines()
        new, moved = [], None
        for line in lines:
            if moved is None and url in line: moved = line
            else: new.append(line)
        with open(src_file, 'w', encoding='utf-8') as f: f.writelines(new)
        with open(dst, 'a', encoding='utf-8') as f: f.write(f"\n# [SUCCESS] {now_ist_ampm()} | source=auto\n{moved}")
        return True
    except Exception: return False

def main():
    log("=" * 62)
    log("🎮 MASTER AGENT v33.0 — RTMP SAFE BUFFER (FIXED CRASH)")
    log(f"   Loop Setup : {LOOP_MSG}")
    log(f"   Ratio      : {RATIO} | Filter: {FILTER} | Bitrate: {BITRATE}M")
    log(f"   FPS Lock   : {TARGET_FPS} FPS")
    log("=" * 62)

    if MANUAL_VIDEO_URL:
        log(f"🎯 Using MANUAL Video URL")
        game = "Manual_Game"
        url = MANUAL_VIDEO_URL
        src_file = "manual_url"
    else:
        log("🤖 No Manual URL. Running Auto-Rotation Brain...")
        result = run_brain()
        if not result: return
        game, url, src_file = result["game_name"], result["source_url"], result["source_file"]

    gap_seconds = STREAM_GAP_MIN * 60
    if gap_seconds > 0:
        log(f"⏳ Waiting for {STREAM_GAP_MIN} minutes before connecting...")
        for i in range(gap_seconds, 0, -10):
            if INTERRUPTED: return
            if i % 60 == 0:
                log(f"   ⏱️ Time remaining: {i // 60} minutes...")
            time.sleep(10)

    log(f"\n📡 Initializing Stream...")
    ok = stream_direct(url, game)
    
    move_link(game, url, src_file, ok)
    
    log("\n" + "=" * 62)
    log(f"{'✅ Complete' if ok else '❌ Failed'}")
    log("=" * 62)

if __name__ == "__main__":
    main()