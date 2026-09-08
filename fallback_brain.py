import base64
import json
import os
import re
import sys
import requests


# --- BLOCK 1: HUGGING FACE VISION API (New Fallback Brain) ---
def try_huggingface(grid_path, prompt_text):
  try:
    print('🔄 Attempting analysis via Hugging Face Vision API...')
    
    # Hugging Face token environment variable se uthayenge
    hf_token = os.environ.get('HF_TOKEN', '')
    headers = {}
    if hf_token:
      headers['Authorization'] = f'Bearer {hf_token}'

    with open(grid_path, 'rb') as f:
      b64_image = base64.b64encode(f.read()).decode('utf-8')

    # Llama 3.2 Vision model endpoint
    api_url = 'https://api-inference.huggingface.co/models/meta-llama/Llama-3.2-11B-Vision-Instruct'

    payload = {
        'inputs': f'<|image|><|begin_of_text|>{prompt_text}',
        'parameters': {
            'max_new_tokens': 300,
            'return_full_text': False
        }
    }
    
    # Note: Hugging Face image payload formats can vary by model, 
    # alternative standard OpenAI-compatible chat endpoint can also be used if preferred:
    # Alternative HF Chat Endpoint: https://router.huggingface.co/v1/chat/completions
    
    resp = requests.post(
        api_url,
        json=payload,
        headers=headers,
        timeout=40,
    )
    
    print(f'🔍 Hugging Face Response Status: {resp.status_code}')
    print(f'🔍 Hugging Face Response Text: {resp.text[:200]}')

    if resp.status_code == 200 and resp.text:
      print('✅ Hugging Face Success!')
      # HF inference returns list or dict depending on the endpoint format
      res_data = resp.json()
      if isinstance(res_data, list) and len(res_data) > 0:
        return res_data[0].get('generated_text', '')
      elif isinstance(res_data, dict):
        return res_data.get('generated_text', str(res_data))
      return resp.text
      
  except Exception as e:
    print(f'⚠️ Hugging Face Error: {e}')
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

  # 1st: Try Hugging Face
  raw_result = try_huggingface(grid_path, prompt_text)

  # Final Output Parser
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
