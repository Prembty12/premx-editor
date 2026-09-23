import ast
import base64
import json
import os
import random
import re
import sys
import time
from datetime import datetime
import requests

# GitHub Actions me live/instant terminal logs dikhane ke liye
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)


def get_current_time():
    return datetime.now().strftime("%H:%M:%S")


def get_random_openrouter_key():
    """Gemini logic ki tarah available keys me se randomly ek key pick karega"""
    keys = []
    for i in range(1, 6):
        key_name = "OPENROUTER_API_KEY" if i == 1 else f"OPENROUTER_API_KEY_{i}"
        val = os.environ.get(key_name, "").strip()
        if val and val not in keys:
            keys.append(val)
    return random.choice(keys) if keys else None


def run_openrouter_agent():
    start_time = time.time()

    grid_path = os.environ.get(
        "GRID_PATH", "temp_frames/merged_60_grid_screenshot.jpg"
    )
    source_duration = os.environ.get("SOURCE_DURATION", "60")
    insights_summary = os.environ.get("INSIGHTS_SUMMARY", "")
    style_prompt = os.environ.get("STYLE_PROMPT", "")

    primary_model = os.environ.get(
        "OPENROUTER_MODEL",
        "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    ).strip()
    fallback_model = "openrouter/free"

    if not os.path.exists(grid_path):
        print(
            json.dumps({"status": "failed", "error": "Grid image not found"})
        )
        return

    # Image ko Base64 me encode karein
    try:
        with open(grid_path, "rb") as f:
            base64_image = base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        print(
            json.dumps(
                {"status": "failed", "error": f"Base64 error: {str(e)}"}
            )
        )
        return

    prompt_text = f"""Analyze the provided 9:16 gaming screenshot grid. Total video source duration is {source_duration} seconds.
Insights Context: {insights_summary}
Style Directive: {style_prompt}

Your primary job as an expert video editor is to find the most thrilling, high-action segment, skipping dull introductions.
Return a JSON object with EXACTLY three keys:
1. 'title' (string: viral title with 1-3 emojis)
2. 'start_time' (string format HH:MM:SS indicating exact peak action start time based on grid timestamps)
3. 'clip_duration' (integer: length between 12 and 45 seconds meeting monetization rules)
Return ONLY valid JSON format, no markdown wrapping."""

    raw_result = None
    requested_model = primary_model
    routed_model = primary_model
    max_retries = 4

    # Gemini jaisa exact Retry + Random Key Switch Loop
    for attempt in range(1, max_retries + 1):
        api_key = get_random_openrouter_key()
        if not api_key:
            print(
                json.dumps(
                    {"status": "failed", "error": "No OpenRouter API keys found"}
                )
            )
            return

        # Attempt 1-2 me Primary, Attempt 3-4 me Fallback Model try hoga
        current_model = (
            primary_model if attempt <= 2 else fallback_model
        )

        print(
            f"🤖 [{get_current_time()}] OpenRouter Attempt {attempt}/{max_retries} | Model: {current_model} | Key: {api_key[:8]}...",
            file=sys.stderr,
            flush=True,
        )

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": current_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt_text},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            },
                        },
                    ],
                }
            ],
            "max_tokens": 256,
            "temperature": 0.4,
        }

        try:
            # Gemini jaisa strict timeout (8 Seconds) taaki script kabhie na atke
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=8,
            )

            if response.status_code == 200:
                res_data = response.json()
                choices = res_data.get("choices", [])
                if choices:
                    msg = choices[0].get("message", {})
                    content = msg.get("content", "") or msg.get("reasoning", "")
                    if content:
                        raw_result = str(content)
                        requested_model = current_model
                        routed_model = res_data.get("model", current_model)
                        print(
                            f"✅ [{get_current_time()}] Success on Attempt {attempt}! Routed Model: {routed_model}",
                            file=sys.stderr,
                            flush=True,
                        )
                        break
        except Exception as e:
            print(
                f"⚠️ [{get_current_time()}] Attempt {attempt} Error: {e}",
                file=sys.stderr,
                flush=True,
            )

        print(
            f"⚠️ [{get_current_time()}] Attempt {attempt} failed. Retrying with a new random key...",
            file=sys.stderr,
            flush=True,
        )
        time.sleep(1)

    if not raw_result:
        total_time = round(time.time() - start_time, 2)
        print(
            json.dumps({
                "status": "failed",
                "error": "All OpenRouter attempts failed",
                "execution_time_seconds": total_time,
            })
        )
        return

    # Clean JSON Output Parsing
    try:
        cleaned = re.sub(r"```json", "", raw_result, flags=re.IGNORECASE)
        cleaned = re.sub(r"```", "", cleaned).strip()

        match = re.search(r"\{.*?\}", cleaned, re.DOTALL)
        target_str = match.group(0) if match else cleaned

        try:
            data = json.loads(target_str)
        except Exception:
            data = ast.literal_eval(target_str)

        title = data.get("title")
        start_time_val = data.get("start_time")
        duration = data.get("clip_duration", data.get("duration", 15))

        total_time = round(time.time() - start_time, 2)

        if title and start_time_val:
            dur_int = max(12, min(45, int(duration)))
            print(
                json.dumps({
                    "status": "success",
                    "requested_model": requested_model,
                    "routed_model": routed_model,
                    "title": str(title),
                    "start_time": str(start_time_val),
                    "duration": dur_int,
                    "execution_time_seconds": total_time,
                })
            )
        else:
            print(
                json.dumps({
                    "status": "failed",
                    "error": "Missing keys in JSON",
                    "execution_time_seconds": total_time,
                })
            )

    except Exception as e:
        total_time = round(time.time() - start_time, 2)
        print(
            json.dumps({
                "status": "failed",
                "error": f"JSON Parsing error: {str(e)}",
                "execution_time_seconds": total_time,
            })
        )


if __name__ == "__main__":
    run_openrouter_agent()
