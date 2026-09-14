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
    """Logs ko stderr me bhejne ke liye taaki stdout JSON ko disturb na kare"""
    sys.stderr.write(f"{msg}\n")


def get_active_key():
    valid = [k for k in GEMINI_KEYS if k]
    if not valid:
        raise ValueError("No valid Gemini API keys found.")
    return random.choice(valid)


def check_facebook_high_performance(game_list):
    if not FB_PAGE_ID or not FB_ACCESS_TOKEN:
        log("⚠️ WARNING: Facebook Page ID ya Access Token missing hai!")
        return None, ""

    try:
        log("🔄 Facebook Graph API se pichle 14 dino ka data fetch ho raha hai...")

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
            log(
                f"❌ ERROR: Facebook API fail ho gayi. "
                f"Status: {response.status_code}"
            )
            return None, ""

        data = response.json().get("data", [])

        log(
            f"✅ SUCCESS: Facebook se {len(data)} videos ka "
            f"data successfully fetch hua!"
        )

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

        log(
            f"📊 CHECK: Highest views pichle 14 dino mein "
            f"{highest_found} mile."
        )

        if winning_game:
            log(
                f"🔥 VIRAL MATCH: 7k+ cross ho gaya! "
                f"Game: {winning_game} ({best_views} views)"
            )
        else:
            log(
                "⏳ NO VIRAL MATCH: Kisi video ne 7k ka target cross "
                "nahi kiya ya game list se match nahi hua."
            )

        return winning_game, winning_title

    except Exception as e:
        log(f"❌ ERROR: Facebook data fetch karne me dikkat aayi: {e}")

    return None, ""


