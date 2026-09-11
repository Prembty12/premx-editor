import ast
import base64
import json
import os
import re
import sys
import requests


def call_openrouter(grid_path, source_duration, insights, style_prompt, model_name, api_keys):
    if not api_keys:
        return {
            "status": "failed",
            "error": "No OpenRouter API keys provided",
        }

    invoke_url = "https://openrouter.ai/api/v1/chat/completions"

    try:
        with open(grid_path, "rb") as f:
            base64_image = base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        return {"status": "failed", "error": f"OpenRouter base64 error: {str(e)}"}

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
        "max_tokens": 1024,
        "temperature": 0.6,
    }

    # Try each API key one by one
    last_error = ""
    for idx, api_key in enumerate(api_keys, 1):
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        
        try:
            print(f"🔑 Trying API Key #{idx} with model {model_name}...", file=sys.stderr)
            response = requests.post(
                invoke_url, headers=headers, json=payload, timeout=45
            )
            
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
    grid_path = os.environ.get(
        "GRID_PATH", "temp_frames/merged_60_grid_screenshot.jpg"
    )
    source_duration = os.environ.get("SOURCE_DURATION", "60")
    insights = os.environ.get("INSIGHTS_SUMMARY", "")
    style_prompt = os.environ.get("STYLE_PROMPT", "")
    
    # Collect up to 5 API keys from environment variables
    api_keys = []
    for i in range(1, 6):
        key_env_name = "OPENROUTER_API_KEY" if i == 1 else f"OPENROUTER_API_KEY_{i}"
        key_val = os.environ.get(key_env_name, "").strip()
        if key_val and key_val not in api_keys:
            api_keys.append(key_val)

    if not api_keys:
        print(
            json.dumps({"status": "failed", "error": "No OpenRouter API keys found in environment variables (OPENROUTER_API_KEY to OPENROUTER_API_KEY_5)"})
        )
        return

    primary_model = os.environ.get("OPENROUTER_MODEL", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free")
    fallback_model = "openrouter/free"
    
    models_to_try = [primary_model]
    if fallback_model not in models_to_try:
        models_to_try.append(fallback_model)

    if not os.path.exists(grid_path):
        print(
            json.dumps({"status": "failed", "error": "Grid image path not found"})
        )
        return

    result = None
    used_model = primary_net = primary_model

    for model in models_to_try:
        print(f"🔄 Trying Model: {model} with available API keys...", file=sys.stderr)
        result = call_openrouter(grid_path, source_duration, insights, style_prompt, model, api_keys)
        if result.get("status") == "success":
            used_model = result.get("actual_model", model)
            break
        else:
            print(f"⚠️ Model {model} completely failed across all keys: {result.get('error')}", file=sys.stderr)

    if result.get("status") != "success":
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error": f"All models and API keys failed. Last error: {result.get('error')}",
                }
            )
        )
        return

    try:
        raw_result = result.get("raw", "")
        if not isinstance(raw_result, str):
            raw_result = str(raw_result)

        cleaned = re.sub(r"```json", "", raw_result, flags=re.IGNORECASE)
        cleaned = re.sub(r"```", "", cleaned).strip()

        match = re.search(r"\{.*?\}", cleaned, re.DOTALL)
        target_str = match.group(0) if match else cleaned

        try:
            data = json.loads(target_str)
        except json.JSONDecodeError:
            data = ast.literal_eval(target_str)

        title = data.get("title")
        start_time = data.get("start_time")
        duration = data.get("clip_duration", data.get("duration", 15))

        if title and start_time:
            dur_int = int(duration)
            if dur_int < 12:
                dur_int = 12
            elif dur_int > 45:
                dur_int = 45
            print(
                json.dumps(
                    {
                        "status": "success",
                        "model": used_model,
                        "title": title,
                        "start_time": start_time,
                        "duration": dur_int,
                    }
                )
            )
        else:
            print(
                json.dumps(
                    {
                        "status": "failed",
                        "error": "Missing title or start_time in JSON",
                    }
                )
            )

    except Exception as e:
        print(
            json.dumps(
                {"status": "failed", "error": f"Parsing error: {str(e)}"}
            )
        )


if __name__ == "__main__":
    run_pipeline()

