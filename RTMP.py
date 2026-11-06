
#!/usr/bin/env python3
"""
MASTER AGENT v34.1
STABLE FACEBOOK + YOUTUBE STREAMING ENGINE

REMOVED:
- game_links_livestream
- game_links_streamed
- agent_memory.json
- Game Memory / last played game

FIXED:
- Non-blocking bounded log queue
- Progress monitoring without log starvation
- Stream keys hidden in logs
- Source URLs hidden in logs
- FFmpeg process cleanup
- Retry and runtime deadline
- Audio mixing and optional watermark
- Automatic and manual source selection

FEATURES:
- Facebook + YouTube RTMP
- Single FFmpeg encoder with tee output
- 1080p presets
- 30 FPS default
- Manual URL + automatic rotation
- Finite / 24-hour looping
- Six visual filters
- Optional background music
- Optional logo watermark
- Retry with exponential backoff
- Input reconnect options
- Graceful shutdown
"""

import os
import sys
import re
import json
import glob
import time
import signal
import random
import shutil
import queue
import threading
import subprocess

from datetime import datetime, timedelta, timezone


# =========================================================
# 1. CONFIGURATION
# =========================================================

def log(message):
    print(
        f"[{datetime.now().strftime('%H:%M:%S')}] {message}",
        file=sys.stderr,
        flush=True
    )


def env_int(name, default, minimum, maximum):
    try:
        value = int(os.getenv(name, str(default)))
        return max(minimum, min(maximum, value))
    except (ValueError, TypeError):
        return default


def env_bool(name, default=True):
    value = os.getenv(
        name, str(default)
    ).strip().lower()

    return value in ("1", "true", "yes", "on")


INTERRUPTED = threading.Event()


def signal_handler(signum, frame):
    log("Shutdown signal received.")
    INTERRUPTED.set()


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


# Directories
MANUAL_DIR = "Manual_links"
AUTO_DIR = "Auto_links"

AUDIO_FILE = "optional_audio.mp3"

for directory in (MANUAL_DIR, AUTO_DIR):
    os.makedirs(directory, exist_ok=True)


# Streaming
STREAM_ENABLED = env_bool("STREAM_ENABLED", True)

STREAM_MODE = os.getenv(
    "STREAM_MODE", "both"
).strip().lower()

if STREAM_MODE not in ("fb", "yt", "both"):
    STREAM_MODE = "both"


# Stream keys
MANUAL_FB_KEY = os.getenv(
    "MANUAL_FB_KEY", ""
).strip()

MANUAL_YT_KEY = os.getenv(
    "MANUAL_YT_KEY", ""
).strip()

SECRET_FB_KEY = os.getenv(
    "FACEBOOK_STREAM_KEY", ""
).strip()

SECRET_YT_KEY = os.getenv(
    "YOUTUBE_STREAM_KEY", ""
).strip()

FACEBOOK_KEY = MANUAL_FB_KEY or SECRET_FB_KEY
YOUTUBE_KEY = MANUAL_YT_KEY or SECRET_YT_KEY

USE_FB = (
    STREAM_MODE in ("fb", "both")
    and bool(FACEBOOK_KEY)
)

USE_YT = (
    STREAM_MODE in ("yt", "both")
    and bool(YOUTUBE_KEY)
)

STREAMING_ENABLED = (
    STREAM_ENABLED and (USE_FB or USE_YT)
)


# Source URLs
MANUAL_VIDEO_URL = os.getenv(
    "MANUAL_VIDEO_URL", ""
).strip()

AUDIO_URL = os.getenv(
    "AUDIO_URL", ""
).strip()


# Video configuration
RATIO = os.getenv("RATIO", "3").strip()
FILTER = os.getenv("FILTER", "2").strip()
SPEED_OPT = os.getenv("SPEED", "1").strip()
FPS_OPT = os.getenv("FPS", "1").strip()

if RATIO not in ("1", "2", "3", "4", "5"):
    RATIO = "3"

if FILTER not in ("1", "2", "3", "4", "5", "6"):
    FILTER = "2"

if SPEED_OPT not in ("1", "2", "3", "4", "5", "6"):
    SPEED_OPT = "1"

