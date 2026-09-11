import ast
import base64
import json
import os
import re
import sys
import requests


def call_openrouter(grid_path, source_duration, insights, style_prompt, model_name="openrouter/free"):
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
            invoke_url, headers=headers, json=payload, timeout=45
        )
        if response.status_code == 200:
            res_json = response.json()
            choices = res_json.get("choices", [])
            if choices:
                msg = choices[0].get("message", {})
                raw_result = msg.get("content", "")
                if raw_result:
                    return {"status": "success", "raw": str(raw_result)}
        return {
            "status": "failed",
            "error": f"OpenRouter Error {response.status_code}: {response.text[:150]}",
        }
    except Exception as e:
        return {"status": "failed", "error": f"OpenRouter Exception: {str(e)}"}


def run_pipeline():
    grid_path = os.environ.get(
        "GRID_PATH", "temp_frames/merged_60_grid_screenshot.jpg"
    )
    source_duration = os.environ.get("SOURCE_DURATION", "60")
    insights = os.environ.get("INSIGHTS_SUMMARY", "")
    style_prompt = os.environ.get("STYLE_PROMPT", "")
    
    # Get model name from environment variable or fallback to default
    openrouter_model = os.environ.get("OPENROUTER_MODEL", "openrouter/free")

    if not os.path.exists(grid_path):
        print(
            json.dumps({"status": "failed", "error": "Grid image path not found"})
        )
        return

    # Call OpenRouter directly, showing the model name being used
    print(f"🔄 Calling OpenRouter API (Model: {openrouter_model})...", file=sys.stderr)
    result = call_openrouter(grid_path, source_duration, insights, style_prompt, openrouter_model)

    # If it fails
    if result.get("status") != "success":
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error": f"OpenRouter failed: {result.get('error')}",
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
            # Fallback for single-quoted strings or python-style dict outputs from LLMs
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
                        "model": openrouter_model,
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
