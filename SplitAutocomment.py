"""
💬 SPLIT AUTO-COMMENT SCRIPT (FULL FINAL)
===========================================
✅ FB auto-reply working
✅ Real username fetch
✅ 3-level conversation thread
✅ 10 comments batch (OpenRouter)
✅ Duplicate protection via FB live check
✅ Auto-save logs
✅ Dashboard update (GAMING_DASHBOARD.md)
✅ Memory + Trending + Best-Time analysis
"""

import os
import re
import json
import time
import sys
import glob
import requests
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from zoneinfo import ZoneInfo
    IST = ZoneInfo("Asia/Kolkata")
except Exception:
    IST = timezone(timedelta(hours=5, minutes=30))


# ============================================================
# HELPERS
# ============================================================
def log(msg):
    sys.stderr.write(f"{msg}\n")
    sys.stderr.flush()


def now_ist():
    return datetime.now(IST)


def now_ist_ampm():
    return datetime.now(IST).strftime("%Y-%m-%d %I:%M:%S %p")


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

KNOWN_GAMES = [
    "BGMI", "Free Fire", "GTA 5", "GTA San Andreas", "GTA", "CODM",
    "Call of Duty", "God of War", "Spider-Man", "Minecraft", "PUBG",
    "Fortnite", "Valorant", "Clash of Clans", "Clash Royale", "Roblox",
    "Among Us", "Apex Legends", "FIFA", "PES", "WWE", "Naruto",
    "Dragon Ball", "Tekken", "Mortal Kombat", "Resident Evil",
    "Black Ops 6", "Black Ops", "Modern Warfare", "Warzone", "MW3",
    "God of War Ragnarok", "Spider-Man 2", "Ghost of Tsushima",
    "Red Dead Redemption", "Elden Ring", "Dark Souls", "Sekiro",
    "Cyberpunk 2077", "Assassin's Creed", "Far Cry", "Battlefield",
    "Need for Speed", "Forza", "Gran Turismo", "Halo", "Gears of War",
    "Subway Surfers", "Candy Crush", "Temple Run", "Clash",
    "VietnamCavePrison", "combatoperation", "ghostandela", "mm2remastered",
    "monkeyKing", "sifu", "codBlackops6", "SpiderMan2", "godofwar3",
    "afghanistanredz", "spider",
]


# ============================================================
# 🚫 ABUSE / SPAM DETECTION
# ============================================================
ABUSE_PATTERNS = [
    r'\b(madarchod|madrchod|bhosd|bhosdi|bhosdike|chutiya|chutya|chutiye|gaand|gandu|gaandu|harami|haramkhor|haramzada|kutta|kutte|kutiya|suar|saala|sala|bkl|mc|bc|bkc|lund|lauda|lavda|randi|rand)\b',
    r'\b(fuck|f\*ck|fuk|shit|sh\*t|bitch|bastard|asshole|dick|pussy|cunt|whore|slut)\b',
    r'(मादरचोद|भोसड़ी|भोसड़ीके|चूतिया|चूतिये|गांड|गांडू|हरामी|हरामखोर|कुत्ता|कुत्ते|कुतिया|सुअर|साला|भड़वे|लंड|लौड़ा|रंडी)',
    r'\b(thevdiya|punda|otha|sunni|lanja|pooka|baadu|koothi)\b',
]

FAMILY_ABUSE_PATTERNS = [
    r'\b(teri maa|teri behen|tere baap|teri ma|teri behan|teri biwi|teri beti)\b',
    r'(तेरी मां|तेरी माँ|तेरी बहन|तेरे बाप|तेरी बीवी|तेरी बेटी)',
]


def detect_abuse(text):
    tl = text.lower()
    for p in FAMILY_ABUSE_PATTERNS:
        if re.search(p, tl, re.IGNORECASE):
            return "family_abuse"
    for p in ABUSE_PATTERNS:
        if re.search(p, tl, re.IGNORECASE):
            return "general_abuse"
    return "none"


def is_spam(text):
    tl = text.lower()
    indicators = ["http://", "https://", ".com", ".xyz", "click here",
                  "follow me", "dm me", "join my", "subscribe my"]
    return any(i in tl for i in indicators)