if FPS_OPT not in ("1", "2"):
    FPS_OPT = "1"

BITRATE = env_int("BITRATE", 8, 2, 20)

TARGET_FPS = 30 if FPS_OPT == "1" else 60

BUFFER_SIZE = os.getenv(
    "BUFFER_SIZE", f"{BITRATE * 2}M"
).strip()

FFMPEG_THREADS = env_int(
    "FFMPEG_THREADS", 0, 0, 64
)


# Retry configuration
STREAM_GAP_MIN = env_int(
    "STREAM_GAP_MIN", 0, 0, 1440
)

MAX_STREAM_RETRIES = env_int(
    "MAX_STREAM_RETRIES", 3, 0, 20
)

RETRY_DELAY = env_int(
    "RETRY_DELAY", 5, 1, 300
)

PROGRESS_TIMEOUT = env_int(
    "PROGRESS_TIMEOUT", 180, 30, 1800
)

INPUT_TIMEOUT = env_int(
    "INPUT_TIMEOUT", 30000000, 5000000, 120000000
)

MAX_RUN_SECONDS = env_int(
    "MAX_RUN_SECONDS", 19800, 60, 86400
)

META_ARTIST = os.getenv(
    "META_ARTIST", "PremxGamer"
)


# Loop configuration
LOOP_INPUT = os.getenv(
    "LOOP_COUNT", "0"
).strip().lower()

if LOOP_INPUT in (
    "24", "24h", "24h/24",
    "-1", "infinite", "inf"
):
    LOOP_ARG = -1
    MAX_RUN_SECONDS = 86400
    LOOP_MSG = "24 Hours"

else:
    try:
        plays = int(LOOP_INPUT)

        if plays > 1:
            LOOP_ARG = min(plays - 1, 1000)
            LOOP_MSG = f"{plays} Times"
        else:
            LOOP_ARG = 0
            LOOP_MSG = "Once"

    except ValueError:
        LOOP_ARG = 0
        LOOP_MSG = "Once (Default)"


# Playback speed
SPEED_MAP = {
    "1": (1.0, 1.0),
    "2": (1.05, 1.05),
    "3": (1.10, 1.10),
    "4": (1.25, 1.25),
    "5": (1.50, 1.50),
    "6": (0.80, 0.80),
}

VIDEO_SPEED, AUDIO_SPEED = SPEED_MAP[SPEED_OPT]


# Timezone
try:
    from zoneinfo import ZoneInfo
    IST = ZoneInfo("Asia/Kolkata")
except ImportError:
    IST = timezone(timedelta(hours=5, minutes=30))


def now_ist():
    return datetime.now(IST).strftime(
        "%Y-%m-%d %I:%M:%S %p"
    )


# =========================================================
# 2. DEPENDENCY CHECK
# =========================================================

def check_dependencies():

    for executable in ("ffmpeg", "ffprobe"):

        if not shutil.which(executable):
            log(f"ERROR: {executable} is not installed.")
            return False

    if AUDIO_URL and not shutil.which("yt-dlp"):
        log(
            "WARNING: yt-dlp missing. "
            "Background audio will be disabled."
        )

    return True


# =========================================================
# 3. SOURCE MANAGEMENT
# =========================================================

def extract_game(filepath):

    base = os.path.basename(filepath)

    suffixes = (
        "_manual.txt",
        "_links_livestream.txt",
        "_livestream.txt",
        ".txt"
    )

    for suffix in suffixes:

        if base.lower().endswith(suffix):
            return base[:-len(suffix)].strip()

    return os.path.splitext(base)[0].strip()


def extract_urls(content):

    pattern = r'https?://[^\s\n\r\)\]\'"<>,;]+'

    urls = re.findall(pattern, content)

    return [
        url.rstrip(".,;)'\"")
        for url in urls
    ]


def read_urls(filepath):

    try:

        with open(
            filepath,
            "r",
            encoding="utf-8",
            errors="ignore"
        ) as file:

            return extract_urls(file.read())

    except OSError as error:

        log(f"Cannot read source file: {error}")
        return []


