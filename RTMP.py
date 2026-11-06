#!/usr/bin/env python3
"""
🎮 MASTER AGENT v37.5 — SELF-ADAPTING + PERFECT CACHE LOOP FIX
======================================================================
✅ Fixed: Wait for cache file to finish writing before looping.
✅ Fixed: Properly close p2 before starting Phase 3.
✅ Original v37.2 ByteBuffer and Logs intact.
"""
import os
import sys
import re
import time
import signal
import subprocess
import threading
import shutil
import tempfile
from collections import deque
from datetime import datetime, timedelta, timezone

# ═══════════════════════════════════════════════════════════
# LOGGING & UTILS
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

try:
    from zoneinfo import ZoneInfo
    IST = ZoneInfo("Asia/Kolkata")
except Exception:
    IST = timezone(timedelta(hours=5, minutes=30))

# ═══════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════
STREAM_MODE   = os.getenv("STREAM_MODE", "both").lower().strip()
MANUAL_FB_KEY = os.getenv("MANUAL_FB_KEY", "").strip()
MANUAL_YT_KEY = os.getenv("MANUAL_YT_KEY", "").strip()
SECRET_FB_KEY = (os.getenv("FACEBOOK_STREAM_KEY") or "").strip()
SECRET_YT_KEY = (os.getenv("YOUTUBE_STREAM_KEY") or "").strip()

FACEBOOK_KEY = MANUAL_FB_KEY if MANUAL_FB_KEY else SECRET_FB_KEY
YOUTUBE_KEY  = MANUAL_YT_KEY if MANUAL_YT_KEY else SECRET_YT_KEY

USE_YT = STREAM_MODE in ("yt", "both") and bool(YOUTUBE_KEY)
USE_FB = STREAM_MODE in ("fb", "both") and bool(FACEBOOK_KEY)

MANUAL_VIDEO_URL = os.getenv("MANUAL_VIDEO_URL", "").strip()
AUDIO_URL      = os.getenv("AUDIO_URL", "").strip()
RATIO          = os.getenv("RATIO", "3")
FILTER         = os.getenv("FILTER", "2")
FPS_OPT        = os.getenv("FPS", "1")
BITRATE_REQ    = int(os.getenv("BITRATE", "8"))
STREAM_GAP_MIN = int(os.getenv("STREAM_GAP_MIN", "2"))
META_ARTIST    = os.getenv("META_ARTIST", "PremxGamer")

TARGET_FPS = "30" if FPS_OPT == "1" else "60"

LOOP_INPUT = os.getenv("LOOP_COUNT", "0").strip().lower()
LOOP_ARG = ""
LOOP_MSG = "Once (No Loop)"
PLAYS = 1            # 0 = infinite
if LOOP_INPUT in ("24", "24h", "24h/24", "-1", "infinite", "inf"):
    LOOP_ARG = "-stream_loop -1 "
    LOOP_MSG = "Infinite (24 Hours)"
    PLAYS = 0
else:
    try:
        plays = int(LOOP_INPUT)
        if plays > 1:
            LOOP_ARG = f"-stream_loop {plays - 1} "
            LOOP_MSG = f"{plays} Times"
            PLAYS = plays
    except ValueError:
        pass

SAFETY_FACTOR = 0.8
MIN_BUFFER_SECS = 30
CACHE_FILE = os.path.join(tempfile.gettempdir(), "encoded_cache.ts")

def _tee():
    o = []
    if USE_YT: o.append(f"[f=flv]rtmp://a.rtmp.youtube.com/live2/{YOUTUBE_KEY}")
    if USE_FB: o.append(f"[f=flv]rtmps://live-api-s.facebook.com:443/rtmp/{FACEBOOK_KEY}")
    return "|".join(o)

# ═══════════════════════════════════════════════════════════
# FILTERS
# ═══════════════════════════════════════════════════════════
def crop_chain():
    return {
        "1": "scale=1080:1080:force_original_aspect_ratio=increase,crop=1080:1080,",
        "2": "scale=1080:1350:force_original_aspect_ratio=increase,crop=1080:1350,",
        "3": "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,",
        "4": "scale=1080:1440:force_original_aspect_ratio=increase,crop=1080:1440,",
        "5": "scale=1440:1080:force_original_aspect_ratio=increase,crop=1440:1080,",
    }.get(RATIO, "")