def is_reply_safe(reply_text, is_abuse=False):
    if not reply_text or len(reply_text.strip()) < 3:
        return False, "too_short"
    if len(reply_text) > 400:
        return False, "too_long"
    rl = reply_text.lower()
    if "http" in rl or ".com" in rl:
        return False, "contains_link"
    for p in ABUSE_PATTERNS:
        if re.search(p, rl, re.IGNORECASE):
            return False, "reply_contains_abuse"
    return True, "safe"


# ============================================================
# 🤖 OPENROUTER CLIENT
# ============================================================
class OpenRouterClient:
    def __init__(self, keys, fixed_model="dots-studio/dots-3-note-preview:free",
                 fallback_model="openrouter/free", max_retries=12):
        self.keys = [k for k in keys if k]
        self.fixed_model = fixed_model
        self.fallback_model = fallback_model
        self.max_retries = max_retries

    def _call_single(self, model, api_key, prompt, max_tokens=150):
        if not api_key:
            return None
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/",
            "X-Title": "Gaming Auto-Agent",
        }
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.9,
            "max_tokens": max_tokens,
            "top_p": 0.95,
        }
        try:
            res = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=40)
            if res.status_code == 200:
                data = res.json()
                choices = data.get("choices", [])
                if choices:
                    c = choices[0].get("message", {}).get("content", "")
                    if c:
                        return c.strip()
            else:
                log(f"   ⚠️ HTTP {res.status_code}: {res.text[:120]}")
        except Exception as e:
            log(f"   ⚠️ Exception: {e}")
        return None

    @staticmethod
    def _extract_json(response):
        if not response:
            return None
        cleaned = response.strip()
        if "```" in cleaned:
            cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
            cleaned = re.sub(r'\s*```$', '', cleaned).strip()
        try:
            r = json.loads(cleaned)
            if isinstance(r, dict):
                return r
        except Exception:
            pass
        s, e = cleaned.find("{"), cleaned.rfind("}")
        if s != -1 and e != -1 and e > s:
            try:
                r = json.loads(cleaned[s:e + 1])
                if isinstance(r, dict):
                    return r
            except Exception:
                pass
        m = re.search(r'\{[\s\S]*\}', cleaned)
        if m:
            try:
                r = json.loads(m.group())
                if isinstance(r, dict):
                    return r
            except Exception:
                pass
        return None

    def generate_batch_replies(self, comments_batch):
        if not comments_batch:
            return {}
        if not self.keys:
            log("❌ No OpenRouter API keys found.")
            return {}

        formatted = ""
        for c in comments_batch:
            tone = "SAVAGE-HATER" if c["is_abuse"] else "FRIENDLY-FAN"
            safe_text = c["comment_text"].replace('"', "'").replace("\n", " ")[:300]
            caption_safe = c.get("post_title", "").replace('"', "'").replace("\n", " ")[:150]
            hashtags_safe = ", ".join(c.get("post_hashtags", []))[:100]

            thread_ctx = c.get("thread_context", "")
            context_line = ""
            if thread_ctx:
                context_line = f'Conversation So Far:\n{thread_ctx}\n'

            formatted += (
                f'[{tone}] ID: "{c["comment_id"]}" | '
                f'Game: "{c["game_name"]}" | '
                f'Hashtags: [{hashtags_safe}] | '
                f'Caption: "{caption_safe}" | '
                f'{context_line}'
                f'Comment: "{safe_text}"\n'
            )

        prompt = f"""You are a SAVAGE, WITTY, and CONFIDENT gaming content creator replying to comments on your gaming channel.

For EACH comment below, write a SHORT reply (maximum 25 words).

REPLY STYLE GUIDE:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FRIENDLY-FAN comments -> Friendly, warm, FUNNY, gaming-community tone.
   - Make them laugh, feel welcomed, and want to comment again.
   - Sometimes end with a playful question to boost engagement.
   - Hype them up like a close friend.

SAVAGE-HATER comments (abuse/insult) -> SAVAGE, WITTY, SARCASTIC comeback.
   - Match their energy but STAY CHILL and CONFIDENT.
   - Roast them with HUMOR, never with abuse.
   - Make it FUNNY, not angry.

If a "Conversation So Far" section exists:
   - Read prior context, DON'T repeat earlier reply.
   - Continue the conversation naturally.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STRICT RULES:
1. DETECT language of each comment and REPLY IN THE SAME LANGUAGE.
2. DO NOT use regional Indian languages (Tamil, Telugu, Bengali, etc.). Reply in ENGLISH or HINGLISH only.
3. GAME NAME RULE:
   - IF the comment ASKS about the game name ("Which game?", "Game name?", "What game is this?"), THEN mention the game name.
   - IF NOT asked, DO NOT mention the game name.
   - Use Caption and Hashtags as context.
4. Include 1-2 emojis per reply.
5. NEVER share links.
6. NEVER insult family, religion, or caste.
7. NEVER use abusive words back.
8. MAX 25 words per reply.
9. HOOK THEM BACK: Sometimes end with a playful question.

CRITICAL OUTPUT REQUIREMENT:
- You MUST return ONLY valid JSON.
- Keys = EXACT comment IDs.
- Values = reply text.
- NO extra text, NO markdown, NO explanation, NO "User Safety", ONLY JSON.

Example format:
{{
  "COMMENT_ID_1": "reply text 1",
  "COMMENT_ID_2": "reply text 2"
}}

COMMENTS TO REPLY:
{formatted}

YOUR JSON RESPONSE:"""

        for attempt in range(1, self.max_retries + 1):
            key_index = (attempt - 1) % len(self.keys)
            current_key = self.keys[key_index]
            model_to_use = self.fixed_model if attempt == 1 else self.fallback_model
            tag = "FIXED" if attempt == 1 else "FALLBACK"
            log(f"🔄 Attempt {attempt}/{self.max_retries} | {tag} | Key {key_index + 1}")

            response = self._call_single(model_to_use, current_key, prompt, max_tokens=1800)
            if not response:
                log("   ⚠️ Empty response — retry")
                time.sleep(1)
                continue

            if response.strip().lower() in ["user safety: safe", "safe", "unsafe", "none"]:
                log("   ⚠️ Safety model response — retry")
                time.sleep(1)
                continue

            parsed = self._extract_json(response)
            if parsed is None:
                log(f"   ⚠️ Invalid JSON — retry. Preview: {response[:100]}")
                time.sleep(1)
                continue

            result = {}
            for c in comments_batch:
                cid = c["comment_id"]
                if cid in parsed:
                    reply = str(parsed[cid]).strip().strip('"').strip("'")
                    if reply and reply.lower() not in ["user safety: safe", "safe", "unsafe", "none"]:
                        result[cid] = reply

            if result:
                log(f"   ✅ Valid JSON on attempt {attempt}: {len(result)}/{len(comments_batch)} replies")
                return result
            log("   ⚠️ Parsed but no valid replies — retry")
            time.sleep(1)

        log(f"❌ Failed to get valid JSON after {self.max_retries} attempts.")
        return {}