def get_source_file(game, manual, automatic):

    manual_file = manual.get(game)

    if manual_file and os.path.isfile(manual_file):

        if read_urls(manual_file):
            return manual_file, "manual"

    auto_file = automatic.get(game)

    if auto_file and os.path.isfile(auto_file):

        if read_urls(auto_file):
            return auto_file, "auto"

    return None, None


def run_brain():

    log("Automatic source selection started.")

    manual_files = glob.glob(
        os.path.join(MANUAL_DIR, "*.txt")
    )

    auto_files = glob.glob(
        os.path.join(AUTO_DIR, "*.txt")
    )

    manual = {
        extract_game(path): path
        for path in manual_files
    }

    automatic = {
        extract_game(path): path
        for path in auto_files
    }

    # Include manual-only source files.
    game_list = sorted(
        set(manual.keys()) | set(automatic.keys())
    )

    if not game_list:

        log(
            "No source files found. "
            "Check Auto_links and Manual_links."
        )

        return None

    candidates = []

    for game in game_list:

        source_file, source_kind = get_source_file(
            game,
            manual,
            automatic
        )

        if not source_file:
            continue

        urls = read_urls(source_file)

        if not urls:
            continue

        candidates.append({
            "game_name": game,
            "source_url": random.choice(urls),
            "source_file": source_file,
            "source_kind": source_kind
        })

    if not candidates:

        log("No valid URLs found in source files.")
        return None

    selected = random.choice(candidates)

    log(
        f"Selected game: {selected['game_name']} "
        f"[{selected['source_kind']}]"
    )

    return selected


# =========================================================
# 4. VIDEO PROBE
# =========================================================

def get_video_info(url):

    command = [
        "ffprobe",
        "-v", "error",
        "-show_entries",
        "format=duration:stream=codec_type",
        "-of", "json",
        url
    ]

    try:

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=45
        )

        if result.returncode != 0:
            log("Video probe failed.")
            return 0.0, False

        data = json.loads(result.stdout)

        duration = float(
            data.get("format", {}).get("duration", 0) or 0
        )

        has_audio = any(
            stream.get("codec_type") == "audio"
            for stream in data.get("streams", [])
        )

        log(f"Video duration: {duration:.1f} seconds")
        log(f"Original audio: {has_audio}")

        return duration, has_audio

    except subprocess.TimeoutExpired:

        log("Video probe timed out.")
        return 0.0, False

    except Exception as error:

        log(f"Probe warning: {error}")
        return 0.0, False


# =========================================================
# 5. OPTIONAL BACKGROUND AUDIO
# =========================================================

def download_audio():

    if not AUDIO_URL:
        return False

    if not shutil.which("yt-dlp"):
        return False

    try:

        if os.path.exists(AUDIO_FILE):
            os.remove(AUDIO_FILE)

        command = [
            "yt-dlp",
            "--no-playlist",
            "--extract-audio",
            "--audio-format", "mp3",
            "--output", "optional_audio.%(ext)s",
            AUDIO_URL
        ]

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=600
        )

        if (
            result.returncode == 0
            and os.path.isfile(AUDIO_FILE)
            and os.path.getsize(AUDIO_FILE) > 0
        ):

            log("Background music downloaded.")
            return True

        log("Background music download failed.")

    except subprocess.TimeoutExpired:

        log("Background audio download timed out.")

    except Exception as error:

        log(f"Background audio error: {error}")

    return False


# =========================================================
# 6. VIDEO FILTERS
# =========================================================

