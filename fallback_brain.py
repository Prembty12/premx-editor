import ast
import base64
import json
import os
import re
import sys
import requests


def parse_json_safely(raw_result):
    """Cleans raw AI response and parses valid JSON"""
    try:
        cleaned = re.sub(r"```json", "", str(raw_result), flags=re.IGNORECASE)
        cleaned = re.sub(r"```", "", cleaned).strip()

        match = re.search(r"\{.*?\}", cleaned, re.DOTALL)
        target_str = match.group(0) if match else cleaned

        # Fix leading zeros in numbers (e.g., 020 -> 20)
        target_str = re.sub(r"(?<=\s|:)\b0+(?=[1-9]\d*)\b", "", target_str)

        try:
            data = json.loads(target_str)
        except Exception:
            data = ast.literal_eval(target_str)

        if isinstance(data, dict):
            title = data.get("title")
            start_time = data.get("start_time")
            duration = data.get("clip_duration", data.get("duration", 15))

            if title and start_time:
                dur_int = int(duration)
                dur_int = max(12, min(45, dur_int))
                return {
                    "title": str(title),
                    "start_time": str(start_time),
                    "duration": dur_int,
                }, None

        return None, "Missing required keys 'title' or 'start_time'"
    except Exception as e:
        return None, f"Parsing error: {str(e)}"


def call_openrouter(
    grid_path,
    source_duration,
    insights,
    style_prompt,
    model_name,
    api_keys,
    timeout_sec=10,
):
    if not api_keys:
        return {"status": "failed", "error": "No OpenRouter API keys provided"}

    invoke_url = "https://openrouter.ai/api/v1/chat/completions"

    try:
        with open(grid_path, "rb") as f:
            base64_image = base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        return {"status": "failed", "error": f"Base64 encoding error: {str(e)}"}

    prompt_text = f"""Analyze the provided 9:16 gaming screenshot grid. Total video source duration is {source_duration} seconds.
Insights Context: {insights}
Style Directive: {style_prompt}

Find the most thrilling, high-action segment.
Return a JSON object with EXACTLY three keys:
1. 'title' (string: viral title with 1-3 emojis)
2. 'start_time' (string format HH:MM:SS)
3. 'clip_duration' (integer: length between 12 and 45 seconds)
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
        "max_tokens": 512,
        "temperature": 0.5,
    }

    last_error = ""
    for idx, api_key in enumerate(api_keys, 1):
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        try:
            print(
                f"🔑 Trying API Key #{idx} with model {model_name} (Max {timeout_sec}s)...",
                file=sys.stderr,
            )
            # STRICT HARD TIMEOUT AT 10 SECONDS
            response = requests.post(
                invoke_url, headers=headers, json=payload, timeout=timeout_sec
            )

            if response.status_code == 200:
                res_json = response.json()
                if "error" in res_json:
                    last_error = f"API Key #{idx} internal error: {res_json['error']}"
                    print(
                        f"⚠️ {last_error}. Trying next key...", file=sys.stderr
                    )
                    continue

                actual_model = res_json.get("model", model_name)
                choices = res_json.get("choices", [])
                if choices:
                    msg = choices[0].get("message", {})
                    raw_result = msg.get("content", "") or msg.get(
                        "reasoning", ""
                    )

                    if raw_result:
                        parsed_data, parse_err = parse_json_safely(raw_result)
                        if parsed_data:
                            return {
                                "status": "success",
                                "data": parsed_data,
                                "actual_model": actual_model,
                            }
                        else:
                            last_error = f"API Key #{idx} valid response but invalid JSON content: {parse_err}"
                            print(
                                f"⚠️ {last_error}. Trying next key...",
                                file=sys.stderr,
                            )
                            continue
                else:
                    last_error = f"API Key #{idx} 200 OK but missing 'choices'."
                    print(
                        f"⚠️ {last_error}. Trying next key...", file=sys.stderr
                    )
            else:
                last_error = f"API Key #{idx} Error {response.status_code}: {response.text[:100]}"
                print(f"⚠️ {last_error}. Trying next key...", file=sys.stderr)

        except requests.exceptions.Timeout:
            last_error = f"API Key #{idx} timed out after {timeout_sec} seconds"
            print(f"⏱️ {last_error}. Trying next key...", file=sys.stderr)
        except Exception as e:
            last_error = f"API Key #{idx} Exception: {str(e)}"
            print(f"⚠️ {last_error}. Trying next key...", file=sys.stderr)

    return {
        "status": "failed",
        "error": f"Failed for model {model_name}. Last error: {last_error}",
    }


def run_pipeline():
    grid_path = os.environ.get(
        "GRID_PATH", "temp_frames/merged_60_grid_screenshot.jpg"
    )
    source_duration = os.environ.get("SOURCE_DURATION", "60")
    insights = os.environ.get("INSIGHTS_SUMMARY", "")
    style_prompt = os.environ.get("STYLE_PROMPT", "")

    api_keys = []
    for i in range(1, 6):
        key_env_name = (
            "OPENROUTER_API_KEY" if i == 1 else f"OPENROUTER_API_KEY_{i}"
        )
        key_val = os.environ.get(key_env_name, "").strip()
        if key_val and key_val not in api_keys:
            api_keys.append(key_val)

    if not api_keys:
        print(
            json.dumps(
                {"status": "failed", "error": "No OpenRouter API keys found"}
            )
        )
        return

    # EXACT MODEL ID FIX WITH .strip()
    primary_model = os.environ.get(
        "OPENROUTER_MODEL",
        "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    ).strip()
    fallback_model = "openrouter/free"

    if not os.path.exists(grid_path):
        print(
            json.dumps(
                {"status": "failed", "error": "Grid image path not found"}
            )
        )
        return

    # STEP 1: Primary Model (1 Try | Strict 10s Limit)
    print(
        f"🔄 Primary Model Check: {primary_model} (1 Try | 10s Limit)...",
        file=sys.stderr,
    )
    result = call_openrouter(
        grid_path,
        source_duration,
        insights,
        style_prompt,
        primary_model,
        api_keys[:1],
        timeout_sec=10,
    )

    if result.get("status") == "success":
        data = result.get("data", {})
        print(
            json.dumps({
                "status": "success",
                "model": result.get("actual_model", primary_model),
                "title": data["title"],
                "start_time": data["start_time"],
                "duration": data["duration"],
            })
        )
        return

    # STEP 2: Instant Fallback to openrouter/free (10s Limit per Key)
    print(f"⚠️ Primary failed: {result.get('error')}", file=sys.stderr)
    print(f"🔄 Instant Switch -> Fallback: {fallback_model}", file=sys.stderr)

    fallback_result = call_openrouter(
        grid_path,
        source_duration,
        insights,
        style_prompt,
        fallback_model,
        api_keys,
        timeout_sec=10,
    )

    if fallback_result.get("status") == "success":
        data = fallback_result.get("data", {})
        print(
            json.dumps({
                "status": "success",
                "model": fallback_result.get("actual_model", fallback_model),
                "title": data["title"],
                "start_time": data["start_time"],
                "duration": data["duration"],
            })
        )
        return

    print(
        json.dumps({
            "status": "failed",
            "error": (
                "Both primary and fallback failed. Last error:"
                f" {fallback_result.get('error')}"
            ),
        })
    )


if __name__ == "__main__":
    run_pipeline()
