import os
import glob
import json
import random
import requests
import sys
from datetime import datetime, timedelta

GEMINI_KEYS = [
    os.environ.get("GEMINI_API_KEY_1"),
    os.environ.get("GEMINI_API_KEY_2"),
    os.environ.get("GEMINI_API_KEY_3"),
]

FB_PAGE_ID = os.environ.get("PAGE_ID")
FB_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")

def log(msg):
    sys.stderr.write(f"{msg}\n")

def get_active_key():
    valid = [k for k in GEMINI_KEYS if k]
    if not valid:
        raise ValueError("No valid Gemini API keys found.")
    return random.choice(valid)

def fetch_and_calculate_scores(game_list, memory):
    """Facebook API se data fetch karke naye 7k+ viral hits ko track karega aur highest views terminal par dikhayega"""
    if not FB_PAGE_ID or not FB_ACCESS_TOKEN:
        log("⚠️ WARNING: Facebook Page ID ya Access Token missing hai!")
        return None, "", "", memory
    
    try:
        log("🔄 Facebook Graph API se pichle 28 dino ka data fetch ho raha hai...")
        twenty_eight_days_ago = datetime.now() - timedelta(days=28)
        since_timestamp = int(twenty_eight_days_ago.timestamp())

        url = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/videos"
        params = {
            "fields": "id,title,description,views,created_time",
            "since": since_timestamp,
            "access_token": FB_ACCESS_TOKEN,
            "limit": 100
        }
        response = requests.get(url, params=params, timeout=15)
        
        if response.status_code != 200:
            log(f"❌ ERROR: Facebook API fail ho gayi. Status: {response.status_code}")
            return None, "", "", memory
            
        data = response.json().get("data", [])
        log(f"✅ SUCCESS: Facebook se {len(data)} videos ka data successfully fetch hua!")
        
        processed_viral_ids = memory.get("processed_viral_ids", [])
        game_scores = memory.get("game_scores", {})
        title_styles = memory.get("title_styles", {})
        style_history = memory.get("style_history", {})
        
        best_views = 7000
        winning_game = None
        winning_title = ""
        winning_video_id = ""
        highest_found = 0
        highest_video_title = "" # Highest view wali video ka title track karne ke liye

        temp_game_views = {g: 0 for g in game_list}
        temp_game_counts = {g: 0 for g in game_list}
        temp_viral_counts = {g: 0 for g in game_list}

        style_total_views = {s: 0 for s in title_styles}
        style_counts = {s: 0 for s in title_styles}
        style_viral_hits = {s: 0 for s in title_styles}
        
        for video in data:
            video_id = video.get("id", "")
            title = video.get("title", "")
            description = video.get("description", "")
            text = (title + " " + description).lower()
            views = video.get("views", 0)
            
            # 🏆 Track Highest Views in Last 28 Days
            if views > highest_found:
                highest_found = views
                highest_video_title = title if title else description
            
            # Style performance tracking
            used_style = style_history.get(video_id)
            if used_style in title_styles:
                style_total_views[used_style] += views
                style_counts[used_style] += 1
                if views >= 7000:
                    style_viral_hits[used_style] += 1

            # Game matching
            for game in game_list:
                if game.lower() in text:
                    temp_game_views[game] += views
                    temp_game_counts[game] += 1
                    
                    if views >= 7000:
                        temp_viral_counts[game] += 1
                    
                    # Check if 7k+ and not blacklisted
                    if views >= 7000 and video_id not in processed_viral_ids:
                        if views > best_views or winning_game is None:
                            best_views = views
                            winning_game = game
                            winning_title = title if title else description
                            winning_video_id = video_id

        # 📊 Game Scores Update
        for game in game_list:
            total_v = temp_game_views[game]
            count_v = temp_game_counts[game]
            viral_c = temp_viral_counts[game]
            if count_v > 0:
                avg_v = total_v / count_v
                calculated_score = int(10 + (avg_v / 500) + (viral_c * 25))
            else:
                calculated_score = 10
            game_scores[game] = max(10, calculated_score)

        # 📊 Title Styles Scores Update
        for style in title_styles:
            s_views = style_total_views[style]
            s_count = style_counts[style]
            s_viral = style_viral_hits[style]
            if s_count > 0:
                s_avg = s_views / s_count
                style_score = int(10 + (s_avg / 500) + (s_viral * 20))
            else:
                style_score = title_styles.get(style, 10)
            title_styles[style] = max(10, style_score)

        memory["game_scores"] = game_scores
        memory["title_styles"] = title_styles

        # 🖥️ Terminal par saaf-saaf Highest Views dikhao
        log(f"🔥 [PERFORMANCE REPORT] Pichle 28 dino mein sabse zyada views: {highest_found} views")
        if highest_video_title:
            log(f"📌 Top Video Title: \"{highest_video_title[:60]}...\"")

        if winning_game:
            log(f"🚀 NAYA UNPROCESSED VIRAL MATCH MIL GAYA: Game: {winning_game}, Video ID: {winning_video_id} ({best_views} views)")
        else:
            log("⏳ Naya koi 7k+ unprocessed video nahi mila. Normal rotation chalegi.")

        return winning_game, winning_title, winning_video_id, memory
        
    except Exception as e:
        log(f"❌ ERROR: Facebook data fetch karne me dikkat aayi: {e}")
        
    return None, "", "", memory