def build_video_filter():

    ratio_map = {

        "1": (
            "scale=1080:1080:"
            "force_original_aspect_ratio=increase,"
            "crop=1080:1080"
        ),

        "2": (
            "scale=1080:1350:"
            "force_original_aspect_ratio=increase,"
            "crop=1080:1350"
        ),

        "3": (
            "scale=1080:1920:"
            "force_original_aspect_ratio=increase,"
            "crop=1080:1920"
        ),

        "4": (
            "scale=1080:1440:"
            "force_original_aspect_ratio=increase,"
            "crop=1080:1440"
        ),

        "5": (
            "scale=1440:1080:"
            "force_original_aspect_ratio=increase,"
            "crop=1440:1080"
        )
    }

    filters = {

        "1": (
            "eq=brightness=0.02:contrast=1.18:saturation=1.25,"
            "hqdn3d=1.5:1.5:6:6,"
            "unsharp=3:3:0.75:3:3:0"
        ),

        "2": (
            "eq=brightness=0.02:contrast=1.20:"
            "saturation=1.22:gamma=1.11,"
            "vibrance=intensity=0.20,"
            "hqdn3d=1.5:1.5:6:6,"
            "cas=0.3,"
            "noise=alls=3:allf=t+u,"
            "unsharp=3:3:0.75:3:3:0"
        ),

        "3": (
            "eq=brightness=0.02:contrast=1.10:"
            "saturation=1.10:gamma=1.10,"
            "vibrance=intensity=0.10,"
            "hqdn3d=1:1:3:3,"
            "cas=0.15,"
            "noise=alls=2:allf=t+u,"
            "unsharp=3:3:0.2:3:3:0"
        ),

        "4": (
            "eq=brightness=0.15:contrast=1.20:gamma=1.25,"
            "unsharp=5:5:1.0:5:5:0"
        ),

        "5": (
            "eq=contrast=1.25:saturation=1.20,"
            "colorbalance=rs=0.08:gs=0.02:bs=-0.08,"
            "unsharp=5:5:1.2:5:5:0"
        ),

        "6": (
            "eq=contrast=1.35:saturation=1.55:gamma=1.05,"
            "unsharp=7:7:2.5:7:7:0"
        )
    }

    parts = []

    if VIDEO_SPEED != 1.0:
        parts.append(f"setpts=PTS/{VIDEO_SPEED}")

    parts.append(ratio_map[RATIO])

    selected_filter = filters.get(FILTER, "")

    if selected_filter:
        parts.append(selected_filter)

    parts.append(f"fps={TARGET_FPS}")

    parts.append(
        "scale=trunc(iw/2)*2:trunc(ih/2)*2"
    )

    return ",".join(parts)


# =========================================================
# 7. AUDIO FILTER
# =========================================================

def build_audio_filter(has_audio, music_exists):

    filters = []

    if has_audio:

        filters.append(
            f"[0:a]atempo={AUDIO_SPEED},"
            "aresample=48000[original]"
        )

    if music_exists:

        filters.append(
            "[1:a]aresample=48000[music]"
        )

        if has_audio:

            filters.append(
                "[original][music]"
                "amix=inputs=2:duration=first:"
                "dropout_transition=2,"
                "alimiter=limit=0.95[aout]"
            )

        else:

            filters.append(
                "[music]volume=0.8,"
                "aresample=48000[aout]"
            )

        return ";".join(filters), "[aout]"

    if has_audio:

        return (
            "[original]anull[aout]",
            "[aout]"
        )

    return "", None


# =========================================================
# 8. RTMP DESTINATIONS
# =========================================================

def escape_tee_url(url):

    return (
        url.replace("\\", "\\\\")
           .replace("|", "\\|")
           .replace("[", "\\[")
           .replace("]", "\\]")
    )


def get_output_targets():

    targets = []

    if USE_YT:

        targets.append(
            "rtmp://a.rtmp.youtube.com/live2/"
            + YOUTUBE_KEY
        )

    if USE_FB:

        targets.append(
            "rtmps://live-api-s.facebook.com:443/rtmp/"
            + FACEBOOK_KEY
        )

    return targets


# =========================================================
# 9. BUILD FFMPEG COMMAND
# =========================================================

