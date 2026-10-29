#!/usr/bin/env python3
"""
🎮 MASTER AGENT v8.4 — SINGLE FILE (Title works even if Commentary OFF)
==============================================================
"""
import os
import sys
import json
import re
import time
import signal
import functools
import subprocess
import requests
import glob
import argparse
import base64
import threading
from datetime import datetime, timedelta, timezone
from PIL import Image, ImageDraw, ImageFont, ImageOps

print = functools.partial(print, flush=True)
try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

try:
    from zoneinfo import ZoneInfo
    IST = ZoneInfo("Asia/Kolkata")
except Exception:
    IST = timezone(timedelta(hours=5, minutes=30))

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


# ═══════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════
def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--video", default=None)
    p.add_argument("--out", default=None)
    p.add_argument("--voice", default=None)
    p.add_argument("--subtitles", choices=["true", "false"], default=None)
    args, _unknown = p.parse_known_args()
    return args


ARGS = parse_args()
FINAL_CLIP_PATH    = ARGS.video
FINAL_DUBBED_VIDEO = ARGS.out


# ═══════════════════════════════════════════════════════════
# UTILS
# ═══════════════════════════════════════════════════════════
def now_ist():
    return datetime.now(IST)

def now_ist_ampm():
    return datetime.now(IST).strftime("%Y-%m-%d %I:%M:%S %p")

def log(msg, end="\n"):
    sys.stderr.write(f"{msg}{end}")
    sys.stderr.flush()

INTERRUPTED = False

def _sigint_handler(signum, frame):
    global INTERRUPTED
    INTERRUPTED = True
    log("\n⚠️ Signal — stopping...")

signal.signal(signal.SIGINT,  _sigint_handler)
signal.signal(signal.SIGTERM, _sigint_handler)


# ═══════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════
COMMENTARY_ENABLED = os.getenv("COMMENTARY_ENABLED", "true").lower() == "true"
STREAM_ENABLED     = os.getenv("STREAM_ENABLED", "true").lower() == "true"
STREAM_MODE        = os.getenv("STREAM_MODE", "both").lower().strip()
if STREAM_MODE not in ("fb", "yt", "both"):
    STREAM_MODE = "both"

YOUTUBE_KEY  = (os.getenv("YOUTUBE_STREAM_KEY") or "").strip()
FACEBOOK_KEY = (os.getenv("FACEBOOK_STREAM_KEY") or "").strip()
USE_YT = STREAM_MODE in ("yt", "both") and bool(YOUTUBE_KEY)
USE_FB = STREAM_MODE in ("fb", "both") and bool(FACEBOOK_KEY)
STREAMING_ENABLED = STREAM_ENABLED and (USE_YT or USE_FB)

STREAM_LOOP        = os.getenv("STREAM_LOOP", "false").lower() == "true"
STREAM_LIMIT_SEC   = int(os.getenv("STREAM_LIMIT_SEC", "0"))
MAX_STREAM_RETRIES = int(os.getenv("MAX_STREAM_RETRIES", "3"))
MAX_RUN_SECONDS    = int(os.getenv("MAX_RUN_SECONDS", str(5 * 3600 + 30 * 60)))

FB_PAGE_ID      = os.getenv("PAGE_ID")
FB_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
FB_GRAPH_URL    = "https://graph.facebook.com/v24.0"

LOGS_DIR       = "gaming_runtime_v8"
MANUAL_DIR     = "Manual_links"
AUTO_DIR       = "game_links_livestream"
STREAMED_DIR   = "game_links_streamed"
DASHBOARD_PATH = "AGENT_DASHBOARD_V7.md"
ANALYSIS_DIR   = "analysis"
SEGMENTS_DIR   = "segments"
FONTS_DIR      = "fonts"
TITLE_JSON     = f"{ANALYSIS_DIR}/title.json"
SRT_PATH       = "final.srt"
ASS_PATH       = "subtitles.ass"
AUDIO_PATH     = "extracted_audio.mp3"

for d in [LOGS_DIR, f"{LOGS_DIR}/games", f"{LOGS_DIR}/leaderboard",
          MANUAL_DIR, AUTO_DIR, STREAMED_DIR, ANALYSIS_DIR,
          SEGMENTS_DIR, FONTS_DIR]:
    os.makedirs(d, exist_ok=True)

def _keys(*names):
    return [os.getenv(n) for n in names if os.getenv(n)]

OPENROUTER_KEYS = _keys(
    "OPENROUTER_API_KEY", "OPENROUTER_API_KEY_2", "OPENROUTER_API_KEY_3",
    "OPENROUTER_API_KEY_4", "OPENROUTER_API_KEY_5")
GROQ_KEYS = _keys("GROQ_API_KEY", "GROQ_API_KEY_2", "GROQ_API_KEY_3")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
VOICE_ID = ARGS.voice or os.getenv("VOICE_ID") or "91w4XjqhkWTX1Jr3O344"

MIN_SLOTS_HARD = 8
MAX_SLOTS_HARD = 80
DUCK_VOLUME    = 0.35

FRAMES_PER_SECOND  = int(os.getenv("FRAMES_PER_SECOND", "3") or "3")
FRAMES_PER_SECOND  = max(1, min(FRAMES_PER_SECOND, 3))
FRAMES_PER_GRID    = 60
GRID_COLS          = 5
GRID_ROWS          = 12
CANVAS_W           = 2160
CANVAS_H           = 3840
MAX_FRAMES_CAP     = 1800
MAX_GRIDS_SOFT     = 30
GRID_TARGET_FRAMES = 1800
GRID_BATCH_SIZES   = [30, 20, 15, 12, 10, 8, 6, 4, 2, 1]

VOICE_SPEED_MIN   = 1.00
VOICE_SPEED_MAX   = 1.17
ATEMPO_MIN        = 1.00
ATEMPO_MAX        = 1.10
ATEMPO_MAX_LAST   = 1.20
ATEMPO_MAX_ACTION = 1.15
MAX_SLOT_EXTEND   = 0.2
SPEED_ACTION      = 1.14
SPEED_DIALOG      = 1.05
SPEED_CALM        = 1.00
VOL_ACTION        = 1.9
VOL_OTHER         = 1.4

SUBTITLE_MODE = 1
if ARGS.subtitles is not None:
    SUBTITLES_ENABLED = ARGS.subtitles.lower() == "true"
else:
    SUBTITLES_ENABLED = os.getenv("SUBTITLES_ENABLED", "true").lower() == "true"

PALETTE = {
    "blue":   {"fill": (10, 170, 255), "glow": (0, 130, 255)},
    "white":  {"fill": (255, 255, 255), "glow": (255, 255, 255)},
    "red":    {"fill": (255, 0, 10),    "glow": (255, 0, 0)},
    "orange": {"fill": (255, 175, 0),   "glow": (255, 110, 0)},
}
GLOW_SIZE = 0.65
GLOW_OPACITY = 0.55
LAYERS = {
    "glow":   (0, "&H%02X&" % int(255 * (1 - GLOW_OPACITY))),
    "shadow": (1, "&H90&"),
    "text":   (2, "&H00&"),
}
IN_FADE  = 0.12
OUT_FADE = 0.35

def ass_color(rgb):
    r, g, b = rgb
    return f"&H{b:02X}{g:02X}{r:02X}&"


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════
def extract_urls(text):
    urls = re.findall(r'https?://[^\s\)\]\'"<>,;]+', text)
    cleaned, seen = [], set()
    for u in urls:
        u = u.rstrip('.,;)\']"')
        if u and u not in seen:
            seen.add(u)
            cleaned.append(u)
    return cleaned

