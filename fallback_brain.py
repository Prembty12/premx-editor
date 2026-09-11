import ast
import base64
import json
import os
import re
import sys
import time
import requests


def clean_and_parse_json(raw_str):
    """Sanitizes raw response to fix invalid JSON/Python literals (e.g. leading zeros like : 015)."""
    cleaned = re.sub(r"```json", "", raw_str, flags=re.IGNORECASE)
    cleaned = re.sub(r"```", "", cleaned).strip()

    match = re.search(r"\{.*?\}", cleaned, re.DOTALL)
    target_str = match.group(0) if match else cleaned

    # Fix: Leading zero integers (e.g. ": 015" -> ": 15", ": 00" -> ": 0")
    target_str = re.sub(r'(:\s*)0+([1-9]\d*)', r'\1\2', target_str)
    target_str = re.sub(r'(:\s*)0+(?=[,\}\n\r])', r'\1 0', target_str)

    try:
        return json.loads(target_str)
    except Exception:
        return ast.literal_eval(target_str)


def call_nvidia(grid_path, source_duration, insights, style_prompt, model_name, api_key):
    if not api_key:
        return {"status": "failed", "error": "No NVIDIA API key provided"}

    invoke_url = "https://integrate.api.nvidia.com/v1/chat/completions"

    valid_model = model_name.strip()
    if valid_model.startswith("vidia/"):
        valid_model = "n" + valid_model

    try:
        with open(grid_path, "rb") as f:
            base64_image = base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        return {"status": "failed", "error": f"NVIDIA base64 error: {str(e)}"}

    prompt_text = f"""Analyze the provided 9:16 gaming screenshot grid. Total video source duration is {source_duration} seconds.
Insights Context: {insights}
Style Directive: {style_prompt}

Your primary job as an expert video editor is to find the most thrilling, high-action segment, skipping dull introductions.
Return a valid JSON object with EXACTLY three keys:
1. "title" (string: viral title with 1-3 emojis)
2. "start_time" (string format "HH:MM:SS" indicating exact peak action start time)
3. "clip_duration" (integer: duration between 12 and 45 seconds without any leading zeros, e.g. 15 not 015)

Return ONLY standard raw JSON format."""

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    payload = {
        "model": valid_model,
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
        "max_tokens": 1024,
        "temperature": 0.2,
    }

    last_error = ""
    for attempt in range(1, 6):
        try:
            print(f"🔑 Trying NVIDIA API (Attempt #{attempt}) with model {valid_model}...", file=sys.stderr)
            response = requests.post(invoke_url, headers=headers, json=payload, timeout=60)

            if response.status_code == 200:
                res_json = response.json()
                choices = res_json.get("choices", [])
                if choices:
                    msg = choices[0].get("message", {})
                    raw_result = msg.get("content", "") or msg.get("reasoning", "")
                    if raw_result:
                        return {
                            "status": "success",
                            "raw": str(raw_result),
                            "actual_model": res_json.get("model", valid_model)
                        }
                last_error = "NVIDIA 200 OK but missing 'choices'."
            elif response.status_code in [429, 503, 504]:
                wait_time = attempt * 5
                last_error = f"NVIDIA Error {response.status_code}: {response.text[:100]}"
                print(f"⚠️ {last_error}. Retrying in {wait_time}s...", file=sys.stderr)
                time.sleep(wait_time)
            else:
                last_error = f"NVIDIA Error {response.status_code}: {response.text[:100]}"
                break
        except Exception as e:
            last_error = f"NVIDIA Exception: {str(e)}"
            time.sleep(attempt * 2)

    return {"status": "failed", "error": last_error}