def build_ffmpeg_command(
    url,
    game_name,
    has_audio,
    music_exists
):

    command = [
        "ffmpeg",
        "-hide_banner",
        "-nostats",
        "-loglevel", "warning",
        "-stats_period", "5",
        "-progress", "pipe:1"
    ]

    # Video input
    if LOOP_ARG != 0:

        command += [
            "-stream_loop", str(LOOP_ARG)
        ]

    command += [
        "-re",
        "-thread_queue_size", "512",
        "-rw_timeout", str(INPUT_TIMEOUT),
        "-reconnect", "1",
        "-reconnect_streamed", "1",
        "-reconnect_delay_max", "5",
        "-i", url
    ]

    # Music input
    if music_exists:

        command += [
            "-stream_loop", "-1",
            "-thread_queue_size", "256",
            "-i", AUDIO_FILE
        ]

    filters = [
        f"[0:v]{build_video_filter()}[vid]"
    ]

    # Optional logo
    logo_exists = (
        os.path.isfile("logo.png")
        and os.path.getsize("logo.png") > 0
    )

    if logo_exists:

        logo_index = 2 if music_exists else 1

        command += [
            "-i", "logo.png"
        ]

        filters.append(
            f"[{logo_index}:v]scale=160:-1[logo]"
        )

        filters.append(
            "[vid][logo]overlay=30:H-h-20[vout]"
        )

        video_map = "[vout]"

    else:

        video_map = "[vid]"

    # Audio
    audio_filter, audio_map = build_audio_filter(
        has_audio,
        music_exists
    )

    if audio_filter:
        filters.append(audio_filter)

    command += [
        "-filter_complex", ";".join(filters),
        "-map", video_map
    ]

    if audio_map:
        command += ["-map", audio_map]
    else:
        command += ["-an"]

    # Video encoder
    command += [
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-threads", str(FFMPEG_THREADS),
        "-profile:v", "high",
        "-pix_fmt", "yuv420p",
        "-b:v", f"{BITRATE}M",
        "-maxrate", f"{BITRATE}M",
        "-bufsize", BUFFER_SIZE,
        "-r", str(TARGET_FPS),
        "-fps_mode", "cfr",
        "-g", str(TARGET_FPS * 2),
        "-keyint_min", str(TARGET_FPS * 2),
        "-sc_threshold", "0"
    ]

    # Audio encoder
    if audio_map:

        command += [
            "-c:a", "aac",
            "-b:a", "128k",
            "-ar", "48000",
            "-ac", "2"
        ]

    # Stop at video end if music is the only audio.
    if music_exists and not has_audio:
        command += ["-shortest"]

    command += [
        "-metadata", f"title={game_name} Gameplay",
        "-metadata", f"artist={META_ARTIST}",
        "-max_muxing_queue_size", "1024"
    ]

    targets = get_output_targets()

    if not targets:
        raise RuntimeError("No RTMP destinations configured.")

    if len(targets) == 1:

        command += [
            "-flvflags", "no_duration_filesize",
            "-f", "flv",
            targets[0]
        ]

    else:

        tee_outputs = []

        for target in targets:

            tee_outputs.append(
                "[f=flv:onfail=ignore]"
                + escape_tee_url(target)
            )

        command += [
            "-f", "tee",
            "|".join(tee_outputs)
        ]

    return command


# =========================================================
# 10. SAFE LOGGING
# =========================================================

def safe_command_log(command, source_url=""):

    safe = " ".join(
        str(part) for part in command
    )

    secrets = [
        FACEBOOK_KEY,
        YOUTUBE_KEY,
        MANUAL_FB_KEY,
        MANUAL_YT_KEY,
        source_url,
        MANUAL_VIDEO_URL,
        AUDIO_URL
    ]

    # Replace longest secrets first.
    secrets = sorted(
        {item for item in secrets if item},
        key=len,
        reverse=True
    )

    for secret in secrets:
        safe = safe.replace(secret, "[HIDDEN]")

    return safe


# =========================================================
# 11. PROCESS MANAGEMENT
# =========================================================

def terminate_process(process):

    if process is None:
        return

    if process.poll() is not None:
        return

    try:

        process.send_signal(signal.SIGINT)
        process.wait(timeout=15)
        return

    except subprocess.TimeoutExpired:
        pass

    except Exception:
        pass

    try:

        process.terminate()
        process.wait(timeout=8)

    except subprocess.TimeoutExpired:

        process.kill()

        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass

    except Exception:
        pass


# =========================================================
# 12. NON-BLOCKING READER THREAD
# =========================================================

