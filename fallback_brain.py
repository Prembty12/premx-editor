import base64
import json
import os
import re
import requests


def run_nvidia_fallback():
  # Pipeline environment variables se values utha rahe hain
  grid_path = os.environ.get(
      'GRID_PATH', 'temp_frames/merged_60_grid_screenshot.jpg'
  )
  source_duration = os.environ.get('SOURCE_DURATION', '60')
  insights = os.environ.get('INSIGHTS_SUMMARY', '')
  style_prompt = os.environ.get('STYLE_PROMPT', '')

  # NVIDIA API Key (Only loaded securely from environment variables)
  api_key = os.environ.get('NVIDIA_API_KEY')

  if not api_key:
    print(
        json.dumps(
            {
                'status': 'failed',
                'error': 'NVIDIA_API_KEY environment variable is missing',
            }
        )
    )
    return

  if not os.path.exists(grid_path):
    print(
        json.dumps(
            {'status': 'failed', 'error': 'Grid image path not found'}
        )
    )
    return

  invoke_url = 'https://integrate.api.nvidia.com/v1/chat/completions'

  # 1. Image ko Base64 me Convert karein
  try:
    with open(grid_path, 'rb') as f:
      base64_image = base64.b64encode(f.read()).decode('utf-8')
  except Exception as e:
    print(
        json.dumps({
            'status': 'failed',
            'error': f'Base64 encode error: {str(e)}',
        })
    )
    return

  headers = {
      'Authorization': f'Bearer {api_key}',
      'Accept': 'application/json',
      'Content-Type': 'application/json',
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
      'model': 'nvidia/nemotron-3-nano-omni-30b-a3b-reasoning',
      'messages': [{
          'role': 'user',
          'content': [
              {'type': 'text', 'text': prompt_text},
              {
                  'type': 'image_url',
                  'image_url': {
                      'url': f'data:image/jpeg;base64,{base64_image}'
                  },
              },
          ],
      }],
      'max_tokens': 1024,
      'temperature': 0.6,
      'top_p': 0.95,
  }

  try:
    response = requests.post(invoke_url, headers=headers, json=payload, timeout=60)

    if response.status_code == 200:
      res_json = response.json()
      choices = res_json.get('choices', [])
      if choices:
        msg = choices[0].get('message', {})
        raw_result = msg.get('content', '') or msg.get('reasoning', '')

        # JSON Cleaning & Parsing
        cleaned = re.sub(r'```json', '', raw_result, flags=re.IGNORECASE)
        cleaned = re.sub(r'```', '', cleaned).strip()

        match = re.search(r'\{.*?\}', cleaned, re.DOTALL)
        if match:
          data = json.loads(match.group(0))
        else:
          data = json.loads(cleaned)

        title = data.get('title')
        start_time = data.get('start_time')
        duration = data.get('clip_duration', data.get('duration', 15))

        if title and start_time:
          dur_int = int(duration)
          if dur_int < 12:
            dur_int = 12
          print(
              json.dumps({
                  'status': 'success',
                  'title': title,
                  'start_time': start_time,
                  'duration': dur_int,
              })
          )
          return

    # Agar response 200 na ho ya keys miss ho jayein
    print(
        json.dumps({
            'status': 'failed',
            'error': f'API Error {response.status_code}: {response.text[:200]}',
        })
    )

  except Exception as e:
    print(json.dumps({'status': 'failed', 'error': str(e)}))


if __name__ == '__main__':
  run_nvidia_fallback()