GAME_FILTERS = {
    "0": "",
    "1": "eq=brightness=0.02:contrast=1.18:saturation=1.25,hqdn3d=1.5:1.5:6:6,unsharp=3:3:0.75:3:3:0.0,",
    "2": "eq=brightness=0.02:contrast=1.20:saturation=1.22:gamma=1.11,vibrance=intensity=0.20,hqdn3d=1.5:1.5:6:6,cas=0.3,noise=alls=3:allf=t+u,unsharp=3:3:0.75:3:3:0.0,",
    "3": "eq=brightness=0.02:contrast=1.10:saturation=1.10:gamma=1.10,vibrance=intensity=0.10,hqdn3d=1.0:1.0:3:3,cas=0.15,noise=alls=2:allf=t+u,unsharp=3:3:0.2:3:3:0.0,",
    "4": "eq=brightness=0.15:contrast=1.20:gamma=1.25,unsharp=5:5:1.0:5:5:0.0,",
    "5": "eq=contrast=1.25:saturation=1.20,colorbalance=rs=0.08:gs=0.02:bs=-0.08,unsharp=5:5:1.2:5:5:0.0,",
    "6": "eq=contrast=1.35:saturation=1.55:gamma=1.05,unsharp=7:7:2.5:7:7:0.0,",
}

def build_vf(filter_id):
    game = GAME_FILTERS.get(filter_id, "")
    return f"{crop_chain()}{game}fps={TARGET_FPS}:round=near,scale=trunc(iw/2)*2:trunc(ih/2)*2"

def enc_flags(bitrate):
    b = f"{bitrate}M"
    buf = f"{bitrate * 2}M"
    return (
        f"-c:v libx264 -preset ultrafast -threads 0 -profile:v high -level:v 4.2 "
        f"-pix_fmt yuv420p -b:v {b} -maxrate {b} -bufsize {buf} "
        f"-r {TARGET_FPS} -fps_mode cfr "
        f"-g {TARGET_FPS} -keyint_min {TARGET_FPS} -sc_threshold 0 "
        f"-c:a aac -b:a 128k -ar 44100 -ac 2 "
        f"-max_muxing_queue_size 16384 "
    )

# ═══════════════════════════════════════════════════════════
# SMART TESTS
# ═══════════════════════════════════════════════════════════
def get_video_duration(url):
    log("⏱️ Probing source video duration...")
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
           "-of", "default=noprint_wrappers=1:nokey=1", url]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if r.stdout.strip():
            dur = float(r.stdout.strip())
            log(f"   📏 Source Duration: {int(dur // 60)}m {int(dur % 60)}s ({int(dur)} seconds)")
            return dur
    except Exception:
        pass
    log("   ⚠️ Duration unknown.")
    return 0

def get_network_speeds():
    log("🌐 Checking Network Download & Upload Speed...")
    try:
        import speedtest
        st = speedtest.Speedtest()
        st.get_best_server()
        d = st.download() / 1_000_000
        u = st.upload() / 1_000_000
        log(f"   ⬇️ Download Speed: {d:.2f} Mbps")
        log(f"   ⬆️ Upload Speed: {u:.2f} Mbps")
        return d, u
    except Exception as e:
        log(f"   ⚠️ Speedtest error: {e}. Network check skipped.")
        return 0, 0