def reader_thread(pipe, output_queue, source):

    important_words = (
        "error",
        "failed",
        "unable",
        "refused",
        "timeout",
        "invalid",
        "connection",
        "broken pipe",
        "server returned"
    )

    try:

        for line in iter(pipe.readline, ""):

            line = line.rstrip()

            # Progress messages are low-volume and important.
            if source == "progress":

                try:
                    output_queue.put_nowait(
                        (source, line)
                    )
                except queue.Full:
                    # Never block the FFmpeg pipe reader.
                    continue

            else:

                # Drop ordinary stderr messages.
                lower = line.lower()

                if any(
                    word in lower
                    for word in important_words
                ):

                    try:
                        output_queue.put_nowait(
                            (source, line)
                        )
                    except queue.Full:
                        # Drop excess logs, never block.
                        continue

    except Exception:
        pass

    finally:

        try:
            output_queue.put_nowait(
                (source, None)
            )
        except queue.Full:
            pass


# =========================================================
# 13. FFMPEG MONITOR
# =========================================================

def run_ffmpeg(command, deadline, source_url):

    if INTERRUPTED.is_set():
        return False

    log("Starting FFmpeg...")

    log(
        safe_command_log(
            command,
            source_url
        )
    )

    try:

        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )

    except Exception as error:

        log(f"FFmpeg start failed: {error}")
        return False

    # Bounded queue. Reader threads never block on a full queue.
    messages = queue.Queue(maxsize=1000)

    stdout_thread = threading.Thread(
        target=reader_thread,
        args=(process.stdout, messages, "progress"),
        daemon=True
    )

    stderr_thread = threading.Thread(
        target=reader_thread,
        args=(process.stderr, messages, "error"),
        daemon=True
    )

    stdout_thread.start()
    stderr_thread.start()

    start_time = time.monotonic()
    last_progress = start_time
    last_log = start_time

    try:

        while process.poll() is None:

            if INTERRUPTED.is_set():

                log("Shutdown requested. Stopping FFmpeg.")
                terminate_process(process)
                return False

            now = time.monotonic()

            # Global runtime deadline
            if now >= deadline:

                log("Maximum stream duration reached.")

                terminate_process(process)
                return True

            try:

                source, line = messages.get(
                    timeout=0.5
                )

                if line is not None:

                    if source == "progress":

                        if (
                            line.startswith("frame=")
                            or line.startswith("out_time=")
                            or line.startswith("progress=")
                        ):

                            last_progress = now

                        if line.startswith("speed="):

                            speed = line.split(
                                "=", 1
                            )[-1]

                            if now - last_log >= 5:

                                log(
                                    f"Encoding speed: {speed}"
                                )

                                last_log = now

                        elif line.startswith("frame="):

                            frame = line.split(
                                "=", 1
                            )[-1]

                            if now - last_log >= 15:

                                log(
                                    f"Processed frames: {frame}"
                                )

                                last_log = now

                    else:

                        # Do not print URLs or keys from error logs.
                        log(f"FFmpeg warning/error: {line[:300]}")

            except queue.Empty:
                pass

            # Stalled progress detection
            if now - last_progress > PROGRESS_TIMEOUT:

                log(
                    "No FFmpeg progress detected. "
                    "Restarting stream."
                )

                terminate_process(process)
                return False

        exit_code = process.wait(timeout=5)

        if exit_code == 0:

            log("FFmpeg completed successfully.")
            return True

        log(f"FFmpeg exited with code: {exit_code}")

        return False

    except Exception as error:

        log(f"FFmpeg monitor error: {error}")

        terminate_process(process)

        return False

    finally:

        if process.poll() is None:
            terminate_process(process)

        for pipe in (
            process.stdout,
            process.stderr
        ):

            try:
                pipe.close()
            except Exception:
                pass


# =========================================================
# 14. RETRY MANAGER
# =========================================================