# ============================================================
# 📁 FILE DISCOVERY + MEMORY (dashboard ke liye)
# ============================================================
def discover_game_files(links_dir="game_links_editor"):
    if not os.path.exists(links_dir):
        return [], {}
    files = glob.glob(os.path.join(links_dir, "*.txt"))
    files = [f for f in files
             if any(k in f for k in ("_uploaded_links", "_links_editor", "_posted_links"))]
    files = [f for f in files if os.path.exists(f)]

    game_list, file_mapping = [], {}
    for f in files:
        g = (os.path.basename(f)
             .replace("_uploaded_links.txt", "")
             .replace("_links_editor.txt", "")
             .replace("_posted_links_editor.txt", "")
             .replace(".txt", "").strip())
        if g:
            file_mapping[g] = f
            game_list.append(g)
    return sorted(set(game_list)), file_mapping


def load_memory(path="logs/agent_memory.json"):
    mem = {
        "game_stats": {},
        "actual_posted_titles": {},
        "last_played_game": "",
        "last_used_style": "curiosity",
        "title_styles": {
            "curiosity": 10, "aggressive": 10, "question": 10, "emoji_heavy": 10,
            "gaming_hype": 10, "clickbait": 10, "informative": 10, "epic_cinematic": 10,
            "funny_roast": 10, "secret_hidden": 10, "exposed": 10, "unbelievable": 10,
            "crazy": 10, "secret": 10, "shocking": 15,
        },
    }
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    mem.update(loaded)
        except Exception:
            pass
    return mem


