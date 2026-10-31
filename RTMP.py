#!/usr/bin/env python3
"""
🎮 MASTER AGENT v15.2 — MANUAL URL + SMART LOOP STREAMER
======================================================================
✅ Manual Video URL Input (Override Auto-Rotation)
✅ Auto Rotation Fallback (Agar URL khali ho)
✅ Buffer Auto-Adjust + Metadata (PremxGamer)
✅ Smart Loop (0=Once, 10=10 times, 24h=24 Hours)
✅ Network Buffer Fix (-max_muxing_queue_size, -rtmp_buffer)
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

# Streaming Configs
STREAM_ENABLED     = os.getenv("STREAM_ENABLED", "true").lower() == "true"
STREAM_MODE        = os.getenv("STREAM_MODE", "both").lower().strip()
if STREAM_MODE not in ("fb", "yt", "both"): STREAM_MODE = "both"

YOUTUBE_KEY  = (os.getenv("YOUTUBE_STREAM_KEY") or "").strip()
FACEBOOK_KEY = (os.getenv("FACEBOOK_STREAM_KEY") or "").strip()
USE_YT = STREAM_MODE in ("yt", "both") and bool(YOUTUBE_KEY)
USE_FB = STREAM_MODE in ("fb", "both") and bool(FACEBOOK_KEY)
STREAMING_ENABLED = STREAM_ENABLED and (USE_YT or USE_FB)

MAX_STREAM_RETRIES = int(os.getenv("MAX_STREAM_RETRIES", "3"))

# 🔥 MANUAL URL INPUT (Agar workflow me dala toh yahan aayega)
MANUAL_VIDEO_URL = os.getenv("MANUAL_VIDEO_URL", "").strip()

# Editor Configs
AUDIO_URL      = os.getenv("AUDIO_URL", "").strip()
RATIO          = os.getenv("RATIO", "3")
FILTER         = os.getenv("FILTER", "2")
SPEED_OPT      = os.getenv("SPEED", "4")  # 4 = 1.25x default
FPS_OPT        = os.getenv("FPS", "60")
BITRATE        = os.getenv("BITRATE", "18") # 12, 16, 18
STREAM_GAP_MIN = int(os.getenv("STREAM_GAP_MIN", "5"))
META_ARTIST    = os.getenv("META_ARTIST", "PremxGamer")

# 🔥 SMART LOOP LOGIC (0=Once, 10=10 times, 24/24h=24 Hours)
LOOP_INPUT = os.getenv("LOOP_COUNT", "0").strip().lower()
LOOP_ARG = ""
MAX_RUN_SECONDS = 5 * 3600 + 45 * 60 # Default GitHub safe (5h 45m)

if LOOP_INPUT in ("24", "24h", "-1", "infinite", "inf"):
    LOOP_ARG = "-stream_loop -1 "
    MAX_RUN_SECONDS = 24 * 3600 # 24 Ghante
    LOOP_MSG = "Infinite (24 Hours)"
else:
    try:
        plays = int(LOOP_INPUT)
        if plays > 1:
            LOOP_ARG = f"-stream_loop {plays - 1} " # -stream_loop 1 = 2 plays
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

# ═══════════════════════════════════════════════════════════
# BRAIN (Auto-Rotation Fallback)
# ═══════════════════════════════════════════════════════════
LOGS_DIR       = "gaming_runtime_v8"
MANUAL_DIR     = "Manual_links"
AUTO_DIR       = "game_links_livestream"
STREAMED_DIR   = "game_links_streamed"

for d in [LOGS_DIR, MANUAL_DIR, AUTO_DIR, STREAMED_DIR]:
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

# ═══════════════════════════════════════════════════════════
# DOWNLOAD LOGIC
# ═══════════════════════════════════════════════════════════
def download_video(url, out="source.mp4"):
    log(f"📥 Fetching video (Only Once): {url[:100]}")
    
    if "videodownapi.com" in url or "download" in url:
        log("🔗 Direct Downloader API link detected...")
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            with requests.get(url, headers=headers, stream=True, timeout=60) as r:
                r.raise_for_status()
                with open(out, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            if os.path.exists(out) and os.path.getsize(out) > 100_000:
                log("✅ Direct download successful!")
            else:
                raise Exception("File too small")
        except Exception as e:
            log(f"⚠️ Direct download failed: {e}. Falling back to yt-dlp...")
            url = ""

    if not os.path.exists(out) or os.path.getsize(out) < 100_000:
        cmd = f'yt-dlp --geo-bypass -f "b[ext=mp4]/best" "{url}" -o "{out}"'
        subprocess.run(cmd, shell=True)

    if not os.path.exists(out) or os.path.getsize(out) < 100_000:
        log("❌ Video download failed completely.")
        return None

    if AUDIO_URL:
        log("🎵 Fetching optional audio...")
        subprocess.run(f'yt-dlp --extract-audio --audio-format mp3 "{AUDIO_URL}" -o "optional_audio.mp3"', shell=True)
        if os.path.exists("optional_audio.mp3"):
            log("🔄 Merging custom audio...")
            subprocess.run(f'ffmpeg -y -i "{out}" -i "optional_audio.mp3" -c:v copy -c:a aac -map 0:v:0 -map 1:a:0 "temp_merged.mp4"', shell=True)
            os.replace("temp_merged.mp4", out)
            try: os.remove("optional_audio.mp3")
            except: pass

    log(f"✅ Download complete: {os.path.getsize(out)//(1024*1024)} MB")
    return out

# ═══════════════════════════════════════════════════════════
# PRE-PROCESSING
# ═══════════════════════════════════════════════════════════
def pre_process_video(input_path, output_path, game_name):
    log(f"⚙️ [Pre-Processing] Applying Filters & Processing...")

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

    FPS = "30" if FPS_OPT == "1" else "60"
    B_V = f"{BITRATE}M"
    BUF = f"{int(BITRATE)*2}M" # 🔥 Buffer Auto-adjust

    vf_chain = f"{V_SPEED}{CROP}{GAME}scale=trunc(iw/2)*2:trunc(ih/2)*2"
    af_chain = f"{A_SPEED}aresample=48000"

    META_TITLE = f"{game_name} Gameplay"
    log(f"🎬 Rendering | Filter: {FILTER} | Speed: {SPEED_OPT} | Bitrate: {B_V} | Buffer: {BUF} | Artist: {META_ARTIST}")

    cmd = (
        f'ffmpeg -y -i "{input_path}" '
        f'-vf "{vf_chain}" -af "{af_chain}" '
        f'-r {FPS} -c:v libx264 -preset slow -profile:v high -level:v 4.2 '
        f'-pix_fmt yuv420p -b:v {B_V} -bufsize {BUF} '
        f'-g 60 -keyint_min 60 -sc_threshold 0 '
        f'-c:a aac -b:a 192k -ar 48000 -ac 2 '
        f'-metadata title="{META_TITLE}" '
        f'-metadata artist="{META_ARTIST}" '
        f'-movflags +faststart "{output_path}"'
    )
    
    subprocess.run(cmd, shell=True, check=True)
    log(f"✅ Pre-processing Done: {output_path}\n")
    return output_path

# ═══════════════════════════════════════════════════════════
# STREAMING
# ═══════════════════════════════════════════════════════════
def _tee():
    o = []
    if USE_YT: o.append(f"[f=flv]rtmp://a.rtmp.youtube.com/live2/{YOUTUBE_KEY}")
    if USE_FB: o.append(f"[f=flv]rtmps://live-api-s.facebook.com:443/rtmp/{FACEBOOK_KEY}")
    return "|".join(o)

def _run_ff(cmd, to):
    log("   $ ffmpeg stream command (keys hidden)")
    try:
        p = subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, bufsize=1)
    except Exception as e: return False, str(e)

    def _reader():
        try:
            for line in iter(p.stderr.readline, ""):
                safe = line.strip()
                for k in (YOUTUBE_KEY, FACEBOOK_KEY):
                    if k and k in safe: safe = safe.replace(k, "***")
                if safe and any(x in safe.lower() for x in ["error", "failed", "connection", "rtmp", "mapping"]):
                    log(f"      [ffmpeg] {safe[:200]}")
        except Exception: pass

    threading.Thread(target=_reader, daemon=True).start()
    start = time.time()
    try:
        while p.poll() is None:
            if INTERRUPTED: p.terminate(); return False, "interrupted"
            if to and (time.time() - start) > to: p.terminate(); return True, "time_limit"
            time.sleep(0.5)
        return p.returncode == 0, "done"
    finally:
        if p.poll() is None: p.kill()

def stream_video(src, game_name):
    if not STREAMING_ENABLED: return False
    n = int(USE_YT) + int(USE_FB)
    if n == 0: return False

    META_TITLE = f"{game_name} Gameplay"

    for att in range(1, MAX_STREAM_RETRIES + 1):
        log(f"📡 Stream Attempt {att}/{MAX_STREAM_RETRIES} → Sending to FB/YT")
        
        in_args = f'{LOOP_ARG}-re -i "{src}" '
        enc_flags = (
            f"-c:v copy -c:a copy "
            f"-metadata title=\"{META_TITLE}\" -metadata artist=\"{META_ARTIST}\" "
            f"-max_muxing_queue_size 1024 "
            f"-rtmp_buffer 1000 "
        )

        if n == 1:
            target = f"rtmp://a.rtmp.youtube.com/live2/{YOUTUBE_KEY}" if USE_YT else f"rtmps://live-api-s.facebook.com:443/rtmp/{FACEBOOK_KEY}"
            cmd = f'ffmpeg -hide_banner -loglevel info {in_args} {enc_flags} -flvflags no_duration_filesize -f flv "{target}"'
        else:
            tee = _tee()
            cmd = f'ffmpeg -hide_banner -loglevel info {in_args} {enc_flags} -flvflags no_duration_filesize -f tee "{tee}"'
        
        ok, err = _run_ff(cmd, MAX_RUN_SECONDS)
        if ok: return True
        if err == "interrupted": return False
        if err == "time_limit": return True
        
        log(f"⚠️ Attempt {att} failed")
        if att < MAX_STREAM_RETRIES: time.sleep(5 * att)
    return False

# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════
def cleanup():
    for f in ["source.mp4", "processed.mp4"]:
        if os.path.exists(f):
            try: os.remove(f)
            except: pass

def move_link(game, url, src_file, ok):
    # 🔥 Agar manual link tha, to file move karne ki zaroorat nahi
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
    log("🎮 MASTER AGENT v15.2 — MANUAL URL + SMART LOOP")
    log(f"   Loop Setup : {LOOP_MSG}")
    log(f"   Metadata   : Artist='{META_ARTIST}'")
    log(f"   Ratio      : {RATIO} | Filter: {FILTER} | Speed: {SPEED_OPT} | Bitrate: {BITRATE}M")
    log("=" * 62)

    # 🔥 Check Manual URL First
    if MANUAL_VIDEO_URL:
        log(f"🎯 Using MANUAL Video URL: {MANUAL_VIDEO_URL[:100]}")
        game = "Manual_Game"
        url = MANUAL_VIDEO_URL
        src_file = "manual_url"
    else:
        log("🤖 No Manual URL. Running Auto-Rotation Brain...")
        result = run_brain()
        if not result: 
            log("❌ No link found. Exiting.")
            return
        game, url, src_file = result["game_name"], result["source_url"], result["source_file"]

    # 1. Download (Only Once)
    local = download_video(url, "source.mp4")
    if not local: return

    # 2. Pre-Processing
    final_video = "processed.mp4"
    try:
        pre_process_video(local, final_video, game)
    except Exception as e:
        log(f"❌ Pre-processing failed: {e}")
        return

    # 3. 🔥 GAP (Wait for 5 mins)
    gap_seconds = STREAM_GAP_MIN * 60
    if gap_seconds > 0:
        log(f"⏳ Waiting for {STREAM_GAP_MIN} minutes before streaming...")
        for i in range(gap_seconds, 0, -60):
            if INTERRUPTED: return
            log(f"   ⏱️ Time remaining: {i // 60} minutes...")
            time.sleep(60)

    # 4. Stream
    log(f"\n📡 Stream starting now...")
    ok = stream_video(final_video, game)
    
    # 5. Cleanup
    move_link(game, url, src_file, ok)
    cleanup()
    
    log("\n" + "=" * 62)
    log(f"{'✅ Complete' if ok else '❌ Failed'}")
    log("=" * 62)

if __name__ == "__main__":
    main()