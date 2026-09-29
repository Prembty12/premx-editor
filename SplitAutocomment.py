"""
💬 SPLIT AUTO-COMMENT SCRIPT (FINAL — Duplicate Bug Fixed)
============================================================
✅ Auto-comment upgraded (username, 3-level, 10 batch)
✅ Dashboard update (rotation read-only)
✅ 🔥 DUPLICATE FIX:
   - Log check PEHLE (always)
   - replied_ids.add() har reply ke baad
   - reply_id fallback (synthetic)
   - FB reply_id check
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


def parse_game_links_file(filepath):
    videos = []
    if not filepath or not os.path.exists(filepath):
        return videos
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        for line in content.split('\n'):
            line = line.strip()
            if not line:
                continue
            if '| Link:' in line:
                parts = line.split('| Link:')
                video_name = parts[0].strip()
                link = parts[1].strip() if len(parts) > 1 else ""
                url_match = re.search(r'(https?://[^\s\n\r\)\]\'"<>,;]+)', link)
                if url_match:
                    link = url_match.group(1).rstrip('.,;)\']"')
                if video_name:
                    videos.append({"video_name": video_name, "source_link": link})
        if not videos:
            urls = extract_urls(content)
            for idx, u in enumerate(urls, 1):
                videos.append({"video_name": f"Video_{idx}", "source_link": u})
    except Exception as e:
        log(f"⚠️ parse_game_links_file error: {e}")
    return videos


def parse_posted_file(filepath, game_name):
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    posts, current_video = [], {}
    for line in content.split('\n'):
        line = line.strip()
        if not line:
            continue
        if '| Link:' in line:
            if current_video.get('vid_id'):
                posts.append(current_video)
            link_part = line.split('| Link:')[-1].strip()
            video_name = line.split('| Link:')[0].strip()
            current_video = {
                'vid_id': None, 'title': None, 'link': link_part,
                'video_name': video_name, 'platform': 'FB + IG', 'game': game_name,
            }
        elif 'Video id :' in line:
            current_video['vid_id'] = line.split('Video id :')[-1].strip()
        elif 'Title :' in line:
            current_video['title'] = line.split('Title :')[-1].strip()
    if current_video.get('vid_id'):
        posts.append(current_video)
    return posts


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
MAX_COMMENT_AGE_HOURS = 720
POSTS_TO_SCAN = 25
COMMENT_FETCH_WORKERS = 10
MAX_JSON_RETRIES = 12

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
1. Reply in the SAME language as the comment (English/Hinglish only, no regional languages).
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
# 💬 AUTO-COMMENT (DUPLICATE-PROOF)
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
    """Load comment_id → depth AND reply_id → depth from log."""
    global _replied_history_cache
    if _replied_history_cache is not None:
        return _replied_history_cache
    _replied_history_cache = {}
    reply_log_file = "logs/auto_reply_log.json"
    if os.path.exists(reply_log_file):
        try:
            with open(reply_log_file, 'r', encoding='utf-8') as f:
                log_data = json.load(f)
            for r in log_data.get("replies", []):
                cid = r.get("comment_id", "")
                rid = r.get("reply_id", "")
                r_to = r.get("reply_to_id", "")
                depth = r.get("depth", 1)
                if cid:
                    _replied_history_cache[cid] = max(
                        _replied_history_cache.get(cid, 0), depth)
                if rid:
                    _replied_history_cache[rid] = max(
                        _replied_history_cache.get(rid, 0), depth)
                if r_to:
                    _replied_history_cache[r_to] = max(
                        _replied_history_cache.get(r_to, 0), depth)
        except Exception:
            pass
    return _replied_history_cache


def was_already_replied(comment_id):
    """Check both log files."""
    if not comment_id:
        return False
    # Check 1: auto_reply_log.json
    if comment_id in load_replied_history():
        return True
    # Check 2: replied_comment_ids.json
    replied_file = "logs/replied_comment_ids.json"
    if os.path.exists(replied_file):
        try:
            with open(replied_file, 'r', encoding='utf-8') as f:
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


def fetch_comment_replies(comment_id):
    params = {
        "fields": "id,message,from{name,id},created_time,can_reply",
        "access_token": FB_ACCESS_TOKEN,
        "limit": 50,
    }
    try:
        res = requests.get(f"{FB_GRAPH_URL}/{comment_id}/comments",
                           params=params, timeout=15)
        if res.status_code == 200:
            return res.json().get("data", [])
    except Exception:
        pass
    return []


def post_fb_reply(comment_id, reply_text):
    """Post reply — with synthetic fallback ID."""
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
            # FB API ne ID nahi di — synthetic banao
            log(f"⚠️ FB API no reply_id — using synthetic")
            return f"synth_{comment_id}_{int(time.time())}"
        log(f"⚠️ Reply post error ({res.status_code}): {res.text[:200]}")
    except Exception as e:
        log(f"⚠️ Reply post exception: {e}")
    return None


def analyze_thread(top_comment):
    """
    ✅ FIXED — Log check FIRST (always), then FB API.
    """
    cid = top_comment.get("id", "")

    # 🛡️ LAYER 1: LOG CHECK — SABSE PEHLE (always)
    if was_already_replied(cid):
        history_depth = load_replied_history().get(cid, 1)
        log(f"      ⏭️ SKIP — comment_id already in log")
        return {
            "should_reply": False,
            "depth": history_depth,
            "reason": "already_replied_log",
        }

    # 🛡️ LAYER 2: FB API se replies fetch
    replies = fetch_comment_replies(cid)
    replies_sorted = sorted(replies, key=lambda x: x.get("created_time", ""))

    # 🛡️ LAYER 3: FB reply_ids log mein check karo
    history = load_replied_history()
    for r in replies_sorted:
        r_id = r.get("id", "")
        if r_id and r_id in history:
            log(f"      ⏭️ SKIP — FB reply_id in log")
            return {
                "should_reply": False,
                "depth": history.get(r_id, 1),
                "reason": "already_replied_log_reply_id",
            }

    # 🛡️ LAYER 4: Page name se our/user classify
    page_name = get_page_name()
    page_name_lower = page_name.lower() if page_name else ""

    our_replies, user_replies = [], []
    for r in replies_sorted:
        r_from = r.get("from", {}) or {}
        r_id = r_from.get("id", "")
        r_name = (r_from.get("name") or "").strip().lower()
        is_ours = (r_id == FB_PAGE_ID
                   or (page_name_lower and r_name == page_name_lower))
        if is_ours:
            our_replies.append(r)
        else:
            user_replies.append(r)

    our_count = len(our_replies)

    if len(replies_sorted) == 0:
        log(f"      🆕 Fresh comment — will reply")
    elif our_count >= MAX_CONVERSATION_DEPTH:
        return {"should_reply": False, "depth": our_count, "reason": "max_depth"}
    elif our_count > 0 and len(user_replies) == 0:
        return {"should_reply": False, "depth": our_count, "reason": "waiting_user"}
    elif our_count > 0 and len(user_replies) > 0:
        last = replies_sorted[-1]
        last_from = last.get("from", {}) or {}
        last_id = last_from.get("id", "")
        last_name = (last_from.get("name") or "").strip().lower()
        last_is_ours = (last_id == FB_PAGE_ID
                        or (page_name_lower and last_name == page_name_lower))
        if last_is_ours:
            return {"should_reply": False, "depth": our_count, "reason": "waiting_user"}
        log(f"      💬 User replied — continuing (depth {our_count})")
    elif our_count == 0 and len(user_replies) > 0:
        log(f"      ⚠️ User replied but no ours — will reply")

    thread_ctx = ""
    for r in replies_sorted[-6:]:
        r_from = r.get("from", {}) or {}
        r_id = r_from.get("id", "")
        r_name = (r_from.get("name") or "").strip().lower()
        is_us = (r_id == FB_PAGE_ID
                 or (page_name_lower and r_name == page_name_lower))
        who = "US" if is_us else "USER"
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

    log("🤖 Auto-reply started (duplicate-proof v3)...")

    page_name = get_page_name()
    log(f"📄 Page name: {page_name or 'N/A'}")

    # Load state
    replied_file = "logs/replied_comment_ids.json"
    replied_data = {"replied": [], "last_updated": ""}
    if os.path.exists(replied_file):
        try:
            with open(replied_file, 'r', encoding='utf-8') as f:
                replied_data = json.load(f)
        except Exception:
            pass
    replied_ids = set(replied_data.get("replied", []))

    reply_log_file = "logs/auto_reply_log.json"
    reply_log = {"total_replies": 0, "total_skipped": 0, "replies": [], "skipped": []}
    if os.path.exists(reply_log_file):
        try:
            with open(reply_log_file, 'r', encoding='utf-8') as f:
                reply_log = json.load(f)
            log(f"📂 Existing history: {len(reply_log.get('replies', []))} replies")
        except Exception:
            pass

    # ✅ Load log into replied_ids (synced)
    history = load_replied_history()
    log(f"📂 Replied history cache: {len(history)} IDs")
    for hid in history.keys():
        replied_ids.add(hid)

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
                if state["reason"] in ("max_depth", "waiting_user", "already_replied_log", "already_replied_log_reply_id"):
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
                "fb_link": post.get("permalink_url", f"https://www.facebook.com/{post_id}"),
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
            # ✅ CRITICAL FIX: replied_ids mein add karo
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

    # ✅ SAVE replied_ids (all IDs)
    replied_data["replied"] = list(replied_ids)[-10000:]
    replied_data["last_updated"] = now_ist_ampm()
    try:
        with open(replied_file, 'w', encoding='utf-8') as f:
            json.dump(replied_data, f, indent=2)
        log(f"💾 Saved {len(replied_data['replied'])} IDs to replied_comment_ids.json")
    except Exception as e:
        log(f"⚠️ replied_file save error: {e}")

    reply_log["replies"] = reply_log.get("replies", [])[-500:]
    reply_log["skipped"] = reply_log.get("skipped", [])[-200:]
    reply_log["last_updated"] = now_ist_ampm()
    try:
        with open(reply_log_file, 'w', encoding='utf-8') as f:
            json.dump(reply_log, f, indent=2, ensure_ascii=False)
    except Exception as e:
        log(f"⚠️ reply_log save error: {e}")

    log(f"🤖 FB Auto-reply done. {replies_count} new replies. "
        f"Total in history: {len(reply_log.get('replies', []))}")
    return reply_log


# ============================================================
# 📊 DASHBOARD UPDATE
# ============================================================
def update_dashboard():
    try:
        from game_analytics import AnalyticsEngine
    except ImportError:
        log("ℹ️ game_analytics not found — using inline dashboard logic")
        update_dashboard_inline()
        return
    # If game_analytics exists, use it
    log("📊 Using game_analytics.py")


def update_dashboard_inline():
    """Inline dashboard — no external import needed."""
    log("\n" + "=" * 60)
    log("📊 DASHBOARD UPDATE (inline)")
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

    # Fetch FB/IG data
    actual_posted_titles, game_views_summary = fetch_fb_ig_data(game_list)
    if not game_views_summary:
        game_views_summary = {g: 0 for g in game_list}

    # Trending + Best time
    try:
        detect_trending_games(actual_posted_titles, days=7)
    except Exception as e:
        log(f"⚠️ Trending error: {e}")
    try:
        analyze_best_time()
    except Exception as e:
        log(f"⚠️ Best time error: {e}")

    memory = {}
    if os.path.exists("logs/agent_memory.json"):
        try:
            with open("logs/agent_memory.json", 'r', encoding='utf-8') as f:
                memory = json.load(f)
        except Exception:
            pass
    game_stats = memory.get("game_stats", {})

    generate_dashboard_md(actual_posted_titles, game_views_summary, game_stats, file_mapping)


def fetch_fb_ig_data(game_list):
    """Simplified FB/IG data fetch."""
    posted_dir = 'posted_links_editor'
    result = {g: [] for g in game_list}
    game_views_summary = {g: 0 for g in game_list}

    if not FB_ACCESS_TOKEN:
        log("⚠️ FB_ACCESS_TOKEN missing")
        return result, game_views_summary

    # Fetch FB page videos
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

    # Map to games
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

    # Sort: posted first
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
    """Generate dashboard MD."""
    dashboard_path = "GAMING_DASHBOARD.md"

    # Analytics
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
          f"> **Last Updated:** {now_ist_ampm()} IST | **Status:** Active\n\n",
          "--- \n\n## 🏆 Global Leaderboard\n\n",
          "| Rank | Game | Videos | Views | Avg/Video | Tier |\n",
          "|:---:|---|---|---|---|---|\n"]
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    for idx, item in enumerate(analytics):
        rank = medals[idx] if idx < len(medals) else f"{idx+1}"
        tier = "🔥 Viral" if item["avg_views"] > 7000 else ("⚡ Trending" if item["avg_views"] > 4000 else "📈 Stable")
        md.append(f"| {rank} | **{item['game']}** | {item['uploaded_count']} | "
                  f"{item['total_views']:,} | {item['avg_views']:,} | {tier} |\n")

    # Trending
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

    # Best time
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

    # Auto-reply log
    md.append("\n--- \n\n## 🤖 Auto-Reply Log\n\n")
    try:
        with open("logs/auto_reply_log.json", 'r', encoding='utf-8') as f:
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

    # Rotation (read-only)
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

    # Full video history
    md.append("\n--- \n\n## 📜 Full Video History\n\n")
    for g_name in sorted(actual_posted_titles.keys()):
        videos = actual_posted_titles.get(g_name, [])
        if videos:
            md.append(f"- **🎮 {g_name}** — {len(videos)} videos\n")

    with open(dashboard_path, 'w', encoding='utf-8') as f:
        f.writelines(md)

    log(f"✅ Dashboard written: {dashboard_path}")

    # Git commit
    git_commit_and_push([
        dashboard_path,
        "logs/auto_reply_log.json",
        "logs/replied_comment_ids.json",
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
    log("🚀 SPLIT AUTO-COMMENT — v3 (Duplicate Fixed)")
    log("=" * 60)

    # STEP 1: Auto-comment
    if AUTO_COMMENT_ENABLED:
        try:
            process_fb_comments()
        except Exception as e:
            log(f"⚠️ Auto-reply error: {e}")
    else:
        log("🚫 Auto-comment disabled")

    # STEP 2: Dashboard
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