def save_memory(mem, path="logs/agent_memory.json"):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(mem, f, indent=4)
    except Exception as e:
        log(f"⚠️ memory save error: {e}")


# ============================================================
# 💬 FB AUTO-COMMENTER
# ============================================================
class FBAutoCommenter:
    def __init__(self,
                 fb_page_id,
                 fb_access_token,
                 openrouter_keys,
                 auto_comment_enabled=True,
                 fb_api_version="v24.0",
                 days_limit=28,
                 max_replies_per_run=10,
                 max_conversation_depth=3,
                 min_comment_age_min=0,
                 max_comment_age_hours=720,
                 posts_to_scan=25,
                 comment_fetch_workers=10,
                 max_json_retries=12,
                 replied_file="logs/replied_comment_ids.json",
                 reply_log_file="logs/auto_reply_log.json"):
        self.fb_page_id = fb_page_id
        self.fb_access_token = fb_access_token
        self.auto_comment_enabled = auto_comment_enabled
        self.fb_graph_url = f"https://graph.facebook.com/{fb_api_version}"

        self.days_limit = days_limit
        self.max_replies_per_run = max_replies_per_run
        self.max_conversation_depth = max_conversation_depth
        self.min_comment_age_min = min_comment_age_min
        self.max_comment_age_hours = max_comment_age_hours
        self.posts_to_scan = posts_to_scan
        self.comment_fetch_workers = comment_fetch_workers

        self.replied_file = replied_file
        self.reply_log_file = reply_log_file

        self._name_cache = {}

        self.client = OpenRouterClient(keys=openrouter_keys, max_retries=max_json_retries)

    # ---------- USER NAME ----------
    def _get_user_name(self, user_id, fallback_from_field=None):
        if fallback_from_field and fallback_from_field.strip():
            return fallback_from_field.strip()
        if not user_id:
            return "Unknown User"
        if user_id in self._name_cache:
            return self._name_cache[user_id]
        try:
            res = requests.get(
                f"{self.fb_graph_url}/{user_id}",
                params={"fields": "name", "access_token": self.fb_access_token},
                timeout=8)
            if res.status_code == 200:
                name = (res.json().get("name") or "").strip()
                if name:
                    self._name_cache[user_id] = name
                    return name
        except Exception:
            pass
        short = user_id[-6:] if len(user_id) > 6 else user_id
        name = f"User_{short}"
        self._name_cache[user_id] = name
        return name

    # ---------- FB API ----------
    def _fetch_fb_comments(self, post_id, since_timestamp=None):
        params = {
            "fields": "id,message,from{name,id},created_time,can_reply",
            "access_token": self.fb_access_token,
            "limit": 50,
        }
        if since_timestamp:
            params["since"] = since_timestamp
        try:
            res = requests.get(f"{self.fb_graph_url}/{post_id}/comments",
                               params=params, timeout=15)
            if res.status_code == 200:
                return res.json().get("data", [])
            log(f"      ⚠️ comments error ({res.status_code}): {res.text[:150]}")
        except Exception as e:
            log(f"      ⚠️ comments exception: {e}")
        return []

    def _fetch_comment_replies(self, comment_id):
        params = {
            "fields": "id,message,from{name,id},created_time,can_reply",
            "access_token": self.fb_access_token,
            "limit": 50,
        }
        try:
            res = requests.get(f"{self.fb_graph_url}/{comment_id}/comments",
                               params=params, timeout=15)
            if res.status_code == 200:
                return res.json().get("data", [])
        except Exception:
            pass
        return []

    def _post_fb_reply(self, reply_to_id, reply_text):
        if not self.auto_comment_enabled:
            log(f"🚫 [AUTO_COMMENT OFF] Would post: {reply_text[:80]}")
            return f"disabled_{reply_to_id}"
        try:
            res = requests.post(
                f"{self.fb_graph_url}/{reply_to_id}/comments",
                data={"message": reply_text, "access_token": self.fb_access_token},
                timeout=15)
            if res.status_code == 200:
                return res.json().get("id")
            log(f"⚠️ Reply post error ({res.status_code}): {res.text[:200]}")
        except Exception as e:
            log(f"⚠️ Reply post exception: {e}")
        return None

    # ---------- THREAD ----------
    def _analyze_thread(self, top_comment):
        cid = top_comment.get("id", "")
        replies = self._fetch_comment_replies(cid)
        replies_sorted = sorted(replies, key=lambda x: x.get("created_time", ""))

        our_count = sum(
            1 for r in replies_sorted
            if r.get("from", {}).get("id") == self.fb_page_id
        )

        if our_count >= self.max_conversation_depth:
            return {"depth": our_count, "should_reply": False, "reason": "max_depth"}

        if replies_sorted and our_count > 0:
            last = replies_sorted[-1]
            if last.get("from", {}).get("id") == self.fb_page_id:
                return {"depth": our_count, "should_reply": False, "reason": "waiting_user"}

        thread_ctx = ""
        for r in replies_sorted[-4:]:
            who = "US" if r.get("from", {}).get("id") == self.fb_page_id else "USER"
            msg = (r.get("message", "") or "").replace("\n", " ")[:100]
            thread_ctx += f"  {who}: {msg}\n"

        user_msgs = [top_comment] + [
            r for r in replies_sorted
            if r.get("from", {}).get("id") != self.fb_page_id
        ]
        if not user_msgs:
            return {"depth": our_count, "should_reply": False, "reason": "no_user_msg"}

        last_user = user_msgs[-1]
        last_text = (last_user.get("message") or "").strip()
        if not last_text:
            return {"depth": our_count, "should_reply": False, "reason": "empty"}

        top_from = top_comment.get("from", {}) or {}
        user_id = top_from.get("id", "")
        user_name = self._get_user_name(user_id, top_from.get("name"))

        return {
            "depth": our_count,
            "should_reply": True,
            "reason": "ok",
            "reply_to_id": last_user.get("id") or cid,
            "reply_to_text": last_text,
            "user_id": user_id,
            "user_name": user_name,
            "thread_context": thread_ctx,
        }

    @staticmethod
    def _detect_game_from_post(post_message_full):
        hashtags = re.findall(r'#(\w+)', post_message_full)
        game_name = "Video Game"
        for tag in hashtags:
            tag_clean = tag.lower().replace("_", "").replace("-", "")
            for g in KNOWN_GAMES:
                g_clean = g.lower().replace(" ", "").replace("_", "").replace("-", "")
                if g_clean == tag_clean or g_clean in tag_clean or tag_clean in g_clean:
                    game_name = g
                    break
            if game_name != "Video Game":
                break
        if game_name == "Video Game":
            for g in KNOWN_GAMES:
                if g.lower() in post_message_full.lower():
                    game_name = g
                    break
        return game_name, hashtags

    # ---------- MAIN RUN ----------
    def run(self):
        if not self.auto_comment_enabled:
            log("🚫 Auto-comment disabled")
            return None
        if not self.fb_page_id or not self.fb_access_token:
            log("❌ FB_PAGE_ID or PAGE_ACCESS_TOKEN missing")
            return None

        log("🤖 FB Auto-reply started...")

        reply_log = {"total_replies": 0, "total_skipped": 0,
                     "replies": [], "skipped": []}
        if os.path.exists(self.reply_log_file):
            try:
                with open(self.reply_log_file, 'r', encoding='utf-8') as f:
                    reply_log = json.load(f)
            except Exception:
                pass

        cutoff_time = (now_ist() - timedelta(hours=self.max_comment_age_hours)).timestamp()
        min_age_time = (now_ist() - timedelta(minutes=self.min_comment_age_min)).timestamp()

        log(f"📥 Fetching latest {self.posts_to_scan} posts")
        try:
            res = requests.get(
                f"{self.fb_graph_url}/{self.fb_page_id}/posts",
                params={"fields": "id,message,created_time,permalink_url",
                        "access_token": self.fb_access_token,
                        "limit": self.posts_to_scan},
                timeout=20)
            if res.status_code != 200:
                log(f"❌ FB posts error ({res.status_code}): {res.text[:300]}")
                return None
            posts = res.json().get("data", [])
            log(f"✅ {len(posts)} posts")
        except Exception as e:
            log(f"❌ FB posts exception: {e}")
            return None

        if not posts:
            return None

        post_comments_map = {}

        def fetch_post_comments(post):
            pid = post.get("id", "")
            if not pid:
                return (pid, [])
            try:
                return (pid, self._fetch_fb_comments(pid))
            except Exception as e:
                log(f"      ⚠️ Error {pid}: {e}")
                return (pid, [])

        with ThreadPoolExecutor(max_workers=self.comment_fetch_workers) as ex:
            futures = {ex.submit(fetch_post_comments, p): p for p in posts}
            for fut in as_completed(futures):
                try:
                    pid, comments = fut.result()
                    post_comments_map[pid] = comments
                except Exception as e:
                    log(f"⚠️ Parallel error: {e}")

        total_comments = sum(len(c) for c in post_comments_map.values())
        log(f"✅ {total_comments} comments fetched")

        valid_comments = []
        skipped_logs = []
        permanent_skip_ids = set()

        for post in posts:
            if len(valid_comments) >= self.max_replies_per_run:
                break
            post_id = post.get("id", "")
            post_message_full = post.get("message", "") or ""
            post_message = post_message_full[:80]
            comments = post_comments_map.get(post_id, [])
            if not comments:
                continue

            game_name, hashtags = self._detect_game_from_post(post_message_full)
            log(f"🔍 Post {post_id} | {post_message} | {len(comments)} comments")
            log(f"      🎮 Game: {game_name}")

            for comment in comments:
                if len(valid_comments) >= self.max_replies_per_run:
                    break

                comment_id = comment.get("id", "")
                comment_text = (comment.get("message") or "").strip()
                comment_time = comment.get("created_time", "")
                can_reply = comment.get("can_reply", True)

                if not comment_id or not comment_text:
                    continue
                if not can_reply:
                    continue

                from_data = comment.get("from", {}) or {}
                if from_data.get("id") == self.fb_page_id:
                    continue

                try:
                    dt = datetime.fromisoformat(comment_time.replace("+0000", "+00:00"))
                    ts = dt.timestamp()
                    if ts < cutoff_time or ts > min_age_time:
                        continue
                except Exception:
                    pass

                abuse_type = detect_abuse(comment_text)
                if abuse_type == "family_abuse":
                    skipped_logs.append({
                        "comment_id": comment_id,
                        "comment_text": comment_text[:100],
                        "reason": "family_abuse",
                        "timestamp": now_ist_ampm(),
                    })
                    permanent_skip_ids.add(comment_id)
                    continue

                if is_spam(comment_text):
                    skipped_logs.append({
                        "comment_id": comment_id,
                        "comment_text": comment_text[:100],
                        "reason": "spam",
                        "timestamp": now_ist_ampm(),
                    })
                    permanent_skip_ids.add(comment_id)
                    continue

                state = self._analyze_thread(comment)
                if not state["should_reply"]:
                    if state["reason"] in ("max_depth", "waiting_user"):
                        log(f"      ⏭️ Thread skip ({state['reason']}) — {comment_id[:20]}")
                    continue

                user_name = state["user_name"]
                user_id = state["user_id"]

                log(f"      ✅ VALID (depth={state['depth']}) | "
                    f"'{state['reply_to_text'][:50]}' | user={user_name}")

                valid_comments.append({
                    "comment_id": comment_id,
                    "reply_to_id": state["reply_to_id"],
                    "comment_text": state["reply_to_text"],
                    "thread_context": state["thread_context"],
                    "current_depth": state["depth"],
                    "game_name": game_name,
                    "post_title": post_message,
                    "post_hashtags": hashtags,
                    "is_abuse": (abuse_type == "general_abuse"),
                    "post_id": post_id,
                    "fb_link": post.get("permalink_url", f"https://www.facebook.com/{post_id}"),
                    "source_link": "",
                    "user_name": user_name,
                    "user_id": user_id,
                })

        if not valid_comments:
            log("ℹ️ No valid comments")
            replies_map = {}
        else:
            log(f"📦 Batch: {len(valid_comments)} comments → 12-retry loop")
            replies_map = self.client.generate_batch_replies(valid_comments)

        replies_count = 0
        for c in valid_comments:
            cid = c["comment_id"]
            reply_text = replies_map.get(cid)
            if not reply_text:
                log(f"⚠️ No reply for {cid} — skip")
                continue

            safe, reason = is_reply_safe(reply_text, is_abuse=c["is_abuse"])
            if not safe:
                log(f"⚠️ Unsafe ({reason}) for {cid}")
                skipped_logs.append({
                    "comment_id": cid,
                    "comment_text": c["comment_text"][:100],
                    "reason": f"unsafe_{reason}",
                    "timestamp": now_ist_ampm(),
                })
                continue

            reply_id = self._post_fb_reply(c["reply_to_id"], reply_text)
            if reply_id:
                replies_count += 1
                reply_log["replies"].append({
                    "reply_id": reply_id,
                    "comment_id": cid,
                    "reply_to_id": c["reply_to_id"],
                    "post_id": c["post_id"],
                    "user_name": c["user_name"],
                    "user_id": c["user_id"],
                    "user_comment": c["comment_text"][:200],
                    "openrouter_reply": reply_text,
                    "type": "savage" if c["is_abuse"] else "friendly",
                    "depth": c["current_depth"] + 1,
                    "game": c["game_name"],
                    "post_title": c["post_title"][:100],
                    "fb_post_link": c["fb_link"],
                    "source_link": c["source_link"],
                    "timestamp": now_ist_ampm(),
                    "status": "posted",
                })
                reply_log["total_replies"] = reply_log.get("total_replies", 0) + 1
                log(f"✅ Posted [depth {c['current_depth'] + 1}] {cid[:20]} → user={c['user_name']}")
                log(f"   💬 {c['comment_text'][:80]}")
                log(f"   🤖 {reply_text[:80]}")
            else:
                log(f"❌ Failed to post for {cid}")

        reply_log["skipped"].extend(skipped_logs)
        reply_log["total_skipped"] = reply_log.get("total_skipped", 0) + len(skipped_logs)

        os.makedirs("logs", exist_ok=True)

        existing_ids = set()
        if os.path.exists(self.replied_file):
            try:
                with open(self.replied_file, 'r', encoding='utf-8') as f:
                    existing_ids = set(json.load(f).get("replied", []))
            except Exception:
                pass

        all_replied_ids = list(existing_ids | permanent_skip_ids)

        try:
            with open(self.replied_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "replied": all_replied_ids[-5000:],
                    "last_updated": now_ist_ampm(),
                }, f, indent=2)
        except Exception as e:
            log(f"⚠️ replied_file save error: {e}")

        reply_log["replies"] = reply_log.get("replies", [])[-200:]
        reply_log["skipped"] = reply_log.get("skipped", [])[-100:]
        reply_log["last_updated"] = now_ist_ampm()
        try:
            with open(self.reply_log_file, 'w', encoding='utf-8') as f:
                json.dump(reply_log, f, indent=2)
        except Exception as e:
            log(f"⚠️ reply_log save error: {e}")

        log(f"🤖 FB Auto-reply done. {replies_count} replies posted.")
        return reply_log


