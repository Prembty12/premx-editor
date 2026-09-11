import base64
import json
import os
import re
import requests


def try_nvidia(grid_path, prompt_text):
  try:
    print('🔄 Attempting analysis via NVIDIA API...')
    api_key = os.environ.get('NVIDIA_API_KEY', '')
    if not api_key:
      print('⚠️ NVIDIA_API_KEY not found')
      return None

    headers = {
        'Authorization': f'Bearer {api_key}',
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    }

    with open(grid_path, 'rb') as f:
      b64_image = base64.b64encode(f.read()).decode('utf-8')

    payload = {
        'model': 'nvidia/nemotron-3-nano-omni-30b-a3b-reasoning',
        'messages': [{
            'role': 'user',
            'content': [
                {'type': 'text', 'text': prompt_text},
                {
                    'type': 'image_url',
                    'image_url': {
                        'url': f'data:image/jpeg;base64,{b64_image}'
                    }
                }
            ]
        }],
        'max_tokens': 1024
    }

    resp = requests.post(
        'https://integrate.api.nvidia.com/v1/chat/completions',
        json=payload,
        headers=headers,
        timeout=45,
    )
    print(f'🔍 NVIDIA Response Status: {resp.status_code}')

    if resp.status_code == 200 and resp.text:
      print('✅ NVIDIA Success!')
      res_data = resp.json()
      choices = res_data.get('choices', [])
      if choices:
        return choices[0].get('message', {}).get('content', '')
  except Exception as e:
    print(f'⚠️ NVIDIA Error: {e}')
  return None


def try_openrouter_fixed(grid_path, prompt_text):
  try:
    print('🔄 Attempting analysis via OpenRouter (Fixed Model)...')
    api_key = os.environ.get('OPENROUTER_API_KEY', '')
    if not api_key:
      print('⚠️ OPENROUTER_API_KEY not found')
      return None

    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
        'HTTP-Referer': 'https://github.com',
        'X-Title': 'Gaming Video Editor'
    }

    with open(grid_path, 'rb') as f:
      b64_image = base64.b64encode(f.read()).decode('utf-8')

    payload = {
        'model': 'liquid/lfm-2.5-2.6b:free',
        'messages': [{
            'role': 'user',
            'content': [
                {'type': 'text', 'text': prompt_text},
                {
                    'type': 'image_url',
                    'image_url': {
                        'url': f'data:image/jpeg;base64,{b64_image}'
                    }
                }
            ]
        }],
        'max_tokens': 300
    }

    resp = requests.post(
        'https://openrouter.ai/api/v1/chat/completions',
        json=payload,
        headers=headers,
        timeout=45,
    )
    print(f'🔍 OpenRouter Fixed Status: {resp.status_code}')

    if resp.status_code == 200 and resp.text:
      print('✅ OpenRouter Fixed Model Success!')
      res_data = resp.json()
      choices = res_data.get('choices', [])
      if choices:
        return choices[0].get('message', {}).get('content', '')
  except Exception as e:
    print(f'⚠️ OpenRouter Fixed Error: {e}')
  return None


def try_openrouter_free(grid_path, prompt_text):
  try:
    print('🔄 Attempting analysis via OpenRouter (openrouter/free)...')
    api_key = os.environ.get('OPENROUTER_API_KEY', '')
    if not api_key:
      print('⚠️ OPENROUTER_API_KEY not found')
      return None

    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
        'HTTP-Referer': 'https://github.com',
        'X-Title': 'Gaming Video Editor'
    }

    with open(grid_path, 'rb') as f:
      b64_image = base64.b64encode(f.read()).decode('utf-8')

    payload = {
        'model': 'openrouter/free',
        'messages': [{
            'role': 'user',
            'content': [
                {'type': 'text', 'text': prompt_text},
                {
                    'type': 'image_url',
                    'image_url': {
                        'url': f'data:image/jpeg;base64,{b64_image}'
                    }
                }
            ]
        }],
        'max_tokens': 300
    }

    resp = requests.post(
        'https://openrouter.ai/api/v1/chat/completions',
        json=payload,
        headers=headers,
        timeout=45,
    )
    print(f'🔍 OpenRouter Free Status: {resp.status_code}')

    if resp.status_code == 200 and resp.text:
      print('✅ OpenRouter Free Success!')
      res_data = resp.json()
      choices = res_data.get('choices', [])
      if choices:
        return choices[0].get('message', {}).get('content', '')
  except Exception as e:
    print(f'⚠️ OpenRouter Free Error: {e}')
  return None


if __name__ == '__main__':
  grid_path = os.environ.get(
      'GRID_PATH', 'temp_frames/merged_60_grid_screenshot.jpg'
  )
  source_duration = os.environ.get('SOURCE_DURATION', '60')
  insights = os.environ.get('INSIGHTS_SUMMARY', '')
  style_prompt = os.environ.get('STYLE_PROMPT', '')

  prompt_text = f"""Analyze the provided 9:16 gaming screenshot grid. Total video source duration is {source_duration} seconds.
Insights Context: {insights}
Style Directive: {style_prompt}

Your primary job as an expert video editor is to find the most thrilling, high-action segment, skipping dull introductions.
Return a JSON object with EXACTLY three keys:
1. 'title' (string: viral title with 1-3 emojis)
2. 'start_time' (string format HH:MM:SS indicating exact peak action start time based on grid timestamps)
3. 'clip_duration' (integer: length between 12 and 45 seconds meeting monetization rules)
Return ONLY valid JSON format, no markdown wrapping."""

  raw_result = None

  # Tier 1: NVIDIA API
  raw_result = try_nvidia(grid_path, prompt_text)

  # Tier 2: OpenRouter Fixed Model
  if not raw_result:
    raw_result = try_openrouter_fixed(grid_path, prompt_text)

  # Tier 3: OpenRouter Free Route
  if not raw_result:
    raw_result = try_openrouter_free(grid_path, prompt_text)

  if raw_result:
    cleaned = re.sub(r'```json', '', raw_result, flags=re.IGNORECASE)
    cleaned = re.sub(r'```', '', cleaned).strip()
    try:
      match = re.search(r'\{.*?\}', cleaned, re.DOTALL)
      if match:
        data = json.loads(match.group(0))
      else:
        data = json.loads(cleaned)

      title = data.get('title')
      start_time = data.get('start_time')
      duration = data.get('duration', data.get('clip_duration', 15))

      if title and start_time:
        print(
            json.dumps({
                'status': 'success',
                'title': title,
                'start_time': start_time,
                'duration': int(duration),
            })
        )
      else:
        print(json.dumps({'status': 'failed', 'error': 'Missing keys in JSON'}))
    except Exception as e:
      print(json.dumps({'status': 'failed', 'error': str(e)}))
  else:
    print(json.dumps({'status': 'failed', 'error': 'All fallback blocks failed'}))
