import ast
import base64
import json
import os
import re
import sys
import time
from datetime import datetime
import requests

# Instant Terminal logs output ke liye
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)


def get_current_time():
    return datetime.now().strftime("%H:%M:%S")


def call_openrouter(
    grid_path, source_duration, insights, style_prompt, model_name, api_key
):
    invoke_url = "https://openrouter.ai/api/v1/chat/completions"

    try:
        with open(grid_path, "rb") as f:
            base64_image = base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        return {"status": "failed", "error": f"Base64 error: {str(e)}"}

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    prompt_text = f"""Analyze the provided 9:16 gaming screenshot grid. Total video source duration is {source_duration} seconds.
Insights Context: {insights}
Style Directive: {style_prompt}

Your primary job as an expert video editor is to find the most thrilling, high-action segment, skipping dull introductions.
Return a JSON object with EXACTLY three keys:
1. 'title' (string: viral title with 1-3 emojis)
2. 'start_time' (string format HH:MM:SS indicating exact peak action start time based on grid timestamps)
3. 'clip_duration' (integer: length between 12 and 45 seconds meeting monetization rules)
Return ONLY valid JSON format, no markdown wrapping."""

    payload = {
        "model": model_name,
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
        req_start = time.time()
        response = requests.post(
            invoke_url, headers=headers, json=payload, timeout=8
        )
        req_elapsed = round(time.time() - req_start, 2)

        if response.status_code == 200:
            res_json = response.json()
            if "error" in res_json:
                return {
                    "status": "failed",
                    "error": f"API internal error: {res_json['error']}",
                }

            # Capture routed actual model name from OpenRouter response
            actual_model = res_json.get("model", model_name)

            choices = res_json.get("choices", [])
            if choices:
                msg = choices[0].get("message", {})
                raw_result = msg.get("content", "") or msg.get("reasoning", "")
                if raw_result:
                    return {
                        "status": "success",
                        "raw": str(raw_result),
                        "actual_model": actual_model,
                    }

            return {
                "status": "failed",
                "error": "200 OK but missing 'choices'",
            }

        return {
            "status": "failed",
            "error": f"Error {response.status_code}: {response.text[:100]}",
        }
    except requests.exceptions.Timeout:
        return {"status": "failed", "error": "Timed out after 8s"}
    except Exception as e:
        return {"status": "failed", "error": f"Exception: {str(e)}"}


def run_pipeline():
    pipeline_start = time.time()

    grid_path = os.environ.get(
        "GRID_PATH", "temp_frames/merged_60_grid_screenshot.jpg"
    )
    source_duration = os.environ.get("SOURCE_DURATION", "60")
    insights = os.environ.get("INSIGHTS_SUMMARY", "")
    style_prompt = os.environ.get("STYLE_PROMPT", "")

    api_keys = []
    for i in range(1, 6):
        key_env = "OPENROUTER_API_KEY" if i == 1 else f"OPENROUTER_API_KEY_{i}"
        val = os.environ.get(key_env, "").strip()
        if val and val not in api_keys:
            api_keys.append(val)

    if not api_keys:
        print(
            json.dumps(
                {"status": "failed", "error": "No OPENROUTER_API_KEY found"}
            )
        )
        return

    primary_model = os.environ.get(
        "OPENROUTER_MODEL",
        "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    ).strip()
    fallback_model = "openrouter/free"

    if not os.path.exists(grid_path):
        print(
            json.dumps({"status": "failed", "error": "Grid image path not found"})
        )
        return

    attempts = []
    for k_idx, key in enumerate(api_keys, 1):
        attempts.append((primary_model, key, k_idx))
    for k_idx, key in enumerate(api_keys, 1):
        attempts.append((fallback_model, key, k_idx))

    result = None
    requested_model = primary_model
    routed_model = primary_model

    for model, key, k_num in attempts:
        print(
            f"🔄 [{get_current_time()}] Trying Model: {model} | Key #{k_num}...",
            file=sys.stderr,
            flush=True,
        )
        result = call_openrouter(
            grid_path,
            source_duration,
            insights,
            style_prompt,
            model,
            key,
        )

        if result.get("status") == "success":
            requested_model = model
            routed_model = result.get("actual_model", model)
            print(
                f"✅ [{get_current_time()}] Success with Key #{k_num}! (Routed Model: {routed_model})",
                file=sys.stderr,
                flush=True,
            )
            break
        else:
            print(
                f"⚠️ [{get_current_time()}] Key #{k_num} failed:"
                f" {result.get('error')}. Trying next...",
                file=sys.stderr,
                flush=True,
            )

    if result.get("status") != "success":
        total_time = round(time.time() - pipeline_start, 2)
        print(
            json.dumps({
                "status": "failed",
                "error": f"All attempts failed. Last error: {result.get('error')}",
                "execution_time_seconds": total_time,
            })
        )
        return

    try:
        raw_result = result.get("raw", "")
        cleaned = re.sub(r"```json", "", raw_result, flags=re.IGNORECASE)
        cleaned = re.sub(r"```", "", cleaned).strip()

        match = re.search(r"\{.*?\}", cleaned, re.DOTALL)
        target_str = match.group(0) if match else cleaned
        target_str = re.sub(r"(?<=\s|:)\b0+(?=[1-9]\d*)\b", "", target_str)

        try:
            data = json.loads(target_str)
        except Exception:
            data = ast.literal_eval(target_str)

        title = data.get("title")
        start_time = data.get("start_time")
        duration = data.get("clip_duration", data.get("duration", 15))

        total_time = round(time.time() - pipeline_start, 2)

        if title and start_time:
            dur_int = max(12, min(45, int(duration)))
            # Both requested model and actual routed model are returned in output
            print(
                json.dumps({
                    "status": "success",
                    "requested_model": requested_model,
                    "routed_model": routed_model,
                    "title": str(title),
                    "start_time": str(start_time),
                    "duration": dur_int,
                    "execution_time_seconds": total_time,
                })
            )
        else:
            print(
                json.dumps({
                    "status": "failed",
                    "error": "Missing title or start_time in JSON",
                    "execution_time_seconds": total_time,
                })
            )

    except Exception as e:
        total_time = round(time.time() - pipeline_start, 2)
        print(
            json.dumps({
                "status": "failed",
                "error": f"Parsing error: {str(e)}",
                "execution_time_seconds": total_time,
            })
        )


if __name__ == "__main__":
    run_pipeline()
