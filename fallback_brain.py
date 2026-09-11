import ast
import base64
import json
import os
import re
import sys
import requests


def call_openrouter(grid_path, source_duration, insights, style_prompt, model_name, timeout_sec=45):
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        return {
            "status": "failed",
            "error": "OPENROUTER_API_KEY environment variable missing",
        }

    invoke_url = "https://openrouter.ai/api/v1/chat/completions"

    try:
        with open(grid_path, "rb") as f:
            base64_image = base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        return {"status": "failed", "error": f"OpenRouter base64 error: {str(e)}"}

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
        "max_tokens": 1024,
        "temperature": 0.6,
    }

    try:
        response = requests.post(
            invoke_url, headers=headers, json=payload, timeout=timeout_sec
        )
        
        if response.status_code == 200:
            try:
                res_json = response.json()
                if "error" in res_json:
                    return {
                        "status": "failed",
                        "error": f"OpenRouter API internal error: {res_json['error']}",
                    }
                
                # Get the actual routed model name returned by OpenRouter API response
                actual_routed_model = res_json.get("model", model_name)
                
                choices = res_json.get("choices", [])
                if choices:
                    msg = choices[0].get("message", {})
                    raw_result = msg.get("content", "")
                    if raw_result:
                        return {
                            "status": "success",
                            "raw": str(raw_result),
                            "routed_model": actual_routed_model
                        }
                
                return {
                    "status": "failed",
                    "error": f"OpenRouter 200 OK but missing 'choices'. Full response: {response.text}",
                }
            except json.JSONDecodeError:
                return {
                    "status": "failed",
                    "error": f"OpenRouter invalid JSON response: {response.text}",
                }
                
        return {
            "status": "failed",
            "error": f"OpenRouter Error {response.status_code}: {response.text}",
        }
    except requests.exceptions.Timeout:
        return {"status": "failed", "error": f"Request timed out after {timeout_sec} seconds"}
    except Exception as e:
        return {"status": "failed", "error": f"OpenRouter Exception: {str(e)}"}


def run_pipeline():
    grid_path = os.environ.get(
        "GRID_PATH", "temp_frames/merged_60_grid_screenshot.jpg"
    )
    source_duration = os.environ.get("SOURCE_DURATION", "60")
    insights = os.environ.get("INSIGHTS_SUMMARY", "")
    style_prompt = os.environ.get("STYLE_PROMPT", "")
    
    primary_model = os.environ.get("OPENROUTER_MODEL", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free")
    fallback_model = "openrouter/free"

    if not os.path.exists(grid_path):
        print(
            json.dumps({"status": "failed", "error": "Grid image path not found"})
        )
        return

    result = None
    final_routed_model = primary_model

    # Step 1: Try primary fixed model with strict 15-second timeout
    print(f"🔄 Trying Primary Model: {primary_model} (15s timeout)...", file=sys.stderr)
    result = call_openrouter(grid_path, source_duration, insights, style_prompt, primary_model, timeout_sec=15)

    # Step 2: If primary model fails or times out, fallback to openrouter/free
    if result.get("status") != "success":
        print(f"⚠️ Primary model failed/timed out: {result.get('error')}. Switching to fallback: {fallback_model}...", file=sys.stderr)
        result = call_openrouter(grid_path, source_duration, insights, style_prompt, fallback_model, timeout_sec=45)
        if result.get("status") == "success":
            final_routed_model = result.get("routed_model", fallback_model)
    else:
        final_routed_model = result.get("routed_model", primary_model)

    # If all models fail
    if not result or result.get("status") != "success":
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error": f"All models failed. Last error: {result.get('error') if result else 'Unknown'}",
                }
            )
        )
        return

    # Parse raw response safely with JSON + AST fallback
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
                        "model": final_routed_model,
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
