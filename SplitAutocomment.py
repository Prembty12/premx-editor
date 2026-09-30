"""
💬 SPLIT AUTO-COMMENT SCRIPT (FINAL v6 — Shared Log Fix)
=========================================================
✅ Auto-comment — Full script ke SATH log share karta hai
✅ FB API pe bharosa (user ke naye reply detect honge)
✅ Recursive nested replies fetch
✅ Last reply check FIRST — no duplicate
✅ Log check sirf FRESH comment ke liye
✅ 🔥 FIX: reply_to_id bhi log me — nested reply pe double reply nahi
"""

import os
import re
import json
import time
import sys
import glob
import random
import requests
import subprocess
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


def utc_to_ist(iso_time_str):
    if not iso_time_str:
        return None
    try:
        s = str(iso_time_str).strip().replace("Z", "+00:00").replace("+0000", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(IST)
    except Exception:
        return None


def normalize(s):
    if not s:
        return ""
    return re.sub(r'[^a-z0-9]', '', s.lower())


def extract_urls(text):
    urls = re.findall(r'https?://[^\s\)\]\'"<>,;]+', text)
    cleaned, seen = [], set()
    for u in urls:
        u = u.rstrip('.,;)\']"')
        if u and u not in seen:
            seen.add(u)
            cleaned.append(u)
    return cleaned


def fix_fb_url(url, vid_id=""):
    if not url:
        return f"https://www.facebook.com/{vid_id}" if vid_id else ""
    url = str(url).strip()
    if url.startswith(("http://", "https://")):
        return url
    if url.startswith("/"):
        return f"https://www.facebook.com{url}"
    return f"https://www.facebook.com/{url}"


def fix_ig_url(url):
    if not url:
        return ""
    url = str(url).strip()
    if url.startswith(("http://", "https://")):
        return url
    if url.startswith("/"):
        return f"https://www.instagram.com{url}"
    return f"https://www.instagram.com/{url}"


def load_source_data(posted_dir="posted_links_editor"):
    source_links_map, source_videos_count, source_titles_map = {}, {}, {}
    if not os.path.exists(posted_dir):
        return source_links_map, source_videos_count, source_titles_map
    for fname in os.listdir(posted_dir):
        if fname.endswith("_posted_links_editor.txt"):
            gname = fname.replace("_posted_links_editor.txt", "")
            try:
                with open(os.path.join(posted_dir, fname), 'r',
                          encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                urls = extract_urls(content)
                if urls:
                    source_links_map[gname] = urls
                vid_count = content.count("Video id :") or len(urls)
                source_videos_count[gname] = vid_count
                titles = re.findall(r'Title\s*:\s*(.+)', content)
                source_titles_map[gname] = [t.strip() for t in titles]
            except Exception:
                pass
    return source_links_map, source_videos_count, source_titles_map


# ============================================================
# 🔑 CONSTANTS
# ============================================================
OPENROUTER_KEYS = [
    os.environ.get("OPENROUTER_API_KEY"),
    os.environ.get("OPENROUTER_API_KEY_2"),
    os.environ.get("OPENROUTER_API_KEY_3"),
    os.environ.get("OPENROUTER_API_KEY_4"),
    os.environ.get("OPENROUTER_API_KEY_5"),
]

FIXED_MODEL = "dots-studio/dots-3-note-preview:free"
FALLBACK_MODEL = "openrouter/free"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

FB_PAGE_ID = os.environ.get("PAGE_ID")
FB_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")

FB_API_VERSION = "v24.0"
FB_GRAPH_URL = f"https://graph.facebook.com/{FB_API_VERSION}"

DAYS_LIMIT = 28
MAX_REPLIES_PER_RUN = 10
MAX_CONVERSATION_DEPTH = 3
MIN_COMMENT_AGE_MIN = 0
MAX_COMMENT_AGE_HOURS = 24
POSTS_TO_SCAN = 25
COMMENT_FETCH_WORKERS = 10
MAX_JSON_RETRIES = 12

# 🔥 SHARED LOG FILES — FULL SCRIPT BHI YEH HI USE KARTA HAI
SHARED_REPLY_LOG = "logs/auto_reply_log.json"
SHARED_REPLIED_IDS = "logs/replied_comment_ids.json"

AUTO_COMMENT_ENABLED = os.environ.get("AUTO_COMMENT", "true").lower() == "true"

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
# 🤖 OPENROUTER CLIENT
# ============================================================
def _call_openrouter_single(model_name, api_key, prompt, max_tokens=150):
    if not api_key:
        return None
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/",
        "X-Title": "Gaming Auto-Agent",
    }
    payload = {
        "model": model_name,
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
                content = choices[0].get("message", {}).get("content", "")
                if content:
                    return content.strip()
        else:
            log(f"   ⚠️ HTTP {res.status_code}: {res.text[:120]}")
    except Exception as e:
        log(f"   ⚠️ Exception: {e}")
    return None


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


def generate_batch_replies(comments_batch, max_retries=MAX_JSON_RETRIES):
    if not comments_batch:
        return {}
    formatted = ""
    for c in comments_batch:
        tone = "SAVAGE" if c["is_abuse"] else "FRIENDLY"
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

    prompt = f"""You are a real gaming content creator replying to comments on your social media page.

Your replies should feel like a real human texting — casual, warm, funny, confident.

RULES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Reply in the SAME language as the comment (English/Hinglish only).
2. Keep it SHORT — maximum 25 words.
3. Use natural slang — bhai, bro, yaar, lol, chill, OP, fire, lit.
4. Use 1-2 emojis max.
5. Sound like a real person, not a robot.
6. Match the vibe of the comment.
7. Make them WANT to reply back.
8. If comment asks game name → tell the game name.
9. If comment is abusive → savage witty comeback, no abuse back.
10. If there's a "Conversation So Far" — continue naturally, don't repeat.

Never share links. Never insult family/religion/caste.

CRITICAL: Return ONLY valid JSON. Keys = comment IDs. Values = reply text.

Example:
{{
  "COMMENT_ID_1": "reply 1",
  "COMMENT_ID_2": "reply 2"
}}

COMMENTS TO REPLY:
{formatted}

YOUR JSON RESPONSE:"""

    valid_keys = [k for k in OPENROUTER_KEYS if k]
    if not valid_keys:
        log("❌ No OpenRouter API keys found.")
        return {}

    for attempt in range(1, max_retries + 1):
        key_index = (attempt - 1) % len(valid_keys)
        current_key = valid_keys[key_index]
        model_to_use = FIXED_MODEL if attempt == 1 else FALLBACK_MODEL
        tag = "FIXED" if attempt == 1 else "FALLBACK"
        log(f"🔄 Attempt {attempt}/{max_retries} | {tag} | Key {key_index + 1}")

        response = _call_openrouter_single(model_to_use, current_key, prompt, max_tokens=1800)
        if not response:
            log("   ⚠️ Empty response — retry")
            time.sleep(1)
            continue
        if response.strip().lower() in ["user safety: safe", "safe", "unsafe", "none"]:
            log("   ⚠️ Safety model response — retry")
            time.sleep(1)
            continue
        parsed = _extract_json(response)
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

    log(f"❌ Failed to get valid JSON after {max_retries} attempts.")
    return {}


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
# 💬 AUTO-COMMENT — SHARED LOG (v6 FIXED)
# ============================================================
_page_name_cache = ""
_user_name_cache = {}
_replied_history_cache = None


def get_page_name():
    global _page_name_cache
    if _page_name_cache:
        return _page_name_cache
    try:
        res = requests.get(
            f"{FB_GRAPH_URL}/{FB_PAGE_ID}",
            params={"fields": "name", "access_token": FB_ACCESS_TOKEN},
            timeout=8)
        if res.status_code == 200:
            name = (res.json().get("name") or "").strip()
            if name:
                _page_name_cache = name
                return name
    except Exception:
        pass
    _page_name_cache = ""
    return ""


def get_user_name(user_id, fallback_from_field=None):
    global _user_name_cache
    if fallback_from_field and str(fallback_from_field).strip():
        return str(fallback_from_field).strip()
    if user_id:
        user_id = str(user_id).strip()
        if user_id in _user_name_cache:
            return _user_name_cache[user_id]
        try:
            res = requests.get(
                f"{FB_GRAPH_URL}/{user_id}",
                params={"fields": "name", "access_token": FB_ACCESS_TOKEN},
                timeout=8)
            if res.status_code == 200:
                name = (res.json().get("name") or "").strip()
                if name:
                    _user_name_cache[user_id] = name
                    return name
        except Exception:
            pass
        short = user_id[-6:] if len(user_id) > 6 else user_id
        name = f"User_{short}"
        _user_name_cache[user_id] = name
        return name
    return "Facebook User"


def load_replied_history():
    """
    ✅ SHARED LOG READER — full script bhi yahi file likhta hai.
    Loads comment_id + reply_id + reply_to_id sab.
    """
    global _replied_history_cache
    if _replied_history_cache is not None:
        return _replied_history_cache
    _replied_history_cache = {}
    if os.path.exists(SHARED_REPLY_LOG):
        try:
            with open(SHARED_REPLY_LOG, 'r', encoding='utf-8') as f:
                log_data = json.load(f)
            for r in log_data.get("replies", []):
                cid = r.get("comment_id", "")
                rid = r.get("reply_id", "")
                r_to = r.get("reply_to_id", "")
                depth = r.get("depth", 1)
                for key in (cid, rid, r_to):
                    if key:
                        _replied_history_cache[key] = max(
                            _replied_history_cache.get(key, 0), depth)
        except Exception:
            pass
    return _replied_history_cache


def was_already_replied(comment_id):
    """
    ✅ SHARED — dono scripts same log check karte hain.
    Check 2 files:
      1. logs/auto_reply_log.json (via load_replied_history)
      2. logs/replied_comment_ids.json
    """
    if not comment_id:
        return False
    if comment_id in load_replied_history():
        return True
    if os.path.exists(SHARED_REPLIED_IDS):
        try:
            with open(SHARED_REPLIED_IDS, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if comment_id in set(data.get("replied", [])):
                return True
        except Exception:
            pass
    return False


def fetch_fb_comments(post_id, since_timestamp=None):
    params = {
        "fields": "id,message,from{name,id},created_time,can_reply",
        "access_token": FB_ACCESS_TOKEN,
        "limit": 50,
    }
    if since_timestamp:
        params["since"] = since_timestamp
    try:
        res = requests.get(f"{FB_GRAPH_URL}/{post_id}/comments",
                           params=params, timeout=15)
        if res.status_code == 200:
            return res.json().get("data", [])
        log(f"      ⚠️ comments error ({res.status_code}): {res.text[:150]}")
    except Exception as e:
        log(f"      ⚠️ comments exception: {e}")
    return []


def fetch_comment_replies(comment_id, depth=0, max_depth=3):
    """✅ RECURSIVE — nested replies bhi fetch karo."""
    if depth >= max_depth:
        return []
    params = {
        "fields": "id,message,from{name,id},created_time,can_reply",
        "access_token": FB_ACCESS_TOKEN,
        "limit": 50,
    }
    all_replies = []
    try:
        res = requests.get(f"{FB_GRAPH_URL}/{comment_id}/comments",
                           params=params, timeout=15)
        if res.status_code == 200:
            replies = res.json().get("data", [])
            for r in replies:
                all_replies.append(r)
                nested = fetch_comment_replies(r["id"], depth + 1, max_depth)
                all_replies.extend(nested)
    except Exception:
        pass
    return all_replies


def post_fb_reply(comment_id, reply_text):
    if not AUTO_COMMENT_ENABLED:
        log(f"🚫 [AUTO_COMMENT OFF] Would post: {reply_text[:80]}")
        return f"disabled_{comment_id}"
    try:
        time.sleep(random.uniform(2, 5))
        res = requests.post(
            f"{FB_GRAPH_URL}/{comment_id}/comments",
            data={"message": reply_text, "access_token": FB_ACCESS_TOKEN},
            timeout=15)
        if res.status_code == 200:
            data = res.json()
            reply_id = data.get("id")
            if reply_id:
                return reply_id
            return f"synth_{comment_id}_{int(time.time())}"
        log(f"⚠️ Reply post error ({res.status_code}): {res.text[:200]}")
    except Exception as e:
        log(f"⚠️ Reply post exception: {e}")
    return None


def _is_our_reply(reply_obj, page_name_lower):
    r_from = reply_obj.get("from", {}) or {}
    r_id = r_from.get("id", "")
    r_name = (r_from.get("name") or "").strip().lower()
    return (r_id == FB_PAGE_ID
            or (page_name_lower and r_name == page_name_lower))


def analyze_thread(top_comment):
    """
    ✅ v6 FIXED LOGIC:
    1. FB API se recursive replies fetch
    2. Last reply check FIRST (agar humara hai → SKIP)
    3. Log check sirf FRESH comment ke liye
    4. Nested reply pe bhi check — agar uska reply ho chuka hai to skip
    """
    cid = top_comment.get("id", "")

    # Step 1: FB API se replies fetch (recursive)
    replies = fetch_comment_replies(cid)
    replies_sorted = sorted(replies, key=lambda x: x.get("created_time", ""))

    page_name = get_page_name()
    page_name_lower = page_name.lower() if page_name else ""

    our_replies, user_replies = [], []
    for r in replies_sorted:
        if _is_our_reply(r, page_name_lower):
            our_replies.append(r)
        else:
            user_replies.append(r)

    our_count = len(our_replies)

    # Step 2: MAX DEPTH check
    if our_count >= MAX_CONVERSATION_DEPTH:
        return {"should_reply": False, "depth": our_count, "reason": "max_depth"}

    # Step 3: FRESH COMMENT (FB pe koi replies nahi)
    if len(replies_sorted) == 0:
        # ✅ SHARED LOG CHECK — agar kisi ne bhi reply kiya to skip
        if was_already_replied(cid):
            log(f"      ⏭️ Fresh on FB but IN SHARED LOG — skip")
            return {"should_reply": False, "depth": 0, "reason": "already_replied_log"}
        log(f"      🆕 Fresh comment — WILL REPLY")

    # Step 4: Replies hain FB pe
    else:
        last = replies_sorted[-1]
        if _is_our_reply(last, page_name_lower):
            log(f"      ⏭️ Last reply is OURS — waiting for user")
            return {"should_reply": False, "depth": our_count, "reason": "waiting_user"}

        # Last reply USER ka hai — check karo ki IS user reply ka already jawab diya hai kya?
        last_user_id = last.get("id", "")
        if last_user_id and was_already_replied(last_user_id):
            log(f"      ⏭️ Already replied to this user reply — skip")
            return {"should_reply": False, "depth": our_count,
                    "reason": "already_replied_this_reply"}

        log(f"      💬 NEW user reply — continuing (depth {our_count})")

    # Step 5: Build context
    thread_ctx = ""
    for r in replies_sorted[-6:]:
        who = "US" if _is_our_reply(r, page_name_lower) else "USER"
        msg = (r.get("message", "") or "").replace("\n", " ")[:150]
        thread_ctx += f"  {who}: {msg}\n"

    user_msgs = [top_comment] + user_replies
    if not user_msgs:
        return {"should_reply": False, "depth": our_count, "reason": "no_user_msg"}

    last_user = user_msgs[-1]
    last_text = (last_user.get("message") or "").strip()
    if not last_text:
        return {"should_reply": False, "depth": our_count, "reason": "empty"}

    top_from = top_comment.get("from", {}) or {}
    user_id = top_from.get("id", "")
    user_name = get_user_name(user_id, top_from.get("name"))

    return {
        "should_reply": True,
        "depth": our_count,
        "reason": "ok",
        "reply_to_id": last_user.get("id") or cid,
        "reply_to_text": last_text,
        "user_id": user_id,
        "user_name": user_name,
        "thread_context": thread_ctx,
    }


def process_fb_comments(actual_posted_titles=None):
    if not AUTO_COMMENT_ENABLED:
        log("🚫 Auto-comment disabled")
        return None

    log("🤖 Auto-reply started (v6 — SHARED LOG)...")
    log(f"📂 Shared log: {SHARED_REPLY_LOG}")

    page_name = get_page_name()
    log(f"📄 Page name: {page_name or 'N/A'}")

    # ✅ Load shared replied_ids
    replied_data = {"replied": [], "last_updated": ""}
    if os.path.exists(SHARED_REPLIED_IDS):
        try:
            with open(SHARED_REPLIED_IDS, 'r', encoding='utf-8') as f:
                replied_data = json.load(f)
        except Exception:
            pass
    replied_ids = set(replied_data.get("replied", []))

    # ✅ Load shared reply_log
    reply_log = {"total_replies": 0, "total_skipped": 0, "replies": [], "skipped": []}
    if os.path.exists(SHARED_REPLY_LOG):
        try:
            with open(SHARED_REPLY_LOG, 'r', encoding='utf-8') as f:
                reply_log = json.load(f)
            log(f"📂 Existing history: {len(reply_log.get('replies', []))} replies (SHARED)")
        except Exception:
            pass

    # ✅ Prime cache with shared history
    history = load_replied_history()
    for hid in history.keys():
        replied_ids.add(hid)
    log(f"📂 Replied history cache: {len(history)} IDs")

    cutoff_time = (now_ist() - timedelta(hours=MAX_COMMENT_AGE_HOURS)).timestamp()
    min_age_time = (now_ist() - timedelta(minutes=MIN_COMMENT_AGE_MIN)).timestamp()

    log(f"📥 Fetching latest {POSTS_TO_SCAN} posts")
    try:
        res = requests.get(
            f"{FB_GRAPH_URL}/{FB_PAGE_ID}/posts",
            params={"fields": "id,message,created_time,permalink_url",
                    "access_token": FB_ACCESS_TOKEN,
                    "limit": POSTS_TO_SCAN},
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
            return (pid, fetch_fb_comments(pid))
        except Exception as e:
            log(f"      ⚠️ Error {pid}: {e}")
            return (pid, [])

    with ThreadPoolExecutor(max_workers=COMMENT_FETCH_WORKERS) as ex:
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

    for post in posts:
        if len(valid_comments) >= MAX_REPLIES_PER_RUN:
            break
        post_id = post.get("id", "")
        post_message_full = post.get("message", "") or ""
        post_message = post_message_full[:80]
        comments = post_comments_map.get(post_id, [])
        if not comments:
            continue

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

        log(f"🔍 Post {post_id} | {post_message} | {len(comments)} comments")
        log(f"      🎮 Game: {game_name}")

        for comment in comments:
            if len(valid_comments) >= MAX_REPLIES_PER_RUN:
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
            if from_data.get("id") == FB_PAGE_ID:
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
                replied_ids.add(comment_id)
                continue
            if is_spam(comment_text):
                skipped_logs.append({
                    "comment_id": comment_id,
                    "comment_text": comment_text[:100],
                    "reason": "spam",
                    "timestamp": now_ist_ampm(),
                })
                replied_ids.add(comment_id)
                continue

            state = analyze_thread(comment)
            if not state["should_reply"]:
                if state["reason"] in ("max_depth", "waiting_user",
                                        "already_replied_log",
                                        "already_replied_this_reply"):
                    log(f"      ⏭️ Skip ({state['reason']}) — {comment_id[:20]}")
                continue

            log(f"      ✅ VALID (depth={state['depth']}) | "
                f"'{state['reply_to_text'][:50]}' | user={state['user_name']}")

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
                "fb_link": post.get("permalink_url",
                                    f"https://www.facebook.com/{post_id}"),
                "source_link": "",
                "user_name": state["user_name"],
                "user_id": state["user_id"],
            })

    if not valid_comments:
        log("ℹ️ No valid comments")
        replies_map = {}
    else:
        log(f"📦 Batch: {len(valid_comments)} comments → 12-retry loop")
        replies_map = generate_batch_replies(valid_comments)

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

        reply_id = post_fb_reply(c["reply_to_id"], reply_text)
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

            # ✅ 3 IDs add karo — dono scripts skip karein
            replied_ids.add(cid)
            replied_ids.add(reply_id)
            replied_ids.add(c["reply_to_id"])

            log(f"✅ Posted [depth {c['current_depth'] + 1}] {cid[:20]} → user={c['user_name']}")
            log(f"   💬 {c['comment_text'][:80]}")
            log(f"   🤖 {reply_text[:80]}")
        else:
            log(f"❌ Failed to post for {cid}")

    reply_log["skipped"].extend(skipped_logs)
    reply_log["total_skipped"] = reply_log.get("total_skipped", 0) + len(skipped_logs)

    os.makedirs("logs", exist_ok=True)

    # ✅ SAVE to SHARED files
    replied_data["replied"] = list(replied_ids)[-10000:]
    replied_data["last_updated"] = now_ist_ampm()
    try:
        with open(SHARED_REPLIED_IDS, 'w', encoding='utf-8') as f:
            json.dump(replied_data, f, indent=2)
        log(f"💾 Saved {len(replied_data['replied'])} IDs to {SHARED_REPLIED_IDS}")
    except Exception as e:
        log(f"⚠️ replied_file save error: {e}")

    reply_log["replies"] = reply_log.get("replies", [])[-500:]
    reply_log["skipped"] = reply_log.get("skipped", [])[-200:]
    reply_log["last_updated"] = now_ist_ampm()
    try:
        with open(SHARED_REPLY_LOG, 'w', encoding='utf-8') as f:
            json.dump(reply_log, f, indent=2, ensure_ascii=False)
        log(f"💾 Shared log updated: {SHARED_REPLY_LOG}")
    except Exception as e:
        log(f"⚠️ reply_log save error: {e}")

    log(f"🤖 FB Auto-reply done. {replies_count} new replies. "
        f"Total in SHARED history: {len(reply_log.get('replies', []))}")
    return reply_log


# ============================================================
# 📊 DASHBOARD
# ============================================================
def update_dashboard_inline():
    log("\n" + "=" * 60)
    log("📊 DASHBOARD UPDATE")
    log("=" * 60)

    links_dir = "game_links_editor"
    os.makedirs("logs", exist_ok=True)

    if not os.path.exists(links_dir):
        log("⚠️ No game_links_editor — dashboard skip")
        return

    all_files = glob.glob(os.path.join(links_dir, "*.txt"))
    all_files = [f for f in all_files
                 if any(k in f for k in ("_uploaded_links", "_links_editor", "_posted_links"))]
    valid_files = [f for f in all_files if os.path.exists(f)]

    game_list, file_mapping = [], {}
    for f in valid_files:
        g = (os.path.basename(f)
             .replace("_uploaded_links.txt", "")
             .replace("_links_editor.txt", "")
             .replace("_posted_links_editor.txt", "")
             .replace(".txt", "").strip())
        if g:
            file_mapping[g] = f
            game_list.append(g)
    game_list = sorted(set(game_list))
    log(f"📁 {len(game_list)} games")

    memory = {}
    if os.path.exists("logs/agent_memory.json"):
        try:
            with open("logs/agent_memory.json", 'r', encoding='utf-8') as f:
                memory = json.load(f)
            log(f"✅ Loaded agent_memory.json")
        except Exception as e:
            log(f"⚠️ Memory read error: {e}")

    actual_posted_titles = memory.get("actual_posted_titles", {})
    game_stats = memory.get("game_stats", {})

    log(f"📊 Loaded {len(actual_posted_titles)} games from memory")

    game_views_summary = {}
    for g_name, videos in actual_posted_titles.items():
        total = 0
        for v in videos:
            total += v.get("fb_views", 0) + v.get("ig_views", 0)
        game_views_summary[g_name] = total

    if not actual_posted_titles:
        log("⚠️ Memory empty — fetching from FB")
        actual_posted_titles, game_views_summary = fetch_fb_ig_data(game_list)

    if not game_views_summary:
        game_views_summary = {g: 0 for g in game_list}

    try:
        detect_trending_games(actual_posted_titles, days=7)
    except Exception as e:
        log(f"⚠️ Trending error: {e}")
    try:
        analyze_best_time()
    except Exception as e:
        log(f"⚠️ Best time error: {e}")

    generate_dashboard_md(actual_posted_titles, game_views_summary, game_stats, file_mapping)


def fetch_fb_ig_data(game_list):
    result = {g: [] for g in game_list}
    game_views_summary = {g: 0 for g in game_list}

    if not FB_ACCESS_TOKEN:
        return result, game_views_summary

    since_ts = int((now_ist() - timedelta(days=DAYS_LIMIT)).timestamp())
    fb_videos, ig_medias = [], []
    try:
        res = requests.get(
            f"{FB_GRAPH_URL}/{FB_PAGE_ID}/videos",
            params={"fields": "id,title,description,views,permalink_url,created_time",
                    "since": since_ts, "access_token": FB_ACCESS_TOKEN, "limit": 100},
            timeout=20)
        if res.status_code == 200:
            fb_videos = res.json().get("data", [])
            log(f"✅ FB page: {len(fb_videos)} videos fetched")
    except Exception as e:
        log(f"❌ FB page fetch error: {e}")

    try:
        res_ig_acc = requests.get(
            f"{FB_GRAPH_URL}/{FB_PAGE_ID}",
            params={"fields": "instagram_business_account",
                    "access_token": FB_ACCESS_TOKEN},
            timeout=10)
        if res_ig_acc.status_code == 200:
            ig_id = res_ig_acc.json().get("instagram_business_account", {}).get("id")
            if ig_id:
                res_ig = requests.get(
                    f"{FB_GRAPH_URL}/{ig_id}/media",
                    params={"fields": "id,caption,permalink,timestamp,like_count,comments_count",
                            "access_token": FB_ACCESS_TOKEN, "limit": 100},
                    timeout=20)
                if res_ig.status_code == 200:
                    ig_medias = res_ig.json().get("data", [])
                    log(f"✅ IG: {len(ig_medias)} media fetched")
    except Exception as e:
        log(f"❌ IG fetch error: {e}")

    for game in game_list:
        game_norm = normalize(game)
        for v in fb_videos:
            title = (v.get("title") or v.get("description") or "").strip()
            if not title or not (game_norm and game_norm in normalize(title)):
                continue
            fb_vid_id = str(v.get("id", "")).strip()
            entry = {
                "title": title,
                "fb_link": fix_fb_url(v.get("permalink_url", ""), fb_vid_id),
                "fb_views": int(v.get("views", 0) or 0),
                "fb_posted": True, "ig_link": "", "ig_views": 0, "ig_posted": False,
                "timestamp": v.get("created_time", ""),
                "vid_id": fb_vid_id, "video_name": "",
                "source_link": "",
            }
            result[game].append(entry)
            game_views_summary[game] += entry["fb_views"]

        for m in ig_medias:
            caption = (m.get("caption") or "").strip()
            if not caption or not (game_norm and game_norm in normalize(caption)):
                continue
            ig_views = (m.get("like_count", 0) * 10) + (m.get("comments_count", 0) * 20)
            ig_media_id = str(m.get("id", "")).strip()
            result[game].append({
                "title": caption[:100], "fb_link": "", "fb_views": 0,
                "fb_posted": False,
                "ig_link": fix_ig_url(m.get("permalink", "")),
                "ig_views": ig_views, "ig_posted": True,
                "timestamp": m.get("timestamp", ""),
                "vid_id": ig_media_id, "video_name": "",
                "source_link": "",
            })
            game_views_summary[game] += ig_views

    for game in game_list:
        result[game].sort(key=lambda x: x.get("timestamp", "") or "0000", reverse=True)

    return result, game_views_summary


def detect_trending_games(actual_posted_titles, days=7):
    game_stats = {}
    for g_name, videos in actual_posted_titles.items():
        total_views, video_count = 0, 0
        latest_post, latest_fb_link = "", ""
        for v in videos:
            if not (v.get("fb_posted") or v.get("ig_posted")):
                continue
            ts = v.get("timestamp", "")
            if not ts:
                continue
            dt = utc_to_ist(ts)
            if dt and (now_ist() - dt).days > days:
                continue
            views = v.get("fb_views", 0) + v.get("ig_views", 0)
            total_views += views
            video_count += 1
            if ts > latest_post:
                latest_post = ts
                latest_fb_link = v.get("fb_link", "")
        if video_count > 0:
            game_stats[g_name] = {
                "total_views": total_views, "video_count": video_count,
                "avg_views": total_views // video_count,
                "latest_post": latest_post, "fb_link": latest_fb_link,
                "source_link": "",
            }

    if not game_stats:
        result = {"last_updated": now_ist_ampm(), "period_days": days,
                  "trending": [], "below_avg": [], "recommendation": None}
        os.makedirs("logs", exist_ok=True)
        with open("logs/trending_cache.json", 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2)
        return result

    all_avgs = [s["avg_views"] for s in game_stats.values()]
    overall_avg = sum(all_avgs) / len(all_avgs) if all_avgs else 1

    trending_list = []
    for g, s in game_stats.items():
        ratio = s["avg_views"] / overall_avg if overall_avg > 0 else 0
        if ratio >= 2.0:
            trend = "viral"
        elif ratio >= 1.5:
            trend = "trending"
        elif ratio >= 1.0:
            trend = "steady"
        elif ratio >= 0.5:
            trend = "slow"
        else:
            trend = "below_avg"
        trending_list.append({
            "game": g, "views_7d": s["total_views"],
            "avg_per_video": s["avg_views"], "trend": trend, "ratio": ratio,
            "fb_link": s["fb_link"], "source_link": s["source_link"],
        })

    trending_list.sort(key=lambda x: x["avg_per_video"], reverse=True)
    top = [t for t in trending_list if t["trend"] in ("viral", "trending", "steady")][:5]
    below = [t for t in trending_list if t["trend"] in ("slow", "below_avg")][:5]
    best = trending_list[0] if trending_list else None

    result = {"last_updated": now_ist_ampm(), "period_days": days,
              "trending": top, "below_avg": below, "recommendation": best}
    os.makedirs("logs", exist_ok=True)
    with open("logs/trending_cache.json", 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2)
    return result


def analyze_best_time():
    all_history = {}
    try:
        with open("logs/dashboard_history.json", 'r', encoding='utf-8') as f:
            all_history = json.load(f)
    except Exception:
        pass

    hourly, daily = {}, {}
    for game, entries in all_history.items():
        for entry in entries:
            ts = entry.get("timestamp", "")
            views = entry.get("views", 0)
            if not ts:
                continue
            dt = utc_to_ist(ts)
            if dt is None:
                continue
            hourly.setdefault(dt.hour, []).append(views)
            daily.setdefault(dt.strftime("%A"), []).append(views)

    hourly_stats = []
    for hour, views_list in hourly.items():
        if len(views_list) < 2:
            continue
        hourly_stats.append({
            "hour": hour, "posts": len(views_list),
            "avg_views": sum(views_list) // len(views_list),
        })
    hourly_stats.sort(key=lambda x: x["avg_views"], reverse=True)

    top_slots = []
    medals = ["🥇", "🥈", "🥉", "4", "5"]
    recs = ["BEST", "Great", "Good", "Average", "Below avg"]
    for idx, h in enumerate(hourly_stats[:5]):
        start = h["hour"]
        end = (start + 1) % 24
        top_slots.append({
            "rank": idx + 1,
            "icon": medals[idx] if idx < len(medals) else str(idx + 1),
            "time_slot": f"{start:02d}:00 - {end:02d}:00",
            "posts": h["posts"], "avg_views": h["avg_views"],
            "recommendation": recs[idx] if idx < len(recs) else "—",
        })

    daily_stats = {}
    for day, views_list in daily.items():
        if views_list:
            daily_stats[day] = {
                "avg_views": sum(views_list) // len(views_list),
                "posts": len(views_list),
            }

    result = {
        "last_updated": now_ist_ampm(),
        "total_posts_analyzed": sum(len(v) for v in hourly.values()),
        "top_slots": top_slots, "daily": daily_stats,
        "today_suggestion": top_slots[0] if top_slots else None,
    }
    os.makedirs("logs", exist_ok=True)
    with open("logs/best_time_analysis.json", 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2)
    return result


def generate_dashboard_md(actual_posted_titles, game_views_summary, game_stats, file_mapping):
    dashboard_path = "GAMING_DASHBOARD.md"

    total_views = sum(game_views_summary.values()) or 1
    analytics = []
    for g, v in game_views_summary.items():
        uploaded = game_stats.get(g, {}).get("uploaded_count", 0)
        avg = int(v / uploaded) if uploaded > 0 else 0
        share = round((v / total_views) * 100, 2)
        analytics.append({"game": g, "total_views": v, "uploaded_count": uploaded,
                          "avg_views": avg, "share_pct": share})
    analytics.sort(key=lambda x: x["total_views"], reverse=True)

    md = ["# 🚀 GAMING AGENT DASHBOARD\n\n",
          f"> **Last Updated:** {now_ist_ampm()} IST | **Status:** Active\n\n"]

    md.append("--- \n\n## 🏆 Global Leaderboard\n\n")
    md.append("| Rank | Game | Videos | Views | Avg/Video | Tier |\n")
    md.append("|:---:|---|---|---|---|---|\n")
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    for idx, item in enumerate(analytics):
        rank = medals[idx] if idx < len(medals) else f"{idx+1}"
        tier = "🔥 Viral" if item["avg_views"] > 7000 else ("⚡ Trending" if item["avg_views"] > 4000 else "📈 Stable")
        md.append(f"| {rank} | **{item['game']}** | {item['uploaded_count']} | "
                  f"{item['total_views']:,} | {item['avg_views']:,} | {tier} |\n")

    md.append("\n--- \n\n## 📺 Live Post Titles + Views (Latest per Game)\n\n")
    md.append("> 🔵 FB = Facebook live | 🟣 IG = Instagram live | ⏳ = Pending\n\n")
    md.append("| Game Name | 📅 Last Posted | 📺 Latest Title | 🔵 FB | 👁️ FB Views | "
              "🟣 IG | 👁️ IG Views | 📊 Remaining / Total | 📂 Source | 📜 All |\n")
    md.append("|---|---|---|---|---|---|---|---|---|---|\n")

    def get_latest_post_time(g_name):
        latest = ""
        for v in actual_posted_titles.get(g_name, []):
            if v.get("fb_posted") or v.get("ig_posted"):
                ts = v.get("timestamp", "")
                if ts > latest:
                    latest = ts
        return latest

    sorted_games = sorted(actual_posted_titles.keys(),
                          key=lambda g: get_latest_post_time(g) or "0000",
                          reverse=True)

    source_links_map, _, _ = load_source_data()
    games_dir = "logs/games"
    os.makedirs(games_dir, exist_ok=True)

    for g_name in sorted_games:
        videos = actual_posted_titles.get(g_name, [])
        src_file = file_mapping.get(g_name, "")

        total_vids = len(videos)
        if src_file and os.path.exists(src_file):
            try:
                with open(src_file, 'r', encoding='utf-8', errors='ignore') as f:
                    c = f.read()
                pipe_count = len(re.findall(r'\|\s*Link:', c))
                total_vids = max(pipe_count, total_vids, len(extract_urls(c)))
            except Exception:
                pass

        uploaded_vids = game_stats.get(g_name, {}).get("uploaded_count", 0)
        remaining_vids = max(0, total_vids - uploaded_vids)
        if total_vids > 0:
            progress_md = f"**{remaining_vids}** / {total_vids}"
            if remaining_vids == 0:
                progress_md = f"✅ {total_vids} / {total_vids}"
        else:
            progress_md = "_N/A_"

        latest_post_time = get_latest_post_time(g_name)
        if latest_post_time:
            dt_ist = utc_to_ist(latest_post_time)
            if dt_ist:
                date_str = dt_ist.strftime("%Y-%m-%d %I:%M %p")
            else:
                date_str = str(latest_post_time)[:16]
        else:
            date_str = "—"

        if not videos:
            md.append(f"| **{g_name}** | {date_str} | _Not Posted Yet_ | ⏳ Pending | "
                      f"_0_ | ⏳ Pending | _0_ | {progress_md} | _N/A_ | — |\n")
            continue

        latest_posted = None
        latest_ts = ""
        for v in videos:
            if v.get("fb_posted") or v.get("ig_posted"):
                ts = v.get("timestamp", "")
                if ts > latest_ts:
                    latest_ts = ts
                    latest_posted = v

        latest = latest_posted if latest_posted else videos[0]
        title = (latest.get("title") or "").replace("\n", " ").replace("|", "\\|")[:80] or "_Untitled_"
        fb_md = f"[🔵 FB]({latest['fb_link']})" if latest.get("fb_posted") and latest.get("fb_link") else "⏳ Pending"
        fb_v_md = f"{latest.get('fb_views', 0):,}" if latest.get("fb_posted") else "_0_"
        ig_md = f"[🟣 IG]({latest['ig_link']})" if latest.get("ig_posted") and latest.get("ig_link") else "⏳ Pending"
        ig_v_md = f"{latest.get('ig_views', 0):,}" if latest.get("ig_posted") else "_0_"

        src_link = latest.get("source_link", "") or (videos[0].get("source_link", "") if videos else "")
        if not src_link:
            src_urls = source_links_map.get(g_name, [])
            src_link = src_urls[0] if src_urls else ""
        src_md = f"[📂]({src_link})" if src_link else "_N/A_"

        safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', g_name)
        game_file_link = f"logs/games/{safe_name}.md"
        all_md = f"**[📜 View {len(videos)}]({game_file_link})**"

        md.append(f"| **{g_name}** | {date_str} | {title} | {fb_md} | {fb_v_md} | "
                  f"{ig_md} | {ig_v_md} | {progress_md} | {src_md} | {all_md} |\n")

    md.append("\n--- \n\n## 📈 Trending Games (Last 7 Days)\n\n")
    try:
        with open("logs/trending_cache.json", 'r', encoding='utf-8') as f:
            data = json.load(f)
        trending = data.get("trending", [])
        if trending:
            md.append("| Rank | Game | Views | Avg | Trend |\n|:---:|---|---|---|---|\n")
            for idx, t in enumerate(trending, 1):
                md.append(f"| {idx} | **{t['game']}** | {t['views_7d']:,} | "
                          f"{t['avg_per_video']:,} | {t['trend']} |\n")
    except Exception:
        md.append("_No data_\n")

    md.append("\n--- \n\n## 🎯 Best Time to Post\n\n")
    try:
        with open("logs/best_time_analysis.json", 'r', encoding='utf-8') as f:
            data = json.load(f)
        slots = data.get("top_slots", [])
        if slots:
            md.append("| Rank | Time | Avg Views |\n|:---:|---|---|\n")
            for s in slots:
                md.append(f"| {s['icon']} | **{s['time_slot']}** | {s['avg_views']:,} |\n")
    except Exception:
        md.append("_No data_\n")

    md.append("\n--- \n\n## 🤖 Auto-Reply Log (SHARED)\n\n")
    try:
        with open(SHARED_REPLY_LOG, 'r', encoding='utf-8') as f:
            data = json.load(f)
        md.append(f"> Total: {data.get('total_replies', 0)} | "
                  f"Skipped: {data.get('total_skipped', 0)} | "
                  f"Last: {data.get('last_updated', 'N/A')}\n\n")
        replies = data.get("replies", [])
        if replies:
            md.append("| # | Time | User | Comment | AI Reply | Depth |\n")
            md.append("|---|---|---|---|---|---|\n")
            for idx, r in enumerate(list(reversed(replies[-20:])), 1):
                un = (r.get("user_name", "?") or "?").replace("|", "\\|")[:20]
                cm = (r.get("user_comment", "") or "").replace("\n", " ").replace("|", "\\|")[:50]
                rp = (r.get("openrouter_reply", "") or "").replace("\n", " ").replace("|", "\\|")[:70]
                ts = r.get("timestamp", "")[:20]
                d = r.get("depth", 1)
                md.append(f"| {idx} | {ts} | **{un}** | {cm} | {rp} | {d} |\n")
    except Exception:
        md.append("_No data_\n")

    md.append("\n--- \n\n## 🔄 Game Rotation Queue (Read-Only)\n\n")
    rotation_file = "logs/rotation_history.json"
    if os.path.exists(rotation_file):
        try:
            with open(rotation_file, 'r', encoding='utf-8') as f:
                rot = json.load(f)
            md.append(f"**🎯 Current:** `{rot.get('current_game', 'N/A')}` | "
                      f"**⏭️ Next:** `{rot.get('next_game', 'N/A')}` | "
                      f"**🔢 Runs:** {rot.get('total_runs', 0)}\n\n")
            md.append("| # | Game | Uploaded | Next Turn | Status |\n")
            md.append("|:---:|---|:---:|:---:|:---:|\n")
            for g in rot.get("all_games", []):
                status = g.get("status", "waiting")
                status_md = ("🎯 **CURRENT**" if status == "current"
                             else "⏭️ **NEXT UP**" if status == "next_up"
                             else f"⏳ Wait {g.get('next_turn_in', 0)}")
                md.append(f"| {g.get('position', 0)} | **{g.get('game', '')}** | "
                          f"{g.get('uploaded', 0)} | {g.get('next_turn_in', 0)} | {status_md} |\n")
        except Exception as e:
            md.append(f"_Error: {e}_\n")
    else:
        md.append("_No rotation data_\n")

    md.append("\n--- \n\n## 📜 Full Video History\n\n")
    for g_name in sorted_games:
        videos = actual_posted_titles.get(g_name, [])
        if videos:
            safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', g_name)
            md.append(f"- **🎮 {g_name}** — {len(videos)} videos — [📜 View All](logs/games/{safe_name}.md)\n")

    with open(dashboard_path, 'w', encoding='utf-8') as f:
        f.writelines(md)

    log(f"✅ Dashboard written: {dashboard_path}")

    git_commit_and_push([
        dashboard_path,
        SHARED_REPLY_LOG,
        SHARED_REPLIED_IDS,
        "logs/trending_cache.json",
        "logs/best_time_analysis.json",
        "logs/games/",
    ])


def git_commit_and_push(file_paths, message="Auto-Agent: Update dashboard [skip ci]"):
    try:
        subprocess.run(["git", "config", "--global", "user.name", "github-actions[bot]"],
                       check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "config", "--global", "user.email",
                        "41898282+github-actions[bot]@users.noreply.github.com"],
                       check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for path in file_paths:
            if os.path.exists(path):
                subprocess.run(["git", "add", path], check=False,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        c = subprocess.run(["git", "commit", "-m", message],
                           capture_output=True, text=True, check=False)
        log(f"🔄 Git Commit: {c.stdout.strip()} {c.stderr.strip()}")
        subprocess.run(["git", "pull", "--rebase", "origin", "main"],
                       capture_output=True, text=True, check=False)
        p = subprocess.run(["git", "push"], capture_output=True, text=True, check=False)
        log(f"🔄 Git Push: {p.stdout.strip()} {p.stderr.strip()}")
    except Exception as e:
        log(f"⚠️ Git auto-push error: {e}")


# ============================================================
# 🚀 MAIN
# ============================================================
def main():
    log("=" * 60)
    log("🚀 SPLIT SCRIPT v6 — Shared Log Fix")
    log("=" * 60)
    log(f"📂 Shared log: {SHARED_REPLY_LOG}")
    log(f"📂 Shared IDs: {SHARED_REPLIED_IDS}")

    if AUTO_COMMENT_ENABLED:
        try:
            process_fb_comments()
        except Exception as e:
            log(f"⚠️ Auto-reply error: {e}")
    else:
        log("🚫 Auto-comment disabled")

    try:
        update_dashboard_inline()
    except Exception as e:
        log(f"⚠️ Dashboard error: {e}")

    log(f"\n{'=' * 60}")
    log(f"✅ DONE — {now_ist_ampm()} IST")
    log(f"{'=' * 60}")


if __name__ == "__main__":
    try:
        main()
        log("✅ Completed successfully — exiting")
        sys.exit(0)
    except KeyboardInterrupt:
        log("⚠️ Interrupted by user")
        sys.exit(130)
    except Exception as e:
        log(f"❌ FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)