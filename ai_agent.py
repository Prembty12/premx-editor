import os
import glob
import json
import random
import requests
from datetime import datetime, timedelta

GEMINI_KEYS = [
    os.environ.get("GEMINI_API_KEY_1"),
    os.environ.get("GEMINI_API_KEY_2"),
    os.environ.get("GEMINI_API_KEY_3"),
]

FB_PAGE_ID = os.environ.get("FB_PAGE_ID")
FB_ACCESS_TOKEN = os.environ.get("FB_ACCESS_TOKEN")

def get_active_key():
    valid = [k for k in GEMINI_KEYS if k]
    if not valid:
        raise ValueError("No valid Gemini API keys found.")
    return random.choice(valid)

def check_facebook_high_performance(game_list):
    """Facebook se pichle 14 dino ke videos check karke best performing game aur winning title dhoondta hai"""
    if not FB_PAGE_ID or not FB_ACCESS_TOKEN:
        print("⚠️ WARNING: Facebook Page ID ya Access Token missing hai!")
        return None, ""
    
    try:
        print("🔄 Facebook Graph API se pichle 14 dino ka data fetch ho raha hai...")
        fourteen_days_ago = datetime.now() - timedelta(days=14)
        since_timestamp = int(fourteen_days_ago.timestamp())

        url = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/videos"
        params = {
            "fields": "title,description,views,created_time",
            "since": since_timestamp,
            "access_token": FB_ACCESS_TOKEN,
            "limit": 50
        }
        response = requests.get(url, params=params, timeout=15)
        
        if response.status_code != 200:
            print(f"❌ ERROR: Facebook API fail ho gayi. Status: {response.status_code}")
            return None, ""
            
        data = response.json().get("data", [])
        print(f"✅ SUCCESS: Facebook se {len(data)} videos ka data successfully fetch hua!")
        
        best_views = 7000
        winning_game = None
        winning_title = ""
        highest_found = 0

        for video in data:
            title = video.get("title", "")
            description = video.get("description", "")
            text = (title + " " + description).lower()
            views = video.get("views", 0)
            
            if views > highest_found:
                highest_found = views
            
            if views > best_views:
                for game in game_list:
                    if game.lower() in text:
                        best_views = views
                        winning_game = game
                        winning_title = title if title else description

        print(f"📊 CHECK: Highest views pichle 14 dino mein {highest_found} mile.")
        
        if winning_game:
            print(f"🔥 VIRAL MATCH: 7k+ cross ho gaya! Game: {winning_game} ({best_views} views)")
        else:
            print("⏳ NO VIRAL MATCH: Kisi video ne 7k ka target cross nahi kiya ya game list se match nahi hua.")

        return winning_game, winning_title
        
    except Exception as e:
        print(f"❌ ERROR: Facebook data fetch karne me dikkat aayi: {e}")
        
    return None, ""

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
        "last_played_game": "",
        "streak_game": "",
        "streak_count": 0,
        "winning_title_context": ""
    }
    
    if os.path.exists(memory_file):
        try:
            with open(memory_file, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    memory.update(loaded)
        except (json.JSONDecodeError, IOError):
            pass

    all_files = glob.glob(os.path.join(links_dir, "*.txt"))
    if not all_files:
        print(json.dumps({"error": "No files found"}))
        return

    valid_game_files = []
    for f in all_files:
        try:
            with open(f, 'r', encoding='utf-8', errors='ignore') as file_obj:
                content = file_obj.read().strip()
            if not content:
                archive_path = os.path.join(archive_dir, os.path.basename(f))
                os.rename(f, archive_path)
            else:
                valid_game_files.append(f)
        except IOError:
            continue

    if not valid_game_files:
        print(json.dumps({"error": "No valid links left in main folder"}))
        return

    game_list = []
    file_mapping = {}
    for f in valid_game_files:
        g_name = os.path.basename(f).replace("_uploaded_links.txt", "").replace(".txt", "")
        game_list.append(g_name)
        file_mapping[g_name] = f

    game_list.sort()

    # High performance check (Returns game name and winning title)
    high_perf_game, winning_title = check_facebook_high_performance(game_list)
    
    current_streak_game = memory.get("streak_game", "")
    current_streak_count = memory.get("streak_count", 0)

    chosen_game = ""

    if high_perf_game and current_streak_count < 3:
        if current_streak_game == high_perf_game:
            current_streak_count += 1
        else:
            current_streak_game = high_perf_game
            current_streak_count = 1
        chosen_game = high_perf_game
        memory["winning_title_context"] = winning_title
    else:
        memory["streak_game"] = ""
        memory["streak_count"] = 0
        memory["winning_title_context"] = ""
        
        # Round-Robin Rotation Fallback
        last_game = memory.get("last_played_game", "")
        if last_game in game_list:
            last_index = game_list.index(last_game)
            next_index = (last_index + 1) % len(game_list)
            chosen_game = game_list[next_index]
        else:
            chosen_game = game_list[0]

    memory["streak_game"] = chosen_game if high_perf_game and chosen_game == high_perf_game else ""
    memory["streak_count"] = current_streak_count if memory["streak_game"] else 0

    styles = memory.get("title_styles", {"curiosity": 10, "aggressive": 10, "question": 10, "emoji_heavy": 10})
    chosen_style = random.choice(list(styles.keys()))
    winning_context = memory.get("winning_title_context", "None")

    try:
        api_key = get_active_key()
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        
        prompt = f"""You are an advanced AI Social Media Manager and Gaming Content Agent.
Target Game for today: {chosen_game}
Title Styles Performance: {styles}
Reference Winning Title (from recent high-performing video with 7k+ views): "{winning_context}"

Task: 
1. Use the selected game: '{chosen_game}'.
2. Pick or generate a catchy title style inspired by the reference winning title context if available.
3. Choose the best title style from: {list(styles.keys())}.

Respond ONLY in a strict JSON format with no extra text or markdown wrappers:
{{"chosen_game": "{chosen_game}", "chosen_style": "style_here", "reasoning": "short reason"}}"""

        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }]
        }

        response = requests.post(url, json=payload, timeout=15)
        response.raise_for_status()
        res_data = response.json()
        
        candidates = res_data.get("candidates", [])
        if candidates and "content" in candidates[0]:
            parts = candidates[0]["content"].get("parts", [])
            if parts:
                text_res = parts[0].get("text", "").replace("```json", "").replace("```", "").strip()
                parsed = json.loads(text_res)
                if parsed.get("chosen_style") in styles:
                    chosen_style = parsed.get("chosen_style")
    except Exception:
        pass

    target_file = file_mapping[chosen_game]
    
    memory["last_used_style"] = chosen_style
    memory["last_played_game"] = chosen_game
    try:
        with open(memory_file, 'w', encoding='utf-8') as f:
            json.dump(memory, f, indent=4)
    except IOError:
        pass

    print(json.dumps({
        "target_file": target_file,
        "game_name": chosen_game,
        "chosen_style": chosen_style,
        "streak_count": memory.get("streak_count", 0),
        "inspired_by_title": winning_context
    }))

if __name__ == "__main__":
    run_agent_brain()