def stream_with_retry(
    url,
    game_name,
    has_audio,
    music_exists
):

    command = build_ffmpeg_command(
        url,
        game_name,
        has_audio,
        music_exists
    )

    deadline = (
        time.monotonic() + MAX_RUN_SECONDS
    )

    total_attempts = MAX_STREAM_RETRIES + 1

    for attempt in range(total_attempts):

        if INTERRUPTED.is_set():
            return False

        if time.monotonic() >= deadline:

            log("Maximum runtime reached.")
            return True

        log(
            f"Streaming attempt "
            f"{attempt + 1}/{total_attempts}"
        )

        success = run_ffmpeg(
            command,
            deadline,
            url
        )

        if success:
            return True

        if INTERRUPTED.is_set():
            return False

        if attempt >= MAX_STREAM_RETRIES:
            break

        delay = min(
            RETRY_DELAY * (2 ** attempt),
            300
        )

        remaining = deadline - time.monotonic()

        if remaining <= 0:
            return True

        delay = min(delay, remaining)

        log(
            f"Stream failed. "
            f"Retrying in {delay:.0f} seconds."
        )

        if INTERRUPTED.wait(delay):
            return False

    log("All streaming retries exhausted.")

    return False


# =========================================================
# 15. MAIN STREAM FUNCTION
# =========================================================

def stream_direct(url, game_name):

    if not STREAMING_ENABLED:

        log(
            "Streaming disabled or stream keys missing."
        )

        return False

    if not url.startswith(("http://", "https://")):

        log("Invalid source URL.")
        return False

    log("Probing source video...")

    duration, has_audio = get_video_info(url)

    if duration <= 0:

        log(
            "WARNING: Duration unavailable. "
            "Check source URL and media accessibility."
        )

    music_exists = download_audio()

    log("=" * 55)
    log("STREAM CONFIGURATION")
    log(f"Game        : {game_name}")
    log(f"Ratio       : {RATIO}")
    log(f"FPS         : {TARGET_FPS}")
    log(f"Bitrate     : {BITRATE} Mbps")
    log(f"Filter      : {FILTER}")
    log(f"Video speed : {VIDEO_SPEED}x")
    log(f"Original audio: {has_audio}")
    log(f"Music       : {music_exists}")
    log(f"Loop        : {LOOP_MSG}")
    log(f"Facebook    : {USE_FB}")
    log(f"YouTube     : {USE_YT}")
    log(f"Max runtime : {MAX_RUN_SECONDS}s")
    log("=" * 55)

    return stream_with_retry(
        url,
        game_name,
        has_audio,
        music_exists
    )


# =========================================================
# 16. MAIN
# =========================================================

def main():

    log("=" * 60)
    log("MASTER AGENT v34.1")
    log("NO GAME MEMORY")
    log("UPDATED LOGGING + PROCESS MANAGEMENT")
    log("=" * 60)

    log(f"Loop       : {LOOP_MSG}")
    log(f"FPS        : {TARGET_FPS}")
    log(f"Bitrate    : {BITRATE} Mbps")
    log(f"Mode       : {STREAM_MODE}")
    log(f"Retries    : {MAX_STREAM_RETRIES}")

    if not check_dependencies():
        return 1

    if not STREAMING_ENABLED:

        log(
            "ERROR: Streaming is not enabled. "
            "Check stream keys and STREAM_MODE."
        )

        return 1

    # Manual URL gets priority.
    if MANUAL_VIDEO_URL:

        log("Manual video URL selected.")

        game = "Manual_Game"
        url = MANUAL_VIDEO_URL

    else:

        log("Selecting automatic source...")

        result = run_brain()

        if not result:

            log("No valid automatic source found.")
            return 1

        game = result["game_name"]
        url = result["source_url"]

    # Optional start delay
    gap_seconds = STREAM_GAP_MIN * 60

    if gap_seconds > 0:

        log(
            f"Waiting {STREAM_GAP_MIN} minutes "
            "before streaming."
        )

        if INTERRUPTED.wait(gap_seconds):
            return 1

    if INTERRUPTED.is_set():
        return 1

    success = False

    try:

        success = stream_direct(
            url,
            game
        )

    except Exception as error:

        log(f"MAIN ERROR: {error}")
        success = False

    finally:

        if os.path.exists(AUDIO_FILE):

            try:
                os.remove(AUDIO_FILE)
            except OSError:
                pass

    log("=" * 60)

    if success:

        log("STREAM COMPLETED.")
        return 0

    log("STREAM FAILED.")

    return 1


if __name__ == "__main__":
    sys.exit(main())