def detect_source_type(url):
    if not url: return "unknown"
    u = url.lower()
    if u.startswith("rtsp://"): return "rtsp"
    if u.startswith(("rtmp://", "rtmps://")): return "rtmp"
    if ".m3u8" in u or ".m3u" in u: return "hls"
    if u.startswith(("http://", "https://")): return "http"
    return "file"

def is_live_source(url):
    return detect_source_type(url) in ("rtsp", "rtmp")

def sec_to_srt(s):
    h = int(s // 3600); m = int((s % 3600) // 60); sec = int(s % 60); ms = int((s - int(s)) * 1000)
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"

def sec_to_ass(s):
    cs = int(round(max(s, 0) * 100))
    h = cs // 360000; m = (cs % 360000) // 6000; sec = (cs % 6000) // 100; c = cs % 100
    return f"{h}:{m:02d}:{sec:02d}.{c:02d}"

def encode_image(p):
    with open(p, "rb") as f: return base64.b64encode(f.read()).decode('utf-8')

def get_duration(p):
    try:
        out = subprocess.check_output(f'ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{p}"', shell=True).decode().strip()
        return float(out) if out else 10.0
    except Exception: return 10.0

def has_audio_stream(p):
    try:
        out = subprocess.check_output(f'ffprobe -v error -select_streams a -show_entries stream=index -of csv=p=0 "{p}"', shell=True).decode().strip()
        return bool(out)
    except Exception: return False

def parse_srt(srt):
    entries = []
    for block in srt.strip().split("\n\n"):
        lines = block.split("\n")
        if len(lines) >= 3:
            tm = re.match(r"(\d+):(\d+):(\d+),(\d+) --> (\d+):(\d+):(\d+),(\d+)", lines[1])
            if tm:
                s = int(tm.group(1))*3600 + int(tm.group(2))*60 + int(tm.group(3)) + int(tm.group(4))/1000
                e = int(tm.group(5))*3600 + int(tm.group(6))*60 + int(tm.group(7)) + int(tm.group(8))/1000
                entries.append({"start": s, "end": e, "text": lines[2].strip()})
    return entries

def speed_for_type(t):
    if t == "action": return SPEED_ACTION
    if t == "dialog": return SPEED_DIALOG
    return SPEED_CALM


# ═══════════════════════════════════════════════════════════
# 🧹 CLEANUP
# ═══════════════════════════════════════════════════════════
def cleanup_temp_files():
    log("🧹 Cleaning temp files...")
    files = ["source.mp4", "dubbed.mp4", "extracted_audio.mp3", "final.srt", "subtitles.ass"]
    total_freed = 0
    for f in files:
        if os.path.exists(f):
            try:
                sz = os.path.getsize(f)
                os.remove(f)
                total_freed += sz
                log(f"   🗑️ {f} ({sz//(1024*1024)} MB)")
            except Exception: pass
    
    for d in [SEGMENTS_DIR, "temp_frames"]:
        if os.path.exists(d):
            for f in glob.glob(f"{d}/*"):
                try: os.remove(f)
                except Exception: pass
            try: os.rmdir(d)
            except Exception: pass
    
    if total_freed > 0: log(f"✅ Freed {total_freed//(1024*1024)} MB\n")
    else: log("✅ Nothing to clean\n")


# ═══════════════════════════════════════════════════════════
# FB API
# ═══════════════════════════════════════════════════════════
def fb_views(vid, token):
    try:
        r = requests.get(f"{FB_GRAPH_URL}/{vid}/video_insights?access_token={token}", timeout=5).json()
        for m in r.get('data', []):
            if m.get('name') == 'total_video_views': return m.get('values', [{}])[0].get('value', 0)
    except Exception: pass
    return 0


# ═══════════════════════════════════════════════════════════
# BRAIN
# ═══════════════════════════════════════════════════════════
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
                if extract_urls(fh.read()): return mf, "manual"
        except Exception: pass
    af = g2a.get(game)
    if af and os.path.exists(af):
        try:
            with open(af, 'r', encoding='utf-8', errors='ignore') as fh:
                if extract_urls(fh.read()): return af, "livestream"
        except Exception: pass
    return None, None

def load_memory():
    mf = f"{LOGS_DIR}/agent_memory.json"
    memory = {"last_played_game": "", "game_stats": {}, "rotation_log": [], "total_runs": 0}
    if os.path.exists(mf):
        try:
            with open(mf, 'r', encoding='utf-8') as f:
                d = json.load(f)
            if isinstance(d, dict): memory.update(d)
        except Exception: pass
    return memory

def save_memory(memory):
    try:
        with open(f"{LOGS_DIR}/agent_memory.json", 'w', encoding='utf-8') as f:
            json.dump(memory, f, indent=2, ensure_ascii=False)
    except Exception: pass

def save_rotation(game_list, chosen, memory):
    data = {"rotation_order": list(game_list), "current_game": chosen, "last_updated": now_ist_ampm(), "rotation_log": memory.get("rotation_log", [])[-20:]}
    if chosen in game_list:
        idx = game_list.index(chosen)
        nxt = game_list[(idx + 1) % len(game_list)]
        data["next_game"] = nxt
        data["next_game_position"] = game_list.index(nxt) + 1
    try:
        with open(f"{LOGS_DIR}/rotation_history.json", 'w', encoding='utf-8') as f: json.dump(data, f, indent=2)
    except Exception: pass

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
    if not game_list:
        log("❌ No games")
        return None
    log(f"📁 Games ({len(game_list)}): {game_list}")

    memory = load_memory()
    last = memory.get("last_played_game", "")
    chosen = game_list[(game_list.index(last) + 1) % len(game_list)] if last in game_list else game_list[0]

    original = chosen
    source_file, source_kind = None, None
    attempts = 0
    while attempts < len(game_list):
        sf, kind = get_source_file(chosen, g2m, g2a)
        if sf:
            source_file, source_kind = sf, kind
            log(f"✅ Pick: {chosen} [{kind}]")
            break
        log(f"⚠️ {chosen}: empty — rotating")
        ci = game_list.index(chosen)
        chosen = game_list[(ci + 1) % len(game_list)]
        attempts += 1

    if not source_file:
        log("❌ All empty")
        return None

    try:
        with open(source_file, 'r', encoding='utf-8', errors='ignore') as f: content = f.read()
        pipe = [u.rstrip('.,;)\']"') for u in re.findall(r'\|\s*Link:\s*(https?://[^\s\n\r\)\]\'"<>,;]+)', content)]
        all_urls = pipe if pipe else extract_urls(content)
        source_url = all_urls[0] if all_urls else ""
        total = max(len(pipe), len(extract_urls(content)))
    except Exception: source_url, total = "", 0

    if not source_url:
        log("❌ No URL")
        return None

    memory["last_played_game"] = chosen
    memory["total_runs"] = memory.get("total_runs", 0) + 1
    memory.setdefault("rotation_log", []).append({"run": memory["total_runs"], "game": chosen, "timestamp": now_ist_ampm()})
    save_memory(memory)
    save_rotation(game_list, chosen, memory)
    os.environ["GAME_NAME_FOR_TITLE"] = chosen

    return {"game_name": chosen, "source_url": source_url, "source_file": source_file, "source_kind": source_kind, "total_links": total, "game_list": game_list, "ai_title": f"🎮 {chosen} Gameplay #{chosen.replace(' ', '')}"}


# ═══════════════════════════════════════════════════════════
# DOWNLOAD
# ═══════════════════════════════════════════════════════════
def download_video(url, out="source.mp4"):
    log(f"📥 Download: {url[:110]}")
    r = subprocess.run(f'yt-dlp -f "best[ext=mp4]/best" -o "{out}" --no-warnings --no-playlist --retries 3 "{url}"', shell=True, capture_output=True, text=True)
    if r.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 50_000:
        log(f"✅ yt-dlp: {os.path.getsize(out)//1024} KB")
        return out
    try:
        with requests.get(url, stream=True, timeout=180) as resp:
            resp.raise_for_status()
            with open(out, "wb") as f:
                for c in resp.iter_content(chunk_size=1 << 15): f.write(c)
        if os.path.getsize(out) > 50_000:
            log(f"✅ HTTP: {out}")
            return out
    except Exception as e: log(f"⚠️ HTTP: {e}")
    return None


# ═══════════════════════════════════════════════════════════
# COMMENTARY PIPELINE
# ═══════════════════════════════════════════════════════════
def c_validate():
    missing = []
    if not OPENROUTER_KEYS: missing.append("OPENROUTER")
    if not GROQ_KEYS: missing.append("GROQ")
    if COMMENTARY_ENABLED and not ELEVENLABS_API_KEY: missing.append("ELEVENLABS")
    if missing:
        log(f"❌ Missing: {', '.join(missing)}")
        return False
    return True

def c_extract_audio(vid, out):
    log("🎧 [1] Extract audio...")
    subprocess.run(f'ffmpeg -y -i "{vid}" -vn -acodec libmp3lame -q:a 4 "{out}"', shell=True, check=True)
    log("✅ Audio\n")

def c_transcribe(audio):
    log(f"📝 [2] Transcribe ({len(GROQ_KEYS)} keys)...")
    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    srt = ""
    for ki, k in enumerate(GROQ_KEYS, 1):
        log(f"   🔑 Key {ki}/{len(GROQ_KEYS)}...")
        try:
            with open(audio, "rb") as f:
                files = {"file": (audio, f, "audio/mp3")}
                data = {"model": "whisper-large-v3", "response_format": "verbose_json"}
                r = requests.post(url, headers={"Authorization": f"Bearer {k}"}, files=files, data=data, timeout=120)
            if r.status_code == 200:
                for i, s in enumerate(r.json().get("segments", []), 1):
                    srt += (f"{i}\n{sec_to_srt(s.get('start',0))} --> {sec_to_srt(s.get('end',0))}\n{s.get('text','').strip()}\n\n")
                with open(SRT_PATH, "w", encoding="utf-8") as sf: sf.write(srt)
                log(f"   ✅ Key {ki} worked\n")
                return srt
            elif r.status_code in (401, 403): time.sleep(1)
            elif r.status_code == 429: time.sleep(2)
        except Exception: time.sleep(2)
    return srt

def c_scene_timeline(vid):
    cmd = f'ffmpeg -i "{vid}" -filter:v "select=\'gt(scene,0.3)\',showinfo" -f null - 2>&1'
    out = subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout
    return [float(m.group(1)) for m in re.finditer(r"pts_time:([\d.]+)", out)]

def c_loudness_timeline(vid):
    cmd = f'ffmpeg -i "{vid}" -af "astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-" -f null - 2>&1'
    out = subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout
    tl, t = [], 0.0
    for line in out.split("\n"):
        pm = re.search(r"pts_time:([\d.]+)", line)
        if pm:
            t = float(pm.group(1)); continue
        m = re.search(r"RMS_level=(-?[\d.]+|-?inf)", line)
        if m and m.group(1) not in ("-inf", "inf"):
            try: tl.append((t, float(m.group(1))))
            except Exception: pass
    return tl

def c_slot_loud(tl, s, e):
    v = [x for t, x in tl if s <= t < e]
    return max(v) if v else -60

def c_motion(vid, s, e):
    try:
        d = max(e - s, 0.5)
        cmd = f'ffmpeg -ss {s:.2f} -t {d:.2f} -i "{vid}" -vf "select=\'gt(scene,0.1)\',metadata=print" -f null - 2>&1'
        return len(re.findall(r"pts_time", subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout))
    except Exception: return 0

def c_build_slots(vid, dur, srt):
    log("📐 [3] Slots...")
    entries = parse_srt(srt)
    sb = set()
    for e in entries:
        sb.add(round(e["start"], 2))
        sb.add(round(e["end"], 2))
    sp = sum(e["end"] - e["start"] for e in entries)
    sr = sp / max(dur, 1)
    st = c_scene_timeline(vid)
    scb = set(round(t, 2) for t in st)
    lt = c_loudness_timeline(vid)
    peaks = set()
    if len(lt) > 5:
        v = [x for _, x in lt]
        th = sorted(v)[int(len(v) * 0.8)]
        for t, x in lt:
            if x >= th and x > -20: peaks.add(round(t, 2))
    log(f"   SRT:{len(sb)} Scene:{len(scb)} Peak:{len(peaks)}")

    if dur <= 20: base = 2.0
    elif dur <= 40: base = 2.5
    elif dur <= 70: base = 3.0
    elif dur <= 120: base = 3.5
    elif dur <= 180: base = 4.0
    elif dur <= 300: base = 5.0
    elif dur <= 450: base = 6.5
    elif dur <= 600: base = 8.0
    elif dur <= 800: base = 10.0
    else: base = 12.0

    if sr > 0.7: base *= 0.85
    elif sr < 0.25: base *= 1.15
    cps = len(st) / max(dur, 1)
    if cps > 0.5: base *= 0.85
    elif cps < 0.12: base *= 1.1

    total = int(round(dur / base))
    total = max(MIN_SLOTS_HARD, min(MAX_SLOTS_HARD, total))
    ss = dur / total
    log(f"   Slot:{ss:.2f}s Total:{total}")

    all_b = sorted(sb | scb | peaks)
    all_b = [b for b in all_b if 0.5 < b < dur - 0.5]
    slots, t, used = [], 0.0, set()
    for i in range(total):
        te = dur if i == total - 1 else t + ss
        cands = [b for b in all_b if b not in used and t + 1.5 < b < te + 1.0]
        if cands and i < total - 1:
            sc = [b for b in cands if b in sb]
            sc2 = [b for b in cands if b in scb]
            if sc: snap = min(sc, key=lambda x: abs(x - te))
            elif sc2: snap = min(sc2, key=lambda x: abs(x - te))
            else: snap = min(cands, key=lambda x: abs(x - te))
            end = snap if abs(snap - te) < 1.0 else te
            used.add(snap)
        else: end = te
        end = min(end, dur); end = max(end, t + 1.5)
        txt = " ".join(e["text"] for e in entries if e["start"] >= t and e["end"] <= end).strip()
        slots.append({"start": round(t, 2), "end": round(end, 2), "type": None, "srt_text": txt, "scene_count": 0, "avg_loud": -50, "sub_analysis": {}, "voice_speed": 1.0, "motion_score": 0, "speed_boost_log": []})
        t = end
        if t >= dur - 0.1: break
    if slots and slots[-1]["end"] < dur - 0.1: slots[-1]["end"] = round(dur, 2)
    for sl in slots:
        se = [e for e in entries if e["start"] >= sl["start"] - 0.15 and e["end"] <= sl["end"] + 0.15]
        sl["srt_text"] = " ".join(e["text"] for e in se)
        for e in se:
            e["start"] = sl["start"]; e["end"] = sl["end"]
    log(f"   ✅ {len(slots)} slots\n")
    return slots

def c_classify(vid, slots, srt):
    log("🔍 [4] Classify...")
    st = c_scene_timeline(vid)
    lt = c_loudness_timeline(vid)
    entries = parse_srt(srt)
    AW = {"shoot","fire","hit","run","kill","die","attack","grenade","boom","jump","dodge","cover","reload","go","move","watch","left","right","down","up","quick","destroy","target","lock","bang","drop","danger","whoa","oh","yeah","nice","sick","cook","big","fast"}
    KW = {"kill","killed","die","died","dead","hit","headshot","shot","destroyed","deleted","bodied","clapped","cooked","one tap","one shot","eliminated","frag","boom","explode","blast"}
    DW = {"you","me","we","what","why","how","hey","listen","wait","okay","yeah","know","think","feel","want","need","can","will"}

    for sl in slots:
        mo = c_motion(vid, sl["start"], sl["end"])
        sl["motion_score"] = mo
        sws, t = [], sl["start"]
        while t < sl["end"]:
            e = min(t + 0.5, sl["end"])
            sws.append({"start": t, "end": e})
            t = e
        ac = dc = cc = 0
        for sw in sws:
            scc = sum(1 for x in st if sw["start"] <= x < sw["end"])
            ld = c_slot_loud(lt, sw["start"], sw["end"])
            txt = " ".join(e["text"] for e in entries if e["start"] >= sw["start"] and e["end"] <= sw["end"]).lower()
            w = set(txt.split())
            if w & KW: ac += 1; continue
            ha = len(w & AW) >= 1; hd = len(w & DW) >= 1; hs = len(txt.strip()) > 3
            if ha and scc >= 1: ac += 1
            elif ha: ac += 1
            elif scc >= 2: ac += 1
            elif ld > -15: ac += 1
            elif hs and hd: dc += 1
            elif hs: dc += 1
            else: cc += 1
        tot = max(len(sws), 1)
        ar, dr, cr = ac/tot, dc/tot, cc/tot
        if mo >= 5: ar = min(1.0, ar + 0.40)
        elif mo >= 3: ar = min(1.0, ar + 0.25)
        elif mo >= 2: ar = min(1.0, ar + 0.15)
        if mo >= 3: cr = max(0.0, cr - 0.30)
        if ar >= 0.30 or mo >= 5: sl["type"] = "action"
        elif dr >= 0.40: sl["type"] = "dialog"
        elif cr >= 0.50 and mo < 2: sl["type"] = "calm"
        elif ar >= 0.20 or mo >= 3: sl["type"] = "action"
        elif dr >= 0.20: sl["type"] = "dialog"
        else: sl["type"] = "calm"
        sl["scene_count"] = sum(1 for x in st if sl["start"] <= x < sl["end"])
        sl["avg_loud"] = round(c_slot_loud(lt, sl["start"], sl["end"]), 1)
        sl["sub_analysis"] = {"action_ratio": round(ar,2), "dialog_ratio": round(dr,2), "calm_ratio": round(cr,2), "motion_score": mo}
        vs = speed_for_type(sl["type"])
        if sl["type"] == "action":
            if sl["scene_count"] >= 3: vs += 0.03
            if sl["avg_loud"] > -12: vs += 0.03
            if mo >= 5: vs += 0.02
        sl["voice_speed"] = round(max(VOICE_SPEED_MIN, min(VOICE_SPEED_MAX, vs)), 2)
    sp = [s["voice_speed"] for s in slots]
    if sp: log(f"✅ Speeds: min={min(sp):.2f} max={max(sp):.2f}\n")
    return slots

def c_build_grids(vid, dur, slots):
    eff = FRAMES_PER_SECOND
    need = GRID_TARGET_FRAMES / max(dur, 1)
    eff = min(FRAMES_PER_SECOND, max(0.5, need))
    tf = int(dur * eff)
    tf = max(3, min(tf, MAX_FRAMES_CAP))
    ng = max(1, (tf + FRAMES_PER_GRID - 1) // FRAMES_PER_GRID)
    if ng > MAX_GRIDS_SOFT:
        tf = MAX_GRIDS_SOFT * FRAMES_PER_GRID; ng = MAX_GRIDS_SOFT; eff = tf / max(dur, 1)
    log(f"🖼️ [5] Grid: {tf}f ({dur:.1f}s × {eff:.2f}fps) → {ng} grid(s)")

    for old in glob.glob(f"{ANALYSIS_DIR}/grid_*.jpg"):
        try: os.remove(old)
        except Exception: pass
    tmp = "temp_frames"; os.makedirs(tmp, exist_ok=True)
    for f in glob.glob(f"{tmp}/*.jpg"):
        try: os.remove(f)
        except Exception: pass

    cmd = f'ffmpeg -y -i "{vid}" -vf "fps={eff:.4f},scale=540:-1" -q:v 4 "{tmp}/frame_%05d.jpg"'
    subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    ex = sorted(glob.glob(f"{tmp}/frame_*.jpg"))
    log(f"   📸 Extracted: {len(ex)}")
    if not ex: return []

    cw, ch = CANVAS_W // GRID_COLS, CANVAS_H // GRID_ROWS
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", max(18, cw // 20))
        sf = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", max(14, cw // 28))
    except Exception: font = sf = ImageFont.load_default()

    grids = []
    for gi in range(ng):
        s, e = gi * FRAMES_PER_GRID, min((gi+1) * FRAMES_PER_GRID, len(ex))
        chunk = ex[s:e]
        if not chunk: break
        g = Image.new("RGB", (CANVAS_W, CANVAS_H), (0, 0, 0))
        dr = ImageDraw.Draw(g)
        for i, fp in enumerate(chunk):
            if i >= FRAMES_PER_GRID: break
            try:
                im = Image.open(fp); im = ImageOps.fit(im, (cw, ch), method=Image.LANCZOS)
            except Exception: continue
            m = re.search(r'frame_(\d+)', fp)
            fn = int(m.group(1)) if m else (s + i + 1)
            t = (fn - 1) / eff
            si, ss, se = 0, 0.0, dur
            for si2, sl in enumerate(slots):
                if sl["start"] <= t < sl["end"]: si, ss, se = si2, sl["start"], sl["end"]; break
            x, y = (i % GRID_COLS) * cw, (i // GRID_COLS) * ch
            g.paste(im, (x, y))
            dr.rectangle([x+4, y+4, x+min(cw-8,260)+4, y+56], fill="black")
            dr.text((x+8, y+6), f"S{si+1}: {ss:.1f}-{se:.1f}s", fill="yellow", font=font)
            dr.text((x+8, y+28), f"@{t:.2f}s", fill="cyan", font=sf)
        gp = f"{ANALYSIS_DIR}/grid_{gi+1:02d}.jpg"
        g.save(gp, quality=70, optimize=True, subsampling=2)
        sz = os.path.getsize(gp) / (1024 * 1024)
        log(f"   ✅ {gi+1}/{ng}: {len(chunk)}c ({sz:.2f}MB)")
        grids.append(gp)

    for f in glob.glob(f"{tmp}/*.jpg"):
        try: os.remove(f)
        except Exception: pass
    try: os.rmdir(tmp)
    except Exception: pass
    log(f"💾 {len(grids)} grids\n")
    return grids


def c_title_and_script(slots, srt, grids, game):
    if not grids: return f"🎮 {game} Gameplay", []
    log(f"\n🏷️🎙️ [6+7] Title + Commentary Generation ({len(grids)} grids)")

    sl_txt = []
    for i, s in enumerate(slots, 1):
        sa = s.get("sub_analysis", {})
        sl_txt.append(f"- S{i}: {s['start']:.1f}-{s['end']:.1f}s [{s['type'].upper()}] scenes={s['scene_count']} motion={sa.get('motion_score',0)} SRT:\"{s['srt_text'][:50]}\"")

    prompt = f"""You are HYPED gaming YouTuber + viral title creator.
{len(grids)} grids of actual gameplay. Read frames to verify.

**READ:**
- 60 cells/grid, yellow "SN:A-Bs" slot, cyan "@T" timestamp
- Grid order = time order
- Read game, characters, kills, HUD, story

**GAME:** {game} | **DUR:** {slots[-1]['end']:.1f}s | **SLOTS:** {len(slots)}

**SLOTS:**
{chr(10).join(sl_txt)}

**TRANSCRIPT:**
{srt[:800]}

**TITLE:** 40-65 chars, game name, max 1 emoji, match emotion, same language as transcript.

**COMMENTARY:** {len(slots)} segments, one per slot, 3-7 words, react to kills, match emotion.

**RETURN ONLY valid JSON:**
{{
  "title": "VIRAL TITLE",
  "title_reason": "what frames showed",
  "segments": [
    {{"slot": 1, "start": 0.0, "end": 3.5, "text": "COMMENTARY", "visual_type": "calm"}}
  ]
}}"""

    url = "https://openrouter.ai/api/v1/chat/completions"

    def _try(mid, key, subset):
        blocks = [{"type": "text", "text": prompt}]
        for gp in subset:
            blocks.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encode_image(gp)}", "detail": "high"}})
        payload = {"model": mid, "messages": [{"role": "user", "content": blocks}], "max_tokens": 16000, "temperature": 0.9, "response_format": {"type": "json_object"}, "plugins": [{"id": "response-healing"}]}
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "HTTP-Referer": "https://github.com/", "X-Title": "Gaming Agent"}
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=180)
            if r.status_code == 200:
                c = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                raw = str(c).strip() if c else ""
                if not raw: return None, "empty"
                if raw.startswith("```"):
                    raw = raw.split("```")[1]
                    if raw.startswith("json"): raw = raw[4:].strip()
                    raw = raw.rstrip("`").strip()
                p = json.loads(raw)
                if not isinstance(p, dict): return None, "not_dict"
                title = str(p.get("title", "")).strip().strip('"').strip("'")
                segs = p.get("segments", [])
                if not title or len(title) < 5: return None, "no_title"
                if not isinstance(segs, list) or len(segs) < int(len(slots) * 0.90):
                    return None, f"segs({len(segs) if isinstance(segs, list) else 0})"
                segs = [s for s in segs if isinstance(s, dict)]
                return {"title": title[:120], "reason": p.get("title_reason", ""), "segments": segs}, None
            elif r.status_code == 404: return None, "Not Found (404)"
            elif r.status_code in (401, 402, 403): return None, "Auth/Quota"
            elif r.status_code == 429: return None, "Rate Limit (429)"
            elif r.status_code == 400: return None, "Too Many Images (400)"
            else: return None, f"HTTP {r.status_code}"
        except Exception as e: return None, f"Exc: {str(e)[:40]}"

    models = ["nvidia/nemotron-3.5-super-vl:free", "google/gemini-2.0-flash-exp:free", "openrouter/free"]
    keys = [k for k in OPENROUTER_KEYS if k]

    for bs in GRID_BATCH_SIZES:
        sub = grids if len(grids) <= bs else [grids[int(i*len(grids)/bs)] for i in range(bs)]
        log(f"\n   📦 Trying Batch Size: {len(sub)} images")
        for model in models:
            for ki, key in enumerate(keys, 1):
                log(f"      🤖 {model.split('/')[1][:15]}... | Key {ki}/{len(keys)}", end=" ")
                res, err = _try(model, key, sub)
                if res:
                    log("✅ SUCCESS!")
                    log(f"      🏆 WINNING MODEL: {model}")
                    log(f"      🏷️ Generated Title: {res['title']}")
                    log(f"      💡 AI Reason: {res['reason']}")
                    log(f"      📜 Segments Generated: {len(res['segments'])}")
                    return res["title"], res["segments"]
                elif err in ("Not Found (404)", "Too Many Images (400)"):
                    log(f"❌ {err} → Skipping rest of keys")
                    break
                else: log(f"⚠️ {err}")
    log("\n❌ All models & keys failed to generate Title/Script")
    return f"🎮 {game} Gameplay", []