# ============================================================
# 📊 DASHBOARD UPDATE (game_analytics.py use karega)
# ============================================================
def update_dashboard():
    """game_analytics.py ko call karke dashboard update karo."""
    try:
        from game_analytics import AnalyticsEngine
    except ImportError as e:
        log(f"⚠️ game_analytics.py not found — skipping dashboard: {e}")
        return

    fb_page_id = os.environ.get("PAGE_ID")
    fb_token = os.environ.get("PAGE_ACCESS_TOKEN")
    openrouter_keys = [
        os.environ.get("OPENROUTER_API_KEY"),
        os.environ.get("OPENROUTER_API_KEY_2"),
        os.environ.get("OPENROUTER_API_KEY_3"),
        os.environ.get("OPENROUTER_API_KEY_4"),
        os.environ.get("OPENROUTER_API_KEY_5"),
    ]

    # Discover games
    game_list, file_mapping = discover_game_files()
    if not game_list:
        log("⚠️ No game files — dashboard skip")
        return

    memory = load_memory()

    log("\n" + "=" * 60)
    log("📊 DASHBOARD UPDATE")
    log("=" * 60)

    engine = AnalyticsEngine(
        game_list=game_list,
        fb_page_id=fb_page_id,
        fb_access_token=fb_token,
        openrouter_keys=openrouter_keys,
        auto_comment_enabled=False,   # dashboard ke liye comment skip
    )

    # Fetch FB/IG data
    actual_posted_titles, game_views_summary = engine.fetch_fb_ig_data()
    if not game_views_summary:
        game_views_summary = {g: 0 for g in game_list}

    # Trending + Best time
    try:
        engine.detect_trending_games(actual_posted_titles, game_views_summary, days=7)
    except Exception as e:
        log(f"⚠️ Trending error: {e}")

    try:
        engine.analyze_best_time({})
    except Exception as e:
        log(f"⚠️ Best time error: {e}")

    # Latest active game
    def latest_ts(g):
        t = ""
        for v in actual_posted_titles.get(g, []):
            if v.get("fb_posted") or v.get("ig_posted"):
                ts = v.get("timestamp", "")
                if ts > t:
                    t = ts
        return t

    chosen_game = memory.get("last_played_game") or ""
    if not chosen_game or chosen_game not in game_list:
        active = [g for g in game_list if latest_ts(g)]
        chosen_game = max(active, key=latest_ts) if active else game_list[0]

    memory["actual_posted_titles"] = actual_posted_titles
    memory["last_played_game"] = chosen_game
    save_memory(memory)

    latest_fb_link = latest_ig_link = latest_title = ""
    latest_views = 0
    for v in actual_posted_titles.get(chosen_game, []):
        if v.get("fb_posted") or v.get("ig_posted"):
            latest_fb_link = v.get("fb_link", "")
            latest_ig_link = v.get("ig_link", "")
            latest_views = v.get("fb_views", 0) + v.get("ig_views", 0)
            latest_title = v.get("title", "")
            break

    generated_ai_title = f"🎮 {chosen_game} Gameplay | #{chosen_game.replace(' ', '')}"

    engine.update_unified_dashboard(
        game_name=chosen_game,
        chosen_style=memory.get("last_used_style", "curiosity"),
        ai_title=generated_ai_title,
        specific_uploaded_link="N/A",
        post_link=latest_fb_link or latest_ig_link or "N/A",
        platform_name=("Facebook" if latest_fb_link
                       else "Instagram" if latest_ig_link
                       else "Local / Pending"),
        views_count=latest_views,
        game_views_summary=game_views_summary,
        game_stats=memory.get("game_stats", {}),
        actual_posted_titles=actual_posted_titles,
        file_mapping=file_mapping,
    )

    log(f"✅ Dashboard updated (context game: {chosen_game})")