def call_openrouter(grid_path, source_duration, insights, style_prompt, model_name, api_keys):
    if not api_keys:
        return {"status": "failed", "error": "No OpenRouter API keys provided"}

    invoke_url = "https://openrouter.ai/api/v1/chat/completions"

    try:
        with open(grid_path, "rb") as f:
            base64_image = base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        return {"status": "failed", "error": f"OpenRouter base64 error: {str(e)}"}

    prompt_text = f"""Analyze the provided 9:16 gaming screenshot grid. Total video source duration is {source_duration} seconds.
Insights Context: {insights}
Style Directive: {style_prompt}

Your primary job as an expert video editor is to find the most thrilling, high-action segment.
Return a JSON object with EXACTLY three keys:
1. 'title' (string: viral title with 1-3 emojis)
2. 'start_time' (string format HH:MM:SS)
3. 'clip_duration' (integer: length between 12 and 45 seconds)
Return ONLY valid JSON format."""

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
        "max_tokens": 1024,
        "temperature": 0.6,
    }

    last_error = ""
    for idx, api_key in enumerate(api_keys, 1):
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        
        try:
            print(f"🔑 Trying OpenRouter API Key #{idx} with model {model_name}...", file=sys.stderr)
            response = requests.post(invoke_url, headers=headers, json=payload, timeout=45)
            
            if response.status_code == 200:
                try:
                    res_json = response.json()
                    if "error" in res_json:
                        last_error = f"API Key #{idx} internal error: {res_json['error']}"
                        print(f"⚠️ {last_error}. Trying next key...", file=sys.stderr)
                        continue
                    
                    actual_model = res_json.get("model", model_name)
                    choices = res_json.get("choices", [])
                    if choices:
                        msg = choices[0].get("message", {})
                        raw_result = msg.get("content", "") or msg.get("reasoning", "")
                        if raw_result:
                            return {
                                "status": "success", 
                                "raw": str(raw_result), 
                                "actual_model": actual_model
                            }
                    
                    last_error = f"API Key #{idx} 200 OK but missing 'choices'."
                    print(f"⚠️ {last_error} Trying next key...", file=sys.stderr)
                except json.JSONDecodeError:
                    last_error = f"API Key #{idx} invalid JSON response: {response.text[:100]}"
                    print(f"⚠️ {last_error} Trying next key...", file=sys.stderr)
            else:
                last_error = f"API Key #{idx} Error {response.status_code}: {response.text[:100]}"
                print(f"⚠️ {last_error} Trying next key...", file=sys.stderr)
                
        except Exception as e:
            last_error = f"API Key #{idx} Exception: {str(e)}"
            print(f"⚠️ {last_error} Trying next key...", file=sys.stderr)

    return {"status": "failed", "error": f"All API keys failed. Last error: {last_error}"}


def run_pipeline():
    grid_path = os.environ.get("GRID_PATH", "temp_frames/merged_60_grid_screenshot.jpg")
    source_duration = os.environ.get("SOURCE_DURATION", "60")
    insights = os.environ.get("INSIGHTS_SUMMARY", "")
    style_prompt = os.environ.get("STYLE_PROMPT", "")
    
    api_keys = []
    for i in range(1, 6):
        key_env_name = "OPENROUTER_API_KEY" if i == 1 else f"OPENROUTER_API_KEY_{i}"
        key_val = os.environ.get(key_env_name, "").strip()
        if key_val and key_val not in api_keys:
            api_keys.append(key_val)

    nvidia_api_key = os.environ.get("NVIDIA_API_KEY", "").strip()
    nvidia_model = os.environ.get("NVIDIA_MODEL", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning")

    primary_model = os.environ.get("OPENROUTER_MODEL", "vidia/nemotron-3-nano-omni-30b-a3b-reasoning:free")
    fallback_model = "openrouter/free"

    if not os.path.exists(grid_path):
        print(json.dumps({"status": "failed", "error": f"Grid image path not found: {grid_path}"}))
        sys.exit(1)

    result = None
    used_model = primary_model

    # Phase 1: OpenRouter
    if api_keys:
        models_to_try = [primary_model]
        if fallback_model not in models_to_try:
            models_to_try.append(fallback_model)

        for model in models_to_try:
            print(f"🔄 Trying OpenRouter Model: {model}...", file=sys.stderr)
            result = call_openrouter(grid_path, source_duration, insights, style_prompt, model, api_keys)
            if result.get("status") == "success":
                used_model = result.get("actual_model", model)
                break

    # Phase 2: NVIDIA Fallback
    if (not result or result.get("status") != "success") and nvidia_api_key:
        print("🔄 Falling back to NVIDIA API direct endpoint...", file=sys.stderr)
        result = call_nvidia(grid_path, source_duration, insights, style_prompt, nvidia_model, nvidia_api_key)
        if result.get("status") == "success":
            used_model = result.get("actual_model", nvidia_model)

    if not result or result.get("status") != "success":
        last_err = result.get("error") if result else "No API keys configured"
        print(json.dumps({"status": "failed", "error": f"All providers failed. Last error: {last_err}"}))
        sys.exit(1)

    # Output Parsing & Formatting
    try:
        raw_result = result.get("raw", "")
        data = clean_and_parse_json(str(raw_result))

        title = data.get("title")
        start_time = data.get("start_time")
        duration = data.get("clip_duration", data.get("duration", 15))

        if title and start_time:
            dur_int = int(duration)
            dur_int = max(12, min(45, dur_int))

            output_payload = {
                "status": "success",
                "model": used_model,
                "title": title,
                "start_time": str(start_time),
                "duration": dur_int,
            }

            gh_output = os.environ.get("GITHUB_OUTPUT")
            if gh_output:
                with open(gh_output, "a") as f:
                    f.write(f"title={title}\n")
                    f.write(f"start_time={start_time}\n")
                    f.write(f"duration={dur_int}\n")

            print(json.dumps(output_payload))
        else:
            print(json.dumps({"status": "failed", "error": "Missing title or start_time in JSON output"}))
            sys.exit(1)

    except Exception as e:
        print(json.dumps({"status": "failed", "error": f"Parsing error: {str(e)}"}))
        sys.exit(1)


if __name__ == "__main__":
    run_pipeline()
    