def c_tts(segments, slots, dur):
    log("🔊 [8] TTS...")
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"
    headers = {"Accept": "audio/mpeg", "Content-Type": "application/json", "xi-api-key": ELEVENLABS_API_KEY}
    audio = []
    for idx, seg in enumerate(segments):
        raw = seg.get("text")
        text = str(raw).strip() if raw else ""
        if not text or text.lower() == "none": continue
        tts = re.sub(r'[^\w\s\.,!\?\'\-\"\*]', '', text) if SUBTITLE_MODE == 2 else text
        sn = seg.get("slot")
        ms = None
        if sn and 1 <= sn <= len(slots): ms = slots[sn - 1]
        else:
            bb = 999
            for s in slots:
                d = abs(s["start"] - seg.get("start", 0))
                if d < bb: bb, ms = d, s
        if not ms: continue
        ss, se = ms["start"], ms["end"]
        tgt = se - ss
        vs = max(VOICE_SPEED_MIN, min(VOICE_SPEED_MAX, ms.get("voice_speed", 1.0)))
        vt = (ms.get("type") or "calm").lower().strip()
        sf = f"{SEGMENTS_DIR}/seg_{idx:03d}.mp3"
        data = {"text": tts, "model_id": "eleven_multilingual_v2", "voice_settings": {"stability": 0.4, "similarity_boost": 0.75, "style": 0.5, "use_speaker_boost": True, "speed": vs}}
        try:
            r = requests.post(url, json=data, headers=headers, timeout=60)
            for _retry in range(3):
                if r.status_code != 429: break
                time.sleep(3 * (_retry + 1))
                r = requests.post(url, json=data, headers=headers, timeout=60)
            if r.status_code == 200:
                with open(sf, "wb") as af: af.write(r.content)
                actual = get_duration(sf)
                ext = 0.0
                is_last = (idx == len(segments) - 1)
                am = ATEMPO_MAX_LAST if is_last else ATEMPO_MAX
                if vt == "action" and not is_last and actual > tgt + 0.05:
                    tempo = max(ATEMPO_MIN, min(ATEMPO_MAX_ACTION, actual/tgt))
                    if tempo > 1.01:
                        ff = f"{SEGMENTS_DIR}/seg_{idx:03d}_fit.mp3"
                        subprocess.run(f'ffmpeg -y -i "{sf}" -filter:a atempo={tempo:.3f} "{ff}"', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        final = ff if os.path.exists(ff) else sf
                    else: final = sf
                    fd = get_duration(final)
                    if fd > tgt + 0.2: ext = min(fd - tgt, MAX_SLOT_EXTEND)
                elif actual > 0 and tgt > 0:
                    tempo = max(ATEMPO_MIN, min(am, actual/tgt))
                    if tempo > 1.01:
                        ff = f"{SEGMENTS_DIR}/seg_{idx:03d}_fit.mp3"
                        subprocess.run(f'ffmpeg -y -i "{sf}" -filter:a atempo={tempo:.3f} "{ff}"', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        final = ff if os.path.exists(ff) else sf
                    else: final = sf
                else: final = sf
                audio.append({"file": final, "start": ss, "end": se + ext, "actual_end": ss + get_duration(final), "actual_dur": actual, "text": text, "visual_type": vt})
                fd = get_duration(final)
                log(f"   ✅ S{sn} [{vt.upper()}] {actual:.2f}→{fd:.2f}s | {text[:35]}")
            elif r.status_code == 401:
                log("   ❌ EL auth"); break
            else: log(f"   ⚠️ S{sn}: HTTP {r.status_code}")
        except Exception as e: log(f"   ⚠️ {idx}: {e}")
    log(f"\n✅ {len(audio)} audio segments\n")
    return audio

def c_ass(audio_files, font_name="BebasNeue-Regular", font_size=40, alignment=2, vertical_margin=65):
    log("🎨 [9] ASS...")
    a = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
ScaledBorderAndShadow: yes
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,{alignment},100,100,{vertical_margin},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    w, W, H = 0, 1920, 1080
    for it in audio_files:
        s, e = it.get("start", 0), it.get("actual_end", it.get("end", 3))
        raw = it.get("text")
        txt = str(raw).strip().upper() if raw else ""
        if not txt or txt.lower() == "none": continue
        if len(txt) > 26:
            words = txt.split(); lines, cl = [], []
            for w2 in words:
                cl.append(w2)
                if len(" ".join(cl)) > 26: lines.append(" ".join(cl)); cl = []
            if cl: lines.append(" ".join(cl))
            txt = "\\N".join(lines)
        vt = (it.get("visual_type") or "calm").lower()
        td = max(e - s, 1.0)
        cn = len(txt.replace(" ", "").replace("\\N", ""))
        if cn == 0: continue
        ins = min(td/cn, 0.06); outs = 0.03
        words = txt.split()
        ev0 = s - 0.05
        ev1 = e + (cn - 1) * outs + OUT_FADE + 0.05
        dur = int((ev1 - ev0) * 1000)
        rel = lambda t: max(0, int((t - ev0) * 1000))
        cx = W * 0.50; nl = txt.count("\\N") + 1
        cy = H - vertical_margin - (font_size * 0.5 * nl)
        def pos(dx=0.0, dy=0.0):
            if vt == "action": return f"\\move({cx+dx:.1f},{cy+20+dy:.1f},{cx+dx:.1f},{cy-20+dy:.1f},0,{dur})"
            return f"\\pos({cx+dx:.1f},{cy+dy:.1f})"
        _w = []
        for x in words: _w.extend(x.replace("\\N", " \\N ").split())
        _t = len(_w)
        for k, (layer, vis) in LAYERS.items():
            if k == "shadow": look, dx, dy = "\\bord0\\shad2.5\\blur0.8", 2.0, 3.0
            elif k == "glow": look, dx, dy = f"\\bord{font_size*0.12*GLOW_SIZE:.1f}\\shad0\\blur{font_size*0.28*GLOW_SIZE:.1f}", 0.0, 0.0
            else: look, dx, dy = f"\\bord{font_size*0.08:.1f}\\shad2.5\\blur0", 0.0, 0.0
            pf = f"{{\\an5{pos(dx,dy)}\\fs{font_size}\\fsp8\\b1{look}}}"
            bd, ci = "", 0
            for wi, wd in enumerate(_w):
                if wd == "\\N": bd += "\\N"; continue
                wp = PALETTE["red"] if (wi == _t-1 and vt=="action") else (PALETTE["orange"] if wi==_t-1 else PALETTE["blue"])
                wc = ass_color(wp["glow" if k=="glow" else "fill"])
                col_tag = ("\\1c" + wc + "\\3c" + wc) if k == "glow" else ("\\1c" + wc)
                bd += "{" + col_tag + "}"
                for ch in wd:
                    if ch in "{}\\": continue
                    ti = s + ci*ins; to = e + ci*outs
                    bd += "{\\alpha&HFF&}"
                    bd += f"{{\\t({rel(ti)},{rel(ti+IN_FADE)},\\alpha{vis})}}"
                    bd += f"{{\\t({rel(to)},{rel(to+OUT_FADE)},\\alpha&HFF&)}}"
                    bd += ch; ci += 1
                if wi < _t-1 and _w[wi+1] != "\\N": bd += " "
            a += f"Dialogue: {layer},{sec_to_ass(ev0)},{sec_to_ass(ev1)},Default,,0,0,0,,{pf}{bd}\n"
            w += 1
    with open(ASS_PATH, "w", encoding="utf-8") as f: f.write(a)
    log(f"✅ ASS: {w} layers\n")

def c_timed(audio, dur):
    log("🎼 [10] Timed audio...")
    sil = f"{SEGMENTS_DIR}/silent.mp3"
    subprocess.run(f'ffmpeg -y -f lavfi -i anullsrc=r=44100:cl=stereo -t {dur} -q:a 9 -acodec libmp3lame "{sil}"', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    inp, parts, mix = ["-i", f'"{sil}"'], [], ["[0:a]"]
    for i, a in enumerate(audio, 1):
        inp.extend(["-i", f'"{a["file"]}"'])
        d = int(a["start"] * 1000)
        parts.append(f"[{i}:a]adelay={d}|{d}[a{i}]")
        mix.append(f"[a{i}]")
    fc = (";".join(parts) + f";{''.join(mix)}amix=inputs={len(mix)}:duration=first:dropout_transition=0:normalize=0,alimiter=limit=0.95[out]")
    fa = f"{SEGMENTS_DIR}/final.mp3"
    subprocess.run(f"ffmpeg -y {' '.join(inp)} -filter_complex \"{fc}\" -map \"[out]\" -acodec libmp3lame -q:a 4 \"{fa}\"", shell=True, check=True)
    log("✅ Timed audio\n")
    return fa

def c_merge(vid, caudio, out, audio, subs=True):
    log("🎬 [11] Merge...")
    at, ot = [], []
    for a in audio:
        vt = (a.get("visual_type") or "").lower()
        if vt == "action": at.append(f"between(t,{a['start']:.2f},{a['end']:.2f})")
        else: ot.append(f"between(t,{a['start']:.2f},{a['end']:.2f})")
    allt = at + ot
    ac = "+".join(allt) if allt else "0"
    ve = f"if({ac},{DUCK_VOLUME},1.0)"
    vv = f"if({'+'.join(at)},{VOL_ACTION},{VOL_OTHER})" if at else f"{VOL_OTHER}"
    if has_audio_stream(vid):
        fc = f"[0:a]volume='{ve}':eval=frame[bg];[1:a]volume='{vv}':eval=frame[vo];[bg][vo]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,alimiter=limit=0.95[aout]"
    else:
        log("   ℹ️ Source has no audio — voiceover only")
        fc = f"[1:a]volume='{vv}':eval=frame,alimiter=limit=0.95[aout]"
    sa = subs and os.path.exists(ASS_PATH)
    vf = f'-vf "subtitles={ASS_PATH}:fontsdir={FONTS_DIR}"' if sa else ""
    vc = "-c:v libx264 -preset fast -crf 23 -pix_fmt yuv420p" if sa else "-c:v copy"
    subprocess.run(f'ffmpeg -y -i "{vid}" -i "{caudio}" -filter_complex "{fc}" {vf} -map 0:v:0 -map "[aout]" {vc} -c:a aac -b:a 192k -shortest "{out}"', shell=True, check=True)
    log(f"🔥 Final: {out}\n")

def run_commentary_pipeline(video_in, video_out):
    global FINAL_CLIP_PATH, FINAL_DUBBED_VIDEO
    FINAL_CLIP_PATH = video_in
    FINAL_DUBBED_VIDEO = video_out
    if not c_validate(): return video_in
    
    dur = get_duration(video_in)
    log(f"📹 Duration: {dur:.2f}s\n")
    
    try:
        c_extract_audio(video_in, AUDIO_PATH)
        srt = c_transcribe(AUDIO_PATH)
        slots = c_build_slots(video_in, dur, srt)
        slots = c_classify(video_in, slots, srt)
        grids = c_build_grids(video_in, dur, slots)
        
        if not grids: 
            log("❌ No grids")
            return video_in
        
        game = os.getenv("GAME_NAME_FOR_TITLE", "Gameplay")
        title, segs = c_title_and_script(slots, srt, grids, game)
        
        if not segs: 
            log("❌ No segments")
            return video_in

        with open(TITLE_JSON, "w", encoding="utf-8") as f:
            json.dump({"title": title, "game": game, "generated_at": datetime.now().isoformat()}, f, indent=2, ensure_ascii=False)
        log(f"💾 Title: {title}\n")

        # 🔥 IF COMMENTARY OFF: STOP HERE, just generate title, skip TTS & Merge
        if not COMMENTARY_ENABLED:
            log("⏭ Commentary OFF — Skipping voice/subtitles. Using original video.")
            return video_in

        if len(segs) < len(slots):
            filled = {s.get("slot") for s in segs if s.get("slot")}
            for si in range(1, len(slots)+1):
                if si not in filled:
                    segs.append({"slot": si, "start": slots[si-1]["start"], "end": slots[si-1]["end"], "text": "", "visual_type": slots[si-1].get("type", "calm")})
            segs.sort(key=lambda x: x.get("slot", 0))

        for s in segs:
            if s.get("text") is None or str(s.get("text")).strip().lower() == "none": s["text"] = ""
            else: s["text"] = str(s["text"]).strip()
            if not s.get("visual_type"): s["visual_type"] = "calm"

        for s in segs:
            sn = s.get("slot")
            if sn and 1 <= sn <= len(slots): s["start"], s["end"] = slots[sn-1]["start"], slots[sn-1]["end"]

        audio = c_tts(segs, slots, dur)
        if not audio: return video_in
        if SUBTITLES_ENABLED: c_ass(audio, font_name="BebasNeue-Regular", font_size=40, alignment=2, vertical_margin=65)
        
        fa = c_timed(audio, dur)
        c_merge(video_in, fa, video_out, audio, subs=SUBTITLES_ENABLED)
        return video_out if os.path.exists(video_out) else video_in
        
    except Exception as e:
        log(f"\n❌ Pipeline error: {e}")
        return video_in


def read_title(fallback):
    try:
        if os.path.exists(TITLE_JSON):
            with open(TITLE_JSON, 'r', encoding='utf-8') as f:
                t = str(json.load(f).get("title", "")).strip()
            if 5 < len(t) < 120: return t
    except Exception: pass
    return fallback


# ═══════════════════════════════════════════════════════════
# RTMP
# ═══════════════════════════════════════════════════════════
def _tee():
    o = []
    if USE_YT: o.append(f"[f=flv]rtmp://a.rtmp.youtube.com/live2/{YOUTUBE_KEY}")
    if USE_FB: o.append(f"[f=flv]rtmps://live-api-s.facebook.com:443/rtmp/{FACEBOOK_KEY}")
    return "|".join(o)

def _in_flags(st):
    if st == "rtsp": return "-rtsp_transport tcp -fflags nobuffer -flags low_delay -analyzeduration 1000000 -probesize 1000000 "
    if st in ("rtmp", "rtmps"): return "-fflags nobuffer -analyzeduration 2000000 -probesize 2000000 "
    if st == "hls": return "-live_start_index -3 -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 "
    return ""

def _enc(low=False):
    t = "-tune zerolatency " if low else ""
    return f"-c:v libx264 -preset veryfast {t}-b:v 3000k -maxrate 3000k -bufsize 6000k -r 30 -pix_fmt yuv420p -g 60 -keyint_min 60 -sc_threshold 0 -c:a aac -b:a 160k -ar 44100 -ac 2 "

def _run_ff(cmd, to):
    log("   $ ffmpeg stream command (keys hidden)")
    try:
        p = subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, bufsize=1)
    except Exception as e:
        return False, str(e)

    err_lines = []
    def _reader():
        try:
            for line in iter(p.stderr.readline, ""):
                safe = line.strip()
                for k in (YOUTUBE_KEY, FACEBOOK_KEY):
                    if k and k in safe: safe = safe.replace(k, "***")
                if safe and any(x in safe.lower() for x in ["error", "failed", "connection", "rtmp", "invalid", "denied", "cannot", "unable", "opening", "stream", "muxing"]):
                    log(f"      [ffmpeg] {safe[:200]}")
                err_lines.append(safe)
                if len(err_lines) > 30: err_lines.pop(0)
        except Exception: pass

    t = threading.Thread(target=_reader, daemon=True)
    t.start()

    start = time.time()
    try:
        while p.poll() is None:
            if INTERRUPTED:
                p.terminate()
                try: p.wait(timeout=10)
                except subprocess.TimeoutExpired: p.kill()
                return False, "interrupted"
            if to and (time.time() - start) > to:
                p.terminate()
                try: p.wait(timeout=10)
                except subprocess.TimeoutExpired: p.kill()
                return True, "time_limit"
            time.sleep(0.5)
        return p.returncode == 0, "\n".join(err_lines[-5:]) or "done"
    finally:
        if p.poll() is None: p.kill()

def stream_rtmp(src, live):
    if not STREAMING_ENABLED:
        log(f"🚫 Stream off [{STREAM_MODE}]"); return False
    n = int(USE_YT) + int(USE_FB)
    if n == 0: log("❌ No targets"); return False
    
    st = detect_source_type(src)
    inf = _in_flags(st)
    ef = _enc(low=live)
    
    has_audio = has_audio_stream(src)
    if not has_audio: log("   🔊 Source me audio nahi — silent audio inject karunga")
    
    for att in range(1, MAX_STREAM_RETRIES + 1):
        log(f"📡 {att}/{MAX_STREAM_RETRIES} → {'LIVE' if live else 'VOD'} [{st}] ({n} target)")
        re_flag = "" if live else "-re "
        loop = "-stream_loop -1 " if (not live and STREAM_LOOP) else ""
        dur = f"-t {STREAM_LIMIT_SEC} " if (not live and STREAM_LIMIT_SEC > 0) else ""
        
        if has_audio:
            in_args = f'{re_flag}{loop}{inf}-i "{src}" '
            map_args = "-map 0:v -map 0:a "
            extra = ""
        else:
            in_args = f'{re_flag}{loop}{inf}-i "{src}" -f lavfi -i anullsrc=channel_layout=stereo:sample_rate=44100 '
            map_args = "-map 0:v -map 1:a "
            extra = "-shortest "
        
        if n == 1:
            if USE_YT:
                target = f"rtmp://a.rtmp.youtube.com/live2/{YOUTUBE_KEY}"
                cmd = f'ffmpeg -hide_banner -loglevel info {in_args}{dur}{ef}{map_args}{extra}-flvflags no_duration_filesize -f flv "{target}"'
            else:
                target = f"rtmps://live-api-s.facebook.com:443/rtmp/{FACEBOOK_KEY}"
                cmd = f'ffmpeg -hide_banner -loglevel info {in_args}{dur}{ef}{map_args}{extra}-flvflags no_duration_filesize -f flv "{target}"'
        else:
            tee = _tee()
            cmd = f'ffmpeg -hide_banner -loglevel info {in_args}{dur}{ef}{map_args}{extra}-flvflags no_duration_filesize -f tee "{tee}"'
        
        ok, err = _run_ff(cmd, MAX_RUN_SECONDS)
        if ok: log("✅ Stream done"); return True
        if err == "interrupted": return False
        if err == "time_limit": return True
        
        log(f"⚠️ Attempt {att} failed")
        if err and err not in ("done", "time_limit", "interrupted"):
            for l in err.split("\n")[-3:]:
                if l and l != "done": log(f"      {l[:200]}")
        
        if att < MAX_STREAM_RETRIES: time.sleep(5 * att)
    return False

def move_link(game, url, src_file, ok):
    if not ok: log("⏭ Not moved (fail)"); return False
    if not src_file or not os.path.exists(src_file): log("⚠️ No src"); return False
    dst = os.path.join(STREAMED_DIR, f"{game}_streamed.txt")
    kind = "manual" if MANUAL_DIR in src_file else "livestream"
    try:
        with open(src_file, 'r', encoding='utf-8', errors='ignore') as f: lines = f.readlines()
    except Exception: return False
    new, moved = [], None
    for line in lines:
        if moved is None and url in line: moved = line
        else: new.append(line)
    if not moved: log("⚠️ URL not found"); return False
    try:
        with open(src_file, 'w', encoding='utf-8') as f: f.writelines(new)
    except Exception: return False
    try:
        with open(dst, 'a', encoding='utf-8') as f:
            f.write(f"\n# [SUCCESS] {now_ist_ampm()} | source={kind}\n")
            f.write(moved if moved.endswith('\n') else moved + '\n')
    except Exception:
        with open(src_file, 'a', encoding='utf-8') as f: f.write(moved)
        return False
    log(f"✅ Moved [{kind}] → {dst} | Pending: {len([l for l in new if l.strip()])}")
    return True


# ═══════════════════════════════════════════════════════════
# DASHBOARD + GIT
# ═══════════════════════════════════════════════════════════
def update_dashboard(res):
    log("📊 Dashboard...")
    game, url = res["game_name"], res["source_url"]
    title = read_title(res.get("ai_title", ""))
    gl = res["game_list"]
    L = [f"# 🎮 AGENT DASHBOARD v7\n\n", f"> **Updated:** {now_ist_ampm()} IST\n", f"> **Game:** **{game}**\n", f"> **Title:** {title}\n", f"> **Source:** [{url[:80]}]({url})\n\n---\n\n", "## 📊 Games\n\n| Game | Streamed | Views | Pending | Status |\n|---|---|---|---|---|\n"]
    for g in gl:
        sf = f"{STREAMED_DIR}/{g}_streamed.txt"
        sc = 0
        if os.path.exists(sf):
            try:
                with open(sf, 'r', encoding='utf-8', errors='ignore') as f: c = f.read()
                sc = len(re.findall(r'\|\s*Link:', c)) or len(re.findall(r'https?://', c))
            except Exception: pass
        views = 0
        if FB_ACCESS_TOKEN and os.path.exists(sf):
            try:
                with open(sf, 'r', encoding='utf-8', errors='ignore') as f: c = f.read()
                vids = re.findall(r'Video id\s*:\s*(\S+)', c)[:10]
                for v in vids: views += fb_views(v, FB_ACCESS_TOKEN)
            except Exception: pass
        p = 0
        for pf in [f"{AUTO_DIR}/{g}_links_livestream.txt", f"{MANUAL_DIR}/{g}_manual.txt"]:
            if os.path.exists(pf):
                try:
                    with open(pf, 'r', encoding='utf-8', errors='ignore') as f: c = f.read()
                    p += max(len(re.findall(r'\|\s*Link:', c)), len(extract_urls(c)))
                except Exception: pass
        st = "🎯 ACTIVE" if g == game else "⏳"
        L.append(f"| **{g}** | {sc} | {views:,} | {p} | {st} |\n")
    try:
        with open(DASHBOARD_PATH, 'w', encoding='utf-8') as f: f.writelines(L)
        log(f"✅ {DASHBOARD_PATH}")
    except Exception as e: log(f"⚠️ {e}")

def git_push():
    try:
        subprocess.run("git config user.name 'github-actions[bot]'", shell=True, check=False)
        subprocess.run("git config user.email '41898282+github-actions[bot]@users.noreply.github.com'", shell=True, check=False)
        subprocess.run("git add -A", shell=True, check=False)
        cr = subprocess.run("git commit -m '🤖 Agent run [skip ci]'", shell=True, capture_output=True, text=True)
        if cr.returncode == 0: log("   ✅ Committed")
        subprocess.run("git pull --rebase origin main", shell=True, check=False)
        pr = subprocess.run("git push", shell=True, capture_output=True, text=True)
        log(f"   {'🚀 Pushed' if pr.returncode == 0 else '⚠️ Push failed'}")
    except Exception as e: log(f"⚠️ Git: {e}")


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════
def main():
    log("=" * 62)
    log("🎮 MASTER AGENT v8.4 — SINGLE FILE (Full Logs + Title Fix)")
    log(f"   Commentary : {'ON' if COMMENTARY_ENABLED else 'OFF'}")
    log(f"   Stream     : {'ON' if STREAMING_ENABLED else 'OFF'} [{STREAM_MODE.upper()}]")
    log(f"   YT:{'✅' if USE_YT else '❌'} FB:{'✅' if USE_FB else '❌'}")
    log(f"   Logs       : {LOGS_DIR}/")
    log(f"   FPS        : {FRAMES_PER_SECOND}")
    log("=" * 62)

    exit_code = 1
    try:
        log("\n🧠 [1/4] Brain...")
        result = run_brain()
        if not result:
            log("❌ Brain failed")
            return
        
        game = result["game_name"]
        url = result["source_url"]
        title = result["ai_title"]
        src_file = result["source_file"]
        src_kind = result["source_kind"]

        log(f"\n🎯 Game: {game}")
        log(f"📺 Title: {title}")
        log(f"🔗 {url[:120]}")
        log(f"📂 {os.path.basename(src_file)} [{src_kind}]")

        st = detect_source_type(url)
        log(f"🧭 Type: {st}")

        if is_live_source(url):
            log("\n🔴 LIVE relay")
            if COMMENTARY_ENABLED: log("   ⚠️ Live: no commentary")
            ok = stream_rtmp(url, live=True)
            move_link(game, url, src_file, ok)
            update_dashboard({**result, "ai_title": title})
            exit_code = 0 if ok else 1
            return

        log("\n📥 [2/4] Download...")
        local = download_video(url, "source.mp4")
        if not local:
            log("❌ Download failed")
            return

        if COMMENTARY_ENABLED:
            log("\n🎙️ [3/4] Commentary + Title...")
        else:
            log("\n🏷️ [3/4] Title ONLY (Commentary OFF)...")
            
        final = run_commentary_pipeline(local, "dubbed.mp4" if COMMENTARY_ENABLED else local)
        title = read_title(title)

        if not os.path.exists(final):
            log(f"❌ Missing: {final}")
            return

        log(f"\n📡 [4/4] Stream {os.path.basename(final)}...")
        ok = stream_rtmp(final, live=False)
        move_link(game, url, src_file, ok)
        update_dashboard({**result, "ai_title": title})
        exit_code = 0 if ok else 1

        log("\n" + "=" * 62)
        log(f"{'✅ Complete' if ok else '❌ Failed'}")
        log(f"🎮 {game}")
        log(f"📺 {title}")
        log(f"🎙️ {'ON' if COMMENTARY_ENABLED else 'OFF'} | 📡 {STREAM_MODE.upper()}")
        log(f"🔗 {'Moved' if ok else 'Pending (retry next)'}")
        log("=" * 62)

    except Exception as e:
        log(f"\n❌ Fatal error: {e}")
        exit_code = 1
    finally:
        cleanup_temp_files()
        git_push()
        sys.exit(exit_code)

if __name__ == "__main__":
    main()