def measure_cpu_speed(url, vf_chain, flags, secs=12):
    cmd = (f'ffmpeg -hide_banner -loglevel error -t {secs} -thread_queue_size 8192 '
           f'-i "{url}" -filter_complex "[0:v]{vf_chain}[vid]" -map "[vid]" '
           f'{flags} -an -f null - -progress pipe:1 -nostats')
    speeds = []
    try:
        p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, text=True)
        start = time.time()
        for line in p.stdout:
            if time.time() - start > secs + 20:
                p.kill()
                break
            m = re.match(r"speed=\s*([\d\.]+)x", line.strip())
            if m:
                speeds.append(float(m.group(1)))
        p.wait()
    except Exception:
        pass
    if not speeds:
        return 0.0
    tail = speeds[max(1, len(speeds) // 3):] or speeds
    return sum(tail) / len(tail)

# ═══════════════════════════════════════════════════════════
# BYTE BUFFER (Disk-backed)
# ═══════════════════════════════════════════════════════════
class ByteBuffer:
    SEG = 8 * 1024 * 1024

    def __init__(self, cap_bytes, directory):
        self.dir = directory
        os.makedirs(self.dir, exist_ok=True)
        self.segs = deque()
        self.pending = bytearray()
        self.size = 0
        self.cap = cap_bytes
        self.n = 0
        self.cv = threading.Condition()
        self.done = False

    def _flush_pending(self):
        path = os.path.join(self.dir, f"seg_{self.n:08d}.bin")
        self.n += 1
        with open(path, "wb") as f:
            f.write(self.pending)
        self.segs.append((path, len(self.pending)))
        self.pending = bytearray()

    def put(self, b):
        with self.cv:
            while self.size >= self.cap and not INTERRUPTED:
                self.cv.wait(1)
            self.pending.extend(b)
            self.size += len(b)
            if len(self.pending) >= self.SEG:
                self._flush_pending()
            self.cv.notify_all()

    def get(self, timeout=1):
        with self.cv:
            if not self.segs and not self.pending and not self.done:
                self.cv.wait(timeout)
            if self.segs:
                path, ln = self.segs.popleft()
                with open(path, "rb") as f:
                    data = f.read()
                try: os.remove(path)
                except Exception: pass
                self.size -= len(data)
                self.cv.notify_all()
                return data
            if self.pending:
                data = bytes(self.pending)
                self.pending = bytearray()
                self.size -= len(data)
                self.cv.notify_all()
                return data
            return None

    def finish(self):
        with self.cv:
            self.done = True
            self.cv.notify_all()

    def cleanup(self):
        shutil.rmtree(self.dir, ignore_errors=True)

# ═══════════════════════════════════════════════════════════
# STREAMING
# ═══════════════════════════════════════════════════════════
def stream_direct(url, game_name):
    n = int(USE_YT) + int(USE_FB)
    if n == 0: return False

    if os.path.exists(CACHE_FILE): os.remove(CACHE_FILE)

    src_dur = get_video_duration(url)

    _, upload = get_network_speeds()
    bitrate = BITRATE_REQ
    flags = enc_flags(bitrate)
    bytes_per_sec = bitrate * 1.1 * 1_000_000 / 8

    BUF_DIR = os.getenv("BUFFER_DIR", os.path.join(tempfile.gettempdir(), "stream_buf"))
    os.makedirs(BUF_DIR, exist_ok=True)
    ram_cap = int(shutil.disk_usage(BUF_DIR).free * 0.8)
    log(f"💾 Temp disk buffer: {BUF_DIR} | limit: {ram_cap / (1024**3):.2f} GB")
    log("🔍 Pre-Flight Test: Checking CPU...")

    chosen = FILTER
    speed = measure_cpu_speed(url, build_vf(chosen), flags)
    log(f"   🖥️ Filter {chosen} | CPU Speed: {speed:.2f}x")
    if speed <= 0: speed = 0.3
    chosen_speed = speed
    worst = speed * SAFETY_FACTOR

    if worst >= 1.0:
        chosen_buf = MIN_BUFFER_SECS
    elif src_dur > 0:
        chosen_buf = int(src_dur * (1.0 - worst)) + MIN_BUFFER_SECS
        max_possible_buf = int(src_dur - 15)
        if chosen_buf > max_possible_buf:
            chosen_buf = max_possible_buf
            log(f"   ✂️ Buffer capped at {chosen_buf}s (Source is only {int(src_dur)}s long).")
    else:
        chosen_buf = 300

    max_secs = int(ram_cap / bytes_per_sec)
    if chosen_buf > max_secs:
        log(f"   ⚠️ Poora buffer ({chosen_buf}s) disk me nahi aata. {max_secs}s tak limit.")
        chosen_buf = max_secs
    target_bytes = int(chosen_buf * bytes_per_sec)

    vf_chain = build_vf(chosen)
    log(f"✅ Your settings: Filter {chosen} | Bitrate {bitrate}M | CPU {chosen_speed:.2f}x")
    log(f"⚙️ Smart Buffer: {chosen_buf} sec ({chosen_buf / 60:.1f} min) = {target_bytes / (1024*1024):.0f} MB")

    inputs = (f'-rtbufsize 2G -thread_queue_size 16384 '
              f'-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -i "{url}" ')

    filter_complex = ""
    audio_map = ""
    video_map = ""
    audio_file_exists = False

    if AUDIO_URL:
        subprocess.run(f'yt-dlp --extract-audio --audio-format mp3 "{AUDIO_URL}" -o "optional_audio.%(ext)s"', shell=True)
        if os.path.exists("optional_audio.mp3"):
            audio_file_exists = True
            inputs += '-thread_queue_size 4096 -stream_loop -1 -i "optional_audio.mp3" '
            filter_complex = f'[0:v]{vf_chain}[vid];[1:a]aresample=48000[a_out]'
            audio_map = '-map "[a_out]" '

    if os.path.exists("logo.png"):
        inputs += '-i "logo.png" '
        logo_idx = 2 if audio_file_exists else 1
        if audio_file_exists:
            filter_complex += f';[{logo_idx}:v]scale=160:-1[logo];[vid][logo]overlay=30:H-h-20[v_out]'
        else:
            filter_complex = f'[0:v]{vf_chain}[vid];[{logo_idx}:v]scale=160:-1[logo];[vid][logo]overlay=30:H-h-20[v_out]'
        log("🏷️ Watermark applied.")
        video_map = '-map "[v_out]" '
    else:
        if not audio_file_exists:
            filter_complex = f'[0:v]{vf_chain}[vid]'
        video_map = '-map "[vid]" '

    if not audio_file_exists:
        audio_map = '-map 0:a? -af "aresample=48000" '

    shortest = "-shortest " if audio_file_exists and PLAYS != 0 else ""

    if n == 1:
        target = (f"rtmp://a.rtmp.youtube.com/live2/{YOUTUBE_KEY}" if USE_YT
                  else f"rtmps://live-api-s.facebook.com:443/rtmp/{FACEBOOK_KEY}")
        out_format = f'-f flv "{target}"'
    else:
        out_format = f'-f tee "{_tee()}"'

    cmd1 = (f'ffmpeg -hide_banner -loglevel error -stats {inputs} '
            f'-filter_complex "{filter_complex}" {video_map}{audio_map} {shortest}'
            f'{flags} -flush_packets 1 -f mpegts pipe:1')

    cmd2 = (f'ffmpeg -hide_banner -loglevel info -stats -re -f mpegts -i pipe:0 '
            f'-c copy -flvflags no_duration_filesize {out_format}')

    p1 = subprocess.Popen(cmd1, shell=True, stdout=subprocess.PIPE)
    p2 = subprocess.Popen(cmd2, shell=True, stdin=subprocess.PIPE,
                          stderr=subprocess.PIPE, universal_newlines=False)

    def read_p2_logs():
        try:
            for line_bytes in iter(p2.stderr.readline, b''):
                safe = line_bytes.decode('utf-8', errors='ignore').strip()
                if "frame=" in safe or "speed=" in safe or "error" in safe.lower():
                    log(f"      [Sending] {safe[:150]}")
        except Exception: pass
    threading.Thread(target=read_p2_logs, daemon=True).start()

    buf = ByteBuffer(cap_bytes=target_bytes + 128 * 1024 * 1024, directory=BUF_DIR)
    cache_f = open(CACHE_FILE, "wb")

    def reader():
        try:
            while not INTERRUPTED:
                c = p1.stdout.read(1024 * 1024)
                if not c: break
                buf.put(c)
                cache_f.write(c)
        except Exception: pass
        finally:
            buf.finish()
            cache_f.close()
    threading.Thread(target=reader, daemon=True).start()

    log(f"   $ Buffering Data (Target: {target_bytes / (1024*1024):.1f} MB)...")
    last_log = 0
    try:
        while buf.size < target_bytes and not buf.done and not INTERRUPTED:
            time.sleep(1)
            if time.time() - last_log >= 10:
                last_log = time.time()
                log(f"      📦 Buffering: {buf.size / target_bytes * 100:.1f}% complete...")

        if buf.size > 0 and not INTERRUPTED:
            log(f"\n✅ Buffer FULL ({buf.size / (1024*1024):.1f} MB)! Starting Stream...")
            last_status = time.time()
            starved = False
            while not INTERRUPTED:
                b = buf.get()
                if b is None:
                    if buf.done and buf.size == 0:
                        break
                    if not starved:
                        starved = True
                        log("   ⚠️ Buffer khali — CPU peeche hai, encoder ka wait...")
                    continue
                starved = False
                p2.stdin.write(b)
                p2.stdin.flush()
                if time.time() - last_status >= 30:
                    last_status = time.time()
                    log(f"   📊 Buffer left: {buf.size / bytes_per_sec:.0f}s ({buf.size / (1024*1024):.0f} MB)")

            log("✅ First Play finished. Cache saved to disk.")
    except BrokenPipeError:
        log("❌ Stream pipe toot gayi (platform ne disconnect kiya).")
    except Exception as e:
        log(f"❌ Pipeline Error: {e}")
    finally:
        try: p2.stdin.close()
        except Exception: pass
        p1.terminate()
        try: p2.wait(timeout=15)
        except Exception: p2.terminate()
        buf.cleanup()
        if os.path.exists("optional_audio.mp3"): os.remove("optional_audio.mp3")

    # ═══════════════════════════════════════════════════════════
    # PHASE 3: SMART LOOP FROM CACHE (0% CPU)
    # ═══════════════════════════════════════════════════════════
    if (PLAYS == 0 or PLAYS > 1) and os.path.exists(CACHE_FILE):
        log("\n🔄 PHASE 3: LOOPING FROM DISK CACHE (0% CPU LOAD)...")
        
        # 🔥 FIX: Wait for cache file to finish writing (size stabilizes)
        log("   ⏳ Waiting for cache file to finalize...")
        last_size = -1
        for _ in range(15):
            if INTERRUPTED: break
            curr_size = os.path.getsize(CACHE_FILE)
            if curr_size > 0 and curr_size == last_size:
                break
            last_size = curr_size
            time.sleep(1)

        loops_to_do = -1 if PLAYS == 0 else PLAYS - 1
        loop_arg = f"-stream_loop {loops_to_do} " if loops_to_do != -1 else "-stream_loop -1 "

        cmd_loop = f'ffmpeg -hide_banner -loglevel info -stats {loop_arg}-re -i "{CACHE_FILE}" -c copy -flvflags no_duration_filesize {out_format}'
        
        p3 = subprocess.Popen(cmd_loop, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, universal_newlines=True)
        while p3.poll() is None:
            if INTERRUPTED: p3.terminate(); break
            line = p3.stderr.readline()
            if line and ("frame=" in line or "speed=" in line):
                log(f"   [Loop] {line.strip()[:120]}")
        p3.wait()

    if os.path.exists(CACHE_FILE): os.remove(CACHE_FILE)
    return True

def main():
    log("=" * 62)
    log("🎮 MASTER AGENT v37.5 — PERFECT CACHE LOOP")
    log(f"   Loop Setup : {LOOP_MSG}")
    log(f"   Ratio      : {RATIO} | Filter: {FILTER} | Bitrate: {BITRATE_REQ}M")
    log(f"   FPS Lock   : {TARGET_FPS} FPS")
    log("=" * 62)

    if MANUAL_VIDEO_URL:
        log("🎯 Using MANUAL Video URL")
    else:
        log("❌ No Manual URL provided.")
        return

    gap_seconds = STREAM_GAP_MIN * 60
    if gap_seconds > 0:
        log(f"⏳ Waiting for {STREAM_GAP_MIN} minutes before connecting...")
        for i in range(gap_seconds, 0, -10):
            if INTERRUPTED: return
            if i % 60 == 0:
                log(f"   ⏱️ Time remaining: {i // 60} minutes...")
            time.sleep(10)

    log("\n📡 Initializing Stream...")
    ok = stream_direct(MANUAL_VIDEO_URL, "Manual_Game")

    log("\n" + "=" * 62)
    log(f"{'✅ Complete' if ok else '❌ Failed'}")
    log("=" * 62)

if __name__ == "__main__":
    main()