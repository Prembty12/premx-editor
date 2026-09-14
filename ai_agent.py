import os
import glob
import json
import random
import requests

GEMINI_KEYS = [
    os.environ.get("GEMINI_API_KEY_1"),
    os.environ.get("GEMINI_API_KEY_2"),
    os.environ.get("GEMINI_API_KEY_3"),
]

def get_active_key():
    valid = [k for k in GEMINI_KEYS if k]
    return random.choice(valid) if valid else os.environ.get("GEMINI_API_KEY_1")

def run_agent_brain():
    links_dir = "game_links_editor"
    archive_dir = "archived_links"
    memory_file = "logs/agent_memory.json"
    
    os.makedirs("logs", exist_ok=True)
    os.makedirs(archive_dir, exist_ok=True)
    
    memory = {
        "game_scores": {}, 
        "title_styles": {
            "curiosity": 10, 
            "aggressive": 10, 
            "question": 10, 
            "emoji_heavy": 10
        },
        "last_used_style": "curiosity",
        "last_played_game": ""
    }
    
    if os.path.exists(memory_file):
        try:
            with open(memory_file, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    memory.update(loaded)
        except:
            pass

    all_files = glob.glob(os.path.join(links_dir, "*.txt"))
    if not all_files:
        print(json.dumps({"error": "No files"}))
        return

    valid_game_files = []
    for f in all_files:
        with open(f, 'r', encoding='utf-8', errors='ignore') as file_obj:
            content = file_obj.read().strip()
        if not content:
            archive_path = os.path.join(archive_dir, os.path.basename(f))
            os.rename(f, archive_path)
        else:
            valid_game_files.append(f)

    if not valid_game_files:
        print(json.dumps({"error": "No valid links left in any file"}))
        return

    game_list = []
    file_mapping = {}
    for f in valid_game_files:
        g_name = os.path.basename(f).replace("_uploaded_links.txt", "").replace(".txt", "")
        game_list.append(g_name)
        file_mapping[g_name] = f

    last_game = memory.get("last_played_game", "")
    available_games = [g for g in game_list if g != last_game]
    if not available_games:
        available_games = game_list

    styles = memory.get("title_styles", {"curiosity": 10, "aggressive": 10, "question": 10, "emoji_heavy": 10})
    sorted_styles = sorted(styles.items(), key=lambda x: x[1])
    chosen_style = sorted_styles[0][0] if random.random() > 0.3 else random.choice(list(styles.keys()))

    api_key = get_active_key()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent?key={api_key}"
    
    prompt = f"""You are an advanced AI Social Media Manager and Gaming Content Agent.
Available games: {available_games}
Game Performance Scores: {memory.get('game_scores', {})}
Title Styles Performance: {styles}

Task: 
1. Pick ONE best game file from the available list to post today.
2. Use the target title style: '{chosen_style}'.

Respond ONLY in a strict JSON format with no extra text or markdown wrappers:
{{"chosen_game": "game_name_here", "chosen_style": "{chosen_style}", "reasoning": "short reason"}}"""

    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }

    chosen_game = random.choice(available_games)
    try:
        response = requests.post(url, json=payload, timeout=15)
        res_data = response.json()
        text_res = res_data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        text_res = text_res.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(text_res)
        if parsed.get("chosen_game") in file_mapping:
            chosen_game = parsed.get("chosen_game")
            chosen_style = parsed.get("chosen_style", chosen_style)
    except Exception:
        scores = memory.get("game_scores", {})
        if scores:
            filtered_scores = {k: v for k, v in scores.items() if k in available_games}
            if filtered_scores:
                chosen_game = max(filtered_scores, key=filtered_scores.get)

    target_file = file_mapping[chosen_game]
    
    memory["last_used_style"] = chosen_style
    memory["last_played_game"] = chosen_game
    with open(memory_file, 'w', encoding='utf-8') as f:
        json.dump(memory, f, indent=4)

    print(json.dumps({
        "target_file": target_file,
        "game_name": chosen_game,
        "chosen_style": chosen_style
    }))

if __name__ == "__main__":
    run_agent_brain()