def run_agent_brain():

    links_dir = "game_links_editor"
    archive_dir = "archived_links"
    memory_file = "logs/agent_memory.json"

    os.makedirs("logs", exist_ok=True)
    os.makedirs(archive_dir, exist_ok=True)

    # ============================================================
    # DEFAULT MEMORY
    # ============================================================

    memory = {
        "game_scores": {},

        "title_styles": {
            "curiosity": 10,
            "aggressive": 10,
            "question": 10,
            "emoji_heavy": 10,
            "gaming_hype": 10,
            "clickbait": 10,
            "informative": 10,
            "epic_cinematic": 10,
            "funny_roast": 10,
            "secret_hidden": 10,
            "exposed": 10,
            "unbelievable": 10,
            "crazy": 10,
            "secret": 10,
            "shocking": 10
        },

        "last_used_style": "curiosity",
        "last_played_game": "",

        "streak_game": "",
        "streak_count": 0,

        # Winning title memory
        "winning_title_context": "",
        "winning_title_game": "",
        "winning_title_uses": 0
    }

    # ============================================================
    # LOAD MEMORY
    # ============================================================

    if os.path.exists(memory_file):
        try:
            with open(memory_file, "r", encoding="utf-8") as f:
                loaded = json.load(f)

                if isinstance(loaded, dict):
                    memory.update(loaded)

        except (json.JSONDecodeError, IOError):
            pass

    # ============================================================
    # OLD MEMORY SAFETY
    # ============================================================

    try:
        winning_title_uses = int(
            memory.get("winning_title_uses", 0)
        )
    except Exception:
        winning_title_uses = 0

    winning_title_context = memory.get(
        "winning_title_context",
        ""
    )

    winning_title_game = memory.get(
        "winning_title_game",
        ""
    )

    # ============================================================
    # FIND GAME FILES
    # ============================================================

    all_files = glob.glob(
        os.path.join(links_dir, "*.txt")
    )

    if not all_files:
        print(json.dumps({
            "error": "No files found"
        }))
        return

    valid_game_files = []

    for f in all_files:

        try:

            with open(
                f,
                "r",
                encoding="utf-8",
                errors="ignore"
            ) as file_obj:

                content = file_obj.read().strip()

            if not content:

                archive_path = os.path.join(
                    archive_dir,
                    os.path.basename(f)
                )

                os.rename(f, archive_path)

            else:

                valid_game_files.append(f)

        except IOError:
            continue

    if not valid_game_files:

        print(json.dumps({
            "error": "No valid links left in main folder"
        }))
        return

    # ============================================================
    # GAME LIST
    # ============================================================

    game_list = []
    file_mapping = {}

    for f in valid_game_files:

        g_name = (
            os.path.basename(f)
            .replace("_uploaded_links.txt", "")
            .replace(".txt", "")
        )

        game_list.append(g_name)
        file_mapping[g_name] = f

    game_list.sort()

    # ============================================================
    # FACEBOOK PERFORMANCE
    # ============================================================

    high_perf_game, winning_title = (
        check_facebook_high_performance(game_list)
    )

    current_streak_game = memory.get(
        "streak_game",
        ""
    )

    current_streak_count = memory.get(
        "streak_count",
        0
    )

    chosen_game = ""

    # ============================================================
    # WINNING TITLE SYSTEM
    #
    # MAXIMUM 3 POSTS FOR SAME WINNING GAME/TITLE
    # ============================================================

    # ------------------------------------------------------------
    # CASE 1:
    # Facebook found a HIGH PERFORMANCE game
    # ------------------------------------------------------------

    if high_perf_game and winning_title:

        # --------------------------------------------------------
        # If Facebook found a DIFFERENT winning game
        # start a fresh 3-use cycle.
        # --------------------------------------------------------

        if winning_title_game != high_perf_game:

            log(
                f"🆕 NEW WINNING GAME: {high_perf_game}"
            )

            winning_title_game = high_perf_game
            winning_title_context = winning_title
            winning_title_uses = 0

        # --------------------------------------------------------
        # Same winning game + under 3 uses
        # --------------------------------------------------------

        if (
            winning_title_game == high_perf_game
            and winning_title_uses < 3
        ):

            if current_streak_game == high_perf_game:
                current_streak_count += 1
            else:
                current_streak_game = high_perf_game
                current_streak_count = 1

            chosen_game = high_perf_game

            # Save latest winning title
            winning_title_context = winning_title
            winning_title_game = high_perf_game

            # IMPORTANT:
            # Count this post/use
            winning_title_uses += 1

            log(
                f"🔥 WINNING TITLE USE: "
                f"{winning_title_uses}/3"
            )

            log(
                f"🎮 Winning Game: {chosen_game}"
            )

        # --------------------------------------------------------
        # 3 USES COMPLETE
        # DO NOT GIVE OLD WINNING TITLE TO AI
        # DO NOT USE OLD WINNING GAME
        # --------------------------------------------------------

        else:

            log(
                "🛑 WINNING TITLE LIMIT REACHED: 3/3"
            )

            log(
                "🚫 Old winning title will NOT be sent to AI."
            )

            log(
                "🚫 Old winning game will NOT be selected."
            )

            # Clear title reference completely
            winning_title_context = ""

            # Keep exhausted winning game remembered
            # so same game cannot immediately restart cycle
            winning_title_game = high_perf_game
            winning_title_uses = 3

            memory["streak_game"] = ""
            memory["streak_count"] = 0

            # ----------------------------------------------------
            # Select NEW GAME
            # ----------------------------------------------------

            last_game = memory.get(
                "last_played_game",
                ""
            )

            # Prefer a game different from exhausted winning game
            candidate_games = [
                g for g in game_list
                if g != high_perf_game
            ]

            if candidate_games:

                if last_game in candidate_games:

                    last_index = candidate_games.index(
                        last_game
                    )

                    next_index = (
                        last_index + 1
                    ) % len(candidate_games)

                    chosen_game = candidate_games[
                        next_index
                    ]

                else:

                    chosen_game = candidate_games[0]

            else:

                # Only one game exists
                # Still use it, but old title remains blocked
                chosen_game = game_list[0]

            current_streak_game = ""
            current_streak_count = 0

            log(
                f"🆕 NEW GAME SELECTED: {chosen_game}"
            )

    # ============================================================
    # NO HIGH PERFORMANCE MATCH
    # ============================================================

    else:

        log(
            "ℹ️ No valid 7k+ winning match found."
        )

        # Old winning title must NOT automatically
        # remain available unless its cycle is still active.
        #
        # If already 3/3, keep it blocked.
        if winning_title_uses >= 3:

            winning_title_context = ""

            log(
                "🚫 Winning title already reached 3/3."
            )

        # --------------------------------------------------------
        # Normal next-game rotation
        # --------------------------------------------------------

        last_game = memory.get(
            "last_played_game",
            ""
        )

        # Don't select the exhausted winning game
        blocked_game = (
            winning_title_game
            if winning_title_uses >= 3
            else ""
        )

        candidate_games = [
            g for g in game_list
            if g != blocked_game
        ]

        if not candidate_games:
            candidate_games = game_list

        if last_game in candidate_games:

            last_index = candidate_games.index(
                last_game
            )

            next_index = (
                last_index + 1
            ) % len(candidate_games)

            chosen_game = candidate_games[
                next_index
            ]

        else:

            chosen_game = candidate_games[0]

        current_streak_game = ""
        current_streak_count = 0

    # ============================================================
    # SAVE STREAK
    # ============================================================

    if (
        high_perf_game
        and chosen_game == high_perf_game
        and winning_title_uses < 3
    ):

        memory["streak_game"] = chosen_game
        memory["streak_count"] = current_streak_count

    else:

        memory["streak_game"] = ""
        memory["streak_count"] = 0

    # ============================================================
    # SAVE WINNING TITLE MEMORY
    # ============================================================

    memory["winning_title_context"] = (
        winning_title_context
    )

    memory["winning_title_game"] = (
        winning_title_game
    )

    memory["winning_title_uses"] = (
        winning_title_uses
    )

    # ============================================================
    # TITLE STYLE
    # ============================================================

    styles = memory.get(
        "title_styles",
        {
            "curiosity": 10,
            "aggressive": 10,
            "question": 10,
            "emoji_heavy": 10
        }
    )

    chosen_style = random.choice(
        list(styles.keys())
    )

    # ============================================================
    # IMPORTANT:
    # AFTER 3 USES, WINNING TITLE = EMPTY
    # AI WILL NOT RECEIVE IT
    # ============================================================

    winning_context = ""

    if winning_title_uses < 3:

        winning_context = memory.get(
            "winning_title_context",
            ""
        )

    # ============================================================
    # BUILD OPTIONAL REFERENCE TEXT
    # ============================================================

    if winning_context:

        reference_text = (
            f'Reference Winning Title '
            f'(from recent high-performing video '
            f'with 7k+ views): "{winning_context}"'
        )

    else:

        reference_text = ""

        log(
            "🔒 AI REFERENCE: Winning title hidden."
        )

    # ============================================================
    # GEMINI
    # ============================================================

    try:

        api_key = get_active_key()

        url = (
            "https://generativelanguage.googleapis.com/"
            "v1beta/models/gemini-1.5-flash:"
            f"generateContent?key={api_key}"
        )

        prompt = f"""You are an advanced AI Social Media Manager and Gaming Content Agent.

Target Game for today: {chosen_game}

Title Styles Performance: {styles}

{reference_text}

Task:
1. Use the selected game: '{chosen_game}'.
2. Pick or generate a catchy title style inspired by the reference winning title context if available.
3. Choose the best title style from: {list(styles.keys())}.

Respond ONLY in a strict JSON format with no extra text or markdown wrappers:
{{"chosen_game": "{chosen_game}", "chosen_style": "style_here", "reasoning": "short reason"}}"""

        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": prompt
                        }
                    ]
                }
            ]
        }

        response = requests.post(
            url,
            json=payload,
            timeout=15
        )

        response.raise_for_status()

        res_data = response.json()

        candidates = res_data.get(
            "candidates",
            []
        )

        if (
            candidates
            and "content" in candidates[0]
        ):

            parts = candidates[0][
                "content"
            ].get(
                "parts",
                []
            )

            if parts:

                text_res = (
                    parts[0]
                    .get("text", "")
                    .replace("```json", "")
                    .replace("```", "")
                    .strip()
                )

                parsed = json.loads(
                    text_res
                )

                if (
                    parsed.get("chosen_style")
                    in styles
                ):

                    chosen_style = parsed.get(
                        "chosen_style"
                    )

    except Exception as e:

        log(
            f"⚠️ Gemini error: {e}"
        )

    # ============================================================
    # TARGET FILE
    # ============================================================

    target_file = file_mapping[
        chosen_game
    ]

    # ============================================================
    # FINAL MEMORY UPDATE
    # ============================================================

    memory["last_used_style"] = (
        chosen_style
    )

    memory["last_played_game"] = (
        chosen_game
    )

    try:

        with open(
            memory_file,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                memory,
                f,
                indent=4,
                ensure_ascii=False
            )

    except IOError as e:

        log(
            f"⚠️ Memory save error: {e}"
        )

    # ============================================================
    # FINAL OUTPUT
    # ============================================================

    print(
        json.dumps(
            {
                "target_file": target_file,
                "game_name": chosen_game,
                "chosen_style": chosen_style,
                "streak_count": memory.get(
                    "streak_count",
                    0
                ),
                "winning_title_uses": memory.get(
                    "winning_title_uses",
                    0
                ),
                "inspired_by_title": winning_context
            },
            ensure_ascii=False
        )
    )


if __name__ == "__main__":
    run_agent_brain()