def run_agent_brain():
    links_dir = "game_links_editor"
    archive_dir = "archived_links"
    memory_file = "logs/agent_memory.json"
    
    os.makedirs("logs", exist_ok=True)
    os.makedirs(archive_dir, exist_ok=True)
    
    memory = {
        "game_scores": {}, 
        "title_styles": {
            "curiosity": 10, "aggressive": 10, "question": 10, "emoji_heavy": 10,
            "gaming_hype": 10, "clickbait": 10, "informative": 10, "epic_cinematic": 10,
            "funny_roast": 10, "secret_hidden": 10, "exposed": 10, "unbelievable": 10,
            "crazy": 10, "secret": 10, "shocking": 10
        },
        "last_used_style": "curiosity",
        "last_played_game": "",
        "streak_game": "",
        "streak_count": 0,
        "winning_title_context": "",
        "winning_video_id": "",
        "processed_viral_ids": [],
        "style_history": {}
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

    # Data fetch & score calculations
    high_perf_game, winning_title, current_video_id, memory = fetch_and_calculate_scores(game_list, memory)
    
    processed_viral_ids = memory.get("processed_viral_ids", [])
    
    # 🛑 4TH TIME SKIP CHECK
    if current_video_id and current_video_id in processed_viral_ids:
        log(f"🛑 SKIP NOTICE: Video ID '{current_video_id}' pehle hi 3 reels/posts ki limit poori kar chuka hai (Blacklisted). 4th time ke liye skip kiya ja raha hai!")
        high_perf_game = None
        winning_title = ""
        current_video_id = ""

    stored_video_id = memory.get("winning_video_id", "")
    current_streak_count = memory.get("streak_count", 0)

    chosen_game = ""

    if high_perf_game and current_video_id:
        if current_video_id != stored_video_id:
            current_streak_count = 1
            memory["winning_video_id"] = current_video_id
            memory["winning_title_context"] = winning_title
            memory["streak_game"] = high_perf_game
            memory["streak_count"] = current_streak_count
            chosen_game = high_perf_game
            log(f"🚀 STREAK START (Post 1/3): Game -> {chosen_game}")
        elif current_streak_count < 3:
            current_streak_count += 1
            memory["streak_count"] = current_streak_count
            chosen_game = high_perf_game
            log(f"📈 STREAK RUNNING (Post {current_streak_count}/3): Game -> {chosen_game}")
            
            if current_streak_count >= 3:
                if current_video_id not in processed_viral_ids:
                    processed_viral_ids.append(current_video_id)
                memory["processed_viral_ids"] = processed_viral_ids
                log(f"🔒 STREAK COMPLETED (3/3): Video ID '{current_video_id}' ab permanently blacklist ho gayi hai.")
        else:
            memory["streak_game"] = ""
            memory["streak_count"] = 0
            memory["winning_title_context"] = ""
            memory["winning_video_id"] = ""
            
            last_game = memory.get("last_played_game", "")
            if last_game in game_list:
                last_index = game_list.index(last_game)
                next_index = (last_index + 1) % len(game_list)
                chosen_game = game_list[next_index]
            else:
                chosen_game = game_list[0]
            log(f"🔄 NORMAL ROTATION (Streak Over): Agla game select hua -> {chosen_game}")
    else:
        memory["streak_game"] = ""
        memory["streak_count"] = 0
        
        last_game = memory.get("last_played_game", "")
        if last_game in game_list:
            last_index = game_list.index(last_game)
            next_index = (last_index + 1) % len(game_list)
            chosen_game = game_list[next_index]
        else:
            chosen_game = game_list[0]
        log(f"🔄 NORMAL ROTATION: Agla game select hua -> {chosen_game}")

    winning_context = memory.get("winning_title_context", "None")
    styles = memory.get("title_styles", {})
    
    style_names = list(styles.keys())
    style_weights = list(styles.values())
    chosen_style = random.choices(style_names, weights=style_weights, k=1)[0]

    try:
        api_key = get_active_key()
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        
        prompt = f"""You are an advanced AI Social Media Manager and Gaming Content Agent specializing in viral gaming reels.
Target Game for today: {chosen_game}
Title Styles Performance Scores: {styles}
Reference Winning Title: "{winning_context}"
Selected Style for this Reel: {chosen_style}

Task: 
1. Use the selected game: '{chosen_game}'.
2. Generate a compelling title strictly following the selected style.
3. Ensure the title is punchy and fully optimized for Facebook Reels.

Respond ONLY in a strict JSON format with no extra text or markdown wrappers:
{{"chosen_game": "{chosen_game}", "chosen_style": "{chosen_style}", "reasoning": "short reason"}}"""

        payload = {
            "contents": [{
                "parts": [{
                    "text": prompt
                }]
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
        "inspired_by_title": winning_context,
        "tracked_video_id": memory.get("winning_video_id", "")
    }))

if __name__ == "__main__":
    run_agent_brain()