# ============================================================
# 🚀 MAIN
# ============================================================
def main():
    auto_enabled = os.environ.get("AUTO_COMMENT", "true").lower() == "true"

    # STEP 1: FB Auto-Comment
    if auto_enabled:
        commenter = FBAutoCommenter(
            fb_page_id=os.environ.get("PAGE_ID"),
            fb_access_token=os.environ.get("PAGE_ACCESS_TOKEN"),
            openrouter_keys=[
                os.environ.get("OPENROUTER_API_KEY"),
                os.environ.get("OPENROUTER_API_KEY_2"),
                os.environ.get("OPENROUTER_API_KEY_3"),
                os.environ.get("OPENROUTER_API_KEY_4"),
                os.environ.get("OPENROUTER_API_KEY_5"),
            ],
            auto_comment_enabled=True,
            max_replies_per_run=10,
            max_conversation_depth=3,
        )
        result = commenter.run()
        if result:
            log(f"\n✅ Auto-reply done: {result.get('total_replies', 0)} posted, "
                f"{result.get('total_skipped', 0)} skipped")
    else:
        log("🚫 AUTO_COMMENT=false — skipping replies")

    # STEP 2: Dashboard Update
    try:
        update_dashboard()
    except Exception as e:
        log(f"⚠️ Dashboard update error: {e}")

    # Final summary
    log(f"\n{'=' * 60}")
    log(f"🚀 SPLIT SCRIPT DONE — {now_ist_ampm()} IST")
    log(f"{'=' * 60}")


if __name__ == "__main__":
    try:
        main()
        log("✅ Script completed successfully — exiting")
        sys.exit(0)
    except KeyboardInterrupt:
        log("⚠️ Interrupted by user")
        sys.exit(130)
    except Exception as e:
        log(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)