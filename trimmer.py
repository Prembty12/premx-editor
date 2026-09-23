import os
import sys
import subprocess

def smart_trim_video(input_url, output_path, start_sec=0, duration_sec=45):
    if duration_sec < 12:
        duration_sec = 12

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start_sec),
        "-i", input_url,
        "-t", str(duration_sec),
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        output_path
    ]

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print(f"✂️ Successfully trimmed video snippet: {output_path}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error during video trimming: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) > 3:
        v_url = sys.argv[1]
        out_file = sys.argv[2]
        start = int(sys.argv[3])
        smart_trim_video(v_url, out_file, start_sec=start)
