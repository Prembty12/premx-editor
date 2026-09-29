"""
💬 SPLIT AUTO-COMMENT SCRIPT (UPGRADED — No Rotation Write)
=============================================================
✅ Auto-comment upgraded (username, 3-level, 10 batch)
✅ Dashboard update (reads rotation_history.json — READ ONLY)
✅ Trending, Best time, Charts
❌ NO rotation write — rotation_history.json NOT updated
❌ NO current/next game change
❌ NO game selection
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

# Optional heavy deps
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

try:
    from reportlab.lib.pagesizes import letter  # noqa
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle  # noqa
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle  # noqa
    from reportlab.lib import colors  # noqa
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


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
# HELPERS
# ============================================================
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
# 🤖 OPENROUTER
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
5. Sound like a real person, not a robot. No "I appreciate", "Thank you for your feedback", etc.
6. Match the vibe of the comment — hype if they hype, chill if they chill, roast if they roast.
7. Make them WANT to reply back. Ask something, joke, tease, hype, or challenge — based on what fits the comment naturally.
8. If comment asks game name → tell the game name.
9. If comment is abusive → savage witty comeback, no abuse back, no crying, stay chill.
10. If there's a "Conversation So Far" — continue naturally, don't repeat.

Use caption + hashtags for context if needed. Never share links. Never insult family/religion/caste.

CRITICAL: Return ONLY valid JSON. Keys = comment IDs. Values = reply text. No extra text, no markdown.

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
# 🚫 ABUSE / SPAM
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
# 💬 AUTO-COMMENT (UPGRADED)
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
                depth = r.get("depth", 1)
                if cid:
                    _replied_history_cache[cid] = max(
                        _replied_history_cache.get(cid, 0), depth)
                if rid:
                    _replied_history_cache[rid] = max(
                        _replied_history_cache.get(rid, 0), depth)
        except Exception:
            pass
    return _replied_history_cache

def was_already_replied(comment_id):
    return comment_id in load_replied_history()

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
            return res.json().get("id")
        log(f"⚠️ Reply post error ({res.status_code}): {res.text[:200]}")
    except Exception as e:
        log(f"⚠️ Reply post exception: {e}")
    return None

def analyze_thread(top_comment):
    cid = top_comment.get("id", "")
    replies = fetch_comment_replies(cid)
    replies_sorted = sorted(replies, key=lambda x: x.get("created_time", ""))

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
        if was_already_replied(cid):
            return {"should_reply": False,
                    "depth": load_replied_history().get(cid, 1),
                    "reason": "already_replied_log"}
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
        if was_already_replied(cid):
            return {"should_reply": False, "depth": 0, "reason": "already_replied_log"}
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
        "should_reply": True, "depth": our_count, "reason": "ok",
        "reply_to_id": last_user.get("id") or cid,
        "reply_to_text": last_text,
        "user_id": user_id, "user_name": user_name,
        "thread_context": thread_ctx,
    }

def process_fb_comments():
    if not AUTO_COMMENT_ENABLED:
        log("🚫 Auto-comment disabled")
        return None

    log("🤖 Auto-reply started (upgraded)...")
    page_name = get_page_name()
    log(f"📄 Page name: {page_name or 'N/A'}")

    replied_history = load_replied_history()
    log(f"📂 Loaded {len(replied_history)} replied IDs from log")

    reply_log = {"total_replies": 0, "total_skipped": 0,
                 "replies": [], "skipped": []}
    if os.path.exists("logs/auto_reply_log.json"):
        try:
            with open("logs/auto_reply_log.json", 'r', encoding='utf-8') as f:
                reply_log = json.load(f)
            log(f"📂 Existing history: {len(reply_log.get('replies', []))} replies")
        except Exception:
            pass

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
    permanent_skip_ids = set()

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

            state = analyze_thread(comment)
            if not state["should_reply"]:
                if state["reason"] in ("max_depth", "waiting_user", "already_replied_log"):
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
            log(f"✅ Posted [depth {c['current_depth'] + 1}] {cid[:20]} → user={c['user_name']}")
            log(f"   💬 {c['comment_text'][:80]}")
            log(f"   🤖 {reply_text[:80]}")
        else:
            log(f"❌ Failed to post for {cid}")

    reply_log["skipped"].extend(skipped_logs)
    reply_log["total_skipped"] = reply_log.get("total_skipped", 0) + len(skipped_logs)

    os.makedirs("logs", exist_ok=True)
    reply_log["replies"] = reply_log.get("replies", [])[-500:]
    reply_log["skipped"] = reply_log.get("skipped", [])[-200:]
    reply_log["last_updated"] = now_ist_ampm()
    try:
        with open("logs/auto_reply_log.json", 'w', encoding='utf-8') as f:
            json.dump(reply_log, f, indent=2, ensure_ascii=False)
    except Exception as e:
        log(f"⚠️ reply_log save error: {e}")

    try:
        with open("logs/replied_comment_ids.json", 'w', encoding='utf-8') as f:
            json.dump({
                "replied": list(permanent_skip_ids)[-5000:],
                "last_updated": now_ist_ampm(),
            }, f, indent=2)
    except Exception as e:
        log(f"⚠️ replied_ids save error: {e}")

    log(f"🤖 FB Auto-reply done. {replies_count} new replies. "
        f"Total in history: {len(reply_log.get('replies', []))}")
    return reply_log


# ============================================================
# 📊 FETCH FB/IG DATA
# ============================================================
def fetch_fb_caption(vid_id):
    try:
        res = requests.get(
            f"{FB_GRAPH_URL}/{vid_id}",
            params={"fields": "description", "access_token": FB_ACCESS_TOKEN},
            timeout=5).json()
        caption = res.get('description', '').strip()
        if caption:
            return caption.split('\n')[0].strip()
    except Exception:
        pass
    return None

def fetch_fb_views_by_id(vid_id):
    try:
        res = requests.get(
            f"{FB_GRAPH_URL}/{vid_id}/video_insights",
            params={"access_token": FB_ACCESS_TOKEN},
            timeout=5).json()
        for metric in res.get('data', []):
            if metric.get('name') == 'total_video_views':
                return metric.get('values', [{}])[0].get('value', 0)
    except Exception:
        pass
    return 0

def fetch_fb_ig_data(game_list):
    posted_dir = 'posted_links_editor'
    result = {g: [] for g in game_list}
    game_views_summary = {g: 0 for g in game_list}

    if not FB_ACCESS_TOKEN:
        log("⚠️ FB_ACCESS_TOKEN missing")
        return result, game_views_summary

    id_to_source_map = {}
    if os.path.exists(posted_dir):
        for fname in os.listdir(posted_dir):
            if not fname.endswith('_posted_links_editor.txt'):
                continue
            try:
                with open(os.path.join(posted_dir, fname), 'r',
                          encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                for block in re.split(r'\n\s*\n', content):
                    block_id, block_link = "", ""
                    for bl in block.split('\n'):
                        bl = bl.strip()
                        if 'Video id :' in bl:
                            block_id = bl.split('Video id :')[-1].strip()
                        elif '| Link:' in bl:
                            lp = bl.split('| Link:')[-1].strip()
                            um = re.search(r'(https?://[^\s\n\r\)\]\'"<>,;]+)', lp)
                            if um:
                                block_link = um.group(1).rstrip('.,;)\']"')
                    if block_id and block_link:
                        id_to_source_map[block_id] = block_link
            except Exception as e:
                log(f"⚠️ ID map error {fname}: {e}")
    log(f"📋 ID→Source map: {len(id_to_source_map)} entries")

    if os.path.exists(posted_dir):
        cutoff_date = now_ist() - timedelta(days=DAYS_LIMIT)
        all_tasks = []
        for filename in os.listdir(posted_dir):
            if not filename.endswith('_posted_links_editor.txt'):
                continue
            game_name = filename.replace('_posted_links_editor.txt', '')
            if game_name not in game_list:
                continue
            filepath = os.path.join(posted_dir, filename)
            try:
                if datetime.fromtimestamp(os.path.getmtime(filepath), tz=IST) < cutoff_date:
                    continue
            except Exception:
                pass
            try:
                all_tasks.extend(parse_posted_file(filepath, game_name))
            except Exception as e:
                log(f"⚠️ Parse error {game_name}: {e}")

        if all_tasks:
            log(f"📊 Total {len(all_tasks)} videos processing (parallel)...")

            def process_video_task(post):
                vid_id = post.get('vid_id')
                if not vid_id:
                    return post
                fb_caption = fetch_fb_caption(vid_id)
                fb_views = fetch_fb_views_by_id(vid_id)
                if fb_caption:
                    title = fb_caption
                elif post.get('title'):
                    title = post['title']
                else:
                    title = post.get('video_name', '').replace('_', ' ').strip() or f"Video {vid_id[:8]}"
                post['title'] = title
                post['fb_views'] = fb_views
                post['fb_posted'] = bool(vid_id)
                post['fb_link'] = f"https://www.facebook.com/{vid_id}"
                return post

            with ThreadPoolExecutor(max_workers=10) as ex:
                futures = {ex.submit(process_video_task, p): p for p in all_tasks}
                for fut in as_completed(futures):
                    try:
                        r = fut.result()
                        game = r.get('game')
                        if game in result:
                            vid_id = str(r.get('vid_id', '')).strip()
                            matched = id_to_source_map.get(vid_id) or r.get('link', '')
                            result[game].append({
                                "title": r.get('title', 'Untitled'),
                                "fb_link": fix_fb_url(r.get('fb_link', ''), vid_id),
                                "fb_views": r.get('fb_views', 0),
                                "fb_posted": r.get('fb_posted', False),
                                "ig_link": "", "ig_views": 0, "ig_posted": False,
                                "timestamp": "", "vid_id": vid_id,
                                "video_name": r.get('video_name', ''),
                                "source_link": matched,
                            })
                            game_views_summary[game] += r.get('fb_views', 0)
                    except Exception as e:
                        log(f"⚠️ Process error: {e}")

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
        existing_titles = {normalize(v.get("title", ""))[:40] for v in result[game]}

        for v in fb_videos:
            title = (v.get("title") or v.get("description") or "").strip()
            if not title or not (game_norm and game_norm in normalize(title)):
                continue
            key = normalize(title)[:40]
            if key in existing_titles:
                continue
            fb_vid_id = str(v.get("id", "")).strip()
            entry = {
                "title": title,
                "fb_link": fix_fb_url(v.get("permalink_url", ""), fb_vid_id),
                "fb_views": int(v.get("views", 0) or 0),
                "fb_posted": True, "ig_link": "", "ig_views": 0, "ig_posted": False,
                "timestamp": v.get("created_time", ""),
                "vid_id": fb_vid_id, "video_name": "",
                "source_link": id_to_source_map.get(fb_vid_id, ""),
            }
            result[game].append(entry)
            game_views_summary[game] += entry["fb_views"]
            existing_titles.add(key)

        for m in ig_medias:
            caption = (m.get("caption") or "").strip()
            if not caption or not (game_norm and game_norm in normalize(caption)):
                continue
            caption_norm = normalize(caption)[:40]
            matched = False
            for v in result[game]:
                v_norm = normalize(v.get("title", ""))[:40]
                if v_norm and (v_norm[:20] in caption_norm or caption_norm[:20] in v_norm):
                    ig_views = (m.get("like_count", 0) * 10) + (m.get("comments_count", 0) * 20)
                    v["ig_link"] = fix_ig_url(m.get("permalink", ""))
                    v["ig_views"] = ig_views
                    v["ig_posted"] = True
                    game_views_summary[game] += ig_views
                    matched = True
                    break
            if not matched and caption_norm not in existing_titles:
                ig_views = (m.get("like_count", 0) * 10) + (m.get("comments_count", 0) * 20)
                ig_media_id = str(m.get("id", "")).strip()
                result[game].append({
                    "title": caption[:100], "fb_link": "", "fb_views": 0,
                    "fb_posted": False,
                    "ig_link": fix_ig_url(m.get("permalink", "")),
                    "ig_views": ig_views, "ig_posted": True,
                    "timestamp": m.get("timestamp", ""),
                    "vid_id": ig_media_id, "video_name": "",
                    "source_link": id_to_source_map.get(ig_media_id, ""),
                })
                game_views_summary[game] += ig_views
                existing_titles.add(caption_norm)

    games_links_dir = "game_links_editor"
    if os.path.exists(games_links_dir):
        for game in game_list:
            src_file = None
            for f in os.listdir(games_links_dir):
                if not f.endswith(".txt"):
                    continue
                base = (f.replace(".txt", "")
                         .replace("_links_editor", "")
                         .replace("_uploaded_links", ""))
                if base == game:
                    src_file = os.path.join(games_links_dir, f)
                    break
            if not src_file:
                for f in os.listdir(games_links_dir):
                    if f.endswith(".txt") and f.startswith(game):
                        src_file = os.path.join(games_links_dir, f)
                        break
            if not src_file or not os.path.exists(src_file):
                continue

            src_videos = parse_game_links_file(src_file)
            existing_vids_lower = {}
            for v in result[game]:
                vname = (v.get("vid_id") or "").lower()
                vtitle = (v.get("title") or "").lower()
                if vname:
                    existing_vids_lower[vname] = v
                if vtitle:
                    existing_vids_lower[vtitle[:30]] = v

            for sv in src_videos:
                vname_lower = sv["video_name"].lower()
                matched = False
                for key, v in list(existing_vids_lower.items()):
                    v_title_lower = (v.get("title") or "").lower()
                    v_vid_lower = (v.get("vid_id") or "").lower()
                    if (vname_lower == v_vid_lower
                        or vname_lower in v_title_lower
                        or v_title_lower[:20] == vname_lower[:20]
                        or (len(vname_lower) > 5 and vname_lower[-5:] in v_title_lower)):
                        if not v.get("source_link"):
                            v["source_link"] = sv["source_link"]
                        if not v.get("video_name"):
                            v["video_name"] = sv["video_name"]
                        matched = True
                        break
                if not matched:
                    result[game].append({
                        "title": sv["video_name"], "fb_link": "", "fb_views": 0,
                        "fb_posted": False, "ig_link": "", "ig_views": 0,
                        "ig_posted": False, "timestamp": "",
                        "vid_id": sv["video_name"], "video_name": sv["video_name"],
                        "source_link": sv["source_link"], "is_source_only": True,
                    })

    for game in game_list:
        posted_v = [x for x in result[game] if x.get("fb_posted") or x.get("ig_posted")]
        pending_v = [x for x in result[game] if not (x.get("fb_posted") or x.get("ig_posted"))]
        posted_v.sort(key=lambda x: x.get("timestamp", "") or "0000", reverse=True)

        def pkey(x):
            digits = re.findall(r'\d+', x.get("video_name") or x.get("vid_id") or "")
            if digits:
                try:
                    return (0, -int(digits[-1]))
                except ValueError:
                    pass
            return (1, x.get("video_name") or "")
        pending_v.sort(key=pkey)
        result[game] = posted_v + pending_v

    return result, game_views_summary


# ============================================================
# 📈 TRENDING + BEST TIME
# ============================================================
def detect_trending_games(actual_posted_titles, days=7):
    game_stats = {}
    for g_name, videos in actual_posted_titles.items():
        total_views, video_count = 0, 0
        latest_post, latest_fb_link, latest_source = "", "", ""
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
                latest_source = v.get("source_link", "")
        if video_count > 0:
            game_stats[g_name] = {
                "total_views": total_views, "video_count": video_count,
                "avg_views": total_views // video_count,
                "latest_post": latest_post, "fb_link": latest_fb_link,
                "source_link": latest_source,
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

def analyze_best_time(all_history=None):
    if not all_history:
        try:
            with open("logs/dashboard_history.json", 'r', encoding='utf-8') as f:
                all_history = json.load(f)
        except Exception:
            all_history = {}

    hourly, daily = {}, {}
    for game, entries in all_history.items():
        for entry in entries:
            ts = entry.get("timestamp", "")
            views = entry.get("views", 0)
            if not ts:
                continue
            dt = utc_to_ist(ts)
            if dt is None:
                for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %I:%M:%S %p"):
                    try:
                        dt = datetime.strptime(ts, fmt)
                        break
                    except Exception:
                        continue
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


# ============================================================
# 📊 DASHBOARD GENERATION
# ============================================================
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

def _generate_visual_reports(game_views_summary, game_stats):
    reports_dir = "logs/reports"
    os.makedirs(reports_dir, exist_ok=True)
    chart_path = os.path.join(reports_dir, "views_chart.png")
    total_platform_views = sum(game_views_summary.values()) or 1

    analytics_data = []
    for g_n, g_v in game_views_summary.items():
        uploaded_count = game_stats.get(g_n, {}).get("uploaded_count", 0)
        avg_views = int(g_v / uploaded_count) if uploaded_count > 0 else 0
        share_pct = round((g_v / total_platform_views) * 100, 2)
        analytics_data.append({
            "game": g_n, "total_views": g_v, "uploaded_count": uploaded_count,
            "avg_views": avg_views, "share_pct": share_pct,
        })
    sorted_analytics = sorted(analytics_data, key=lambda x: x["total_views"], reverse=True)

    if MATPLOTLIB_AVAILABLE and sorted_analytics:
        try:
            games = [i["game"] for i in sorted_analytics]
            total_v = [i["total_views"] for i in sorted_analytics]
            avg_v = [i["avg_views"] for i in sorted_analytics]
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
            ax1.bar(games, total_v, color='#4A90E2')
            ax1.set_title("Total Views Leaderboard", fontsize=12, fontweight='bold')
            ax1.set_ylabel("Views", fontsize=10, fontweight='bold')
            ax1.tick_params(axis='x', rotation=30)
            ax2.bar(games, avg_v, color='#50E3C2')
            ax2.set_title("Avg Views per Video", fontsize=12, fontweight='bold')
            ax2.set_ylabel("Avg Views / Video", fontsize=10, fontweight='bold')
            ax2.tick_params(axis='x', rotation=30)
            plt.suptitle("Advanced Gaming Performance Analytics", fontsize=14, fontweight='bold')
            plt.tight_layout()
            plt.savefig(chart_path, dpi=300)
            plt.close()
        except Exception as e:
            log(f"⚠️ Chart error: {e}")
    return sorted_analytics

def _generate_trending_section():
    try:
        with open("logs/trending_cache.json", 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return ""
    out = ["\n--- \n\n## 📈 Trending Games (Last 7 Days)\n\n",
           f"> Auto-detected | Last Updated: {data.get('last_updated', 'N/A')}\n\n"]
    trending = data.get("trending", [])
    if trending:
        out.append("| Rank | Game Name | Views (7d) | Avg / Video | Trend | FB Post | Source |\n")
        out.append("|:---:|---|---|---|---|---|---|\n")
        for idx, t in enumerate(trending, 1):
            medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
            rank_icon = medals[idx - 1] if idx <= 5 else str(idx)
            trend_icon = {"viral": "🚀 **VIRAL**", "trending": "🔥 Trending",
                          "steady": "⚡ Steady"}.get(t["trend"], "📈")
            fb_md = f"[🔵]({t['fb_link']})" if t.get("fb_link") else "_N/A_"
            src_md = f"[📂]({t['source_link']})" if t.get("source_link") else "_N/A_"
            out.append(f"| {rank_icon} | **{t['game']}** | {t['views_7d']:,} | "
                       f"{t['avg_per_video']:,} | {trend_icon} | {fb_md} | {src_md} |\n")
    below = data.get("below_avg", [])
    if below:
        out.append("\n### 📉 Below Average This Week\n\n| Game | Views (7d) | Avg |\n|---|---|---|\n")
        for b in below:
            out.append(f"| {b['game']} | {b['views_7d']:,} | {b['avg_per_video']:,} |\n")
    rec = data.get("recommendation")
    if rec:
        out.append(f"\n### 💡 Recommendation\n\n**Best game to post next:** "
                   f"🚀 **{rec['game']}** (Avg {rec['avg_per_video']:,} views/video)\n")
    return "".join(out)

def _generate_best_time_section():
    try:
        with open("logs/best_time_analysis.json", 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return ""
    out = ["\n--- \n\n## 🎯 Best Time to Post (IST)\n\n",
           f"> Analysis from {data.get('total_posts_analyzed', 0)} posts | "
           f"Last Updated: {data.get('last_updated', 'N/A')}\n\n"]
    slots = data.get("top_slots", [])
    if slots:
        out.append("| Rank | Time (IST) | Posts | Avg Views | Recommendation |\n")
        out.append("|:---:|---|:---:|:---:|---|\n")
        for s in slots:
            rec_icon = {"BEST": "🔥 **BEST**", "Great": "⚡ **Great**",
                        "Good": "✅ **Good**", "Average": "📊 Average",
                        "Below avg": "📉 Below avg"}.get(s["recommendation"], s["recommendation"])
            out.append(f"| {s['icon']} | **{s['time_slot']}** | {s['posts']} | "
                       f"**{s['avg_views']:,}** | {rec_icon} |\n")
    today = data.get("today_suggestion")
    if today:
        out.append(f"\n### 💡 Today's Suggestion\n\n"
                   f"**Aaj post karo:** ⏰ **{today['time_slot']} IST**\n")
    daily = data.get("daily", {})
    if daily:
        out.append("\n### 📅 Weekly Pattern\n\n| Day | Posts | Avg Views |\n|---|---|---|\n")
        for day in ["Monday", "Tuesday", "Wednesday", "Thursday",
                    "Friday", "Saturday", "Sunday"]:
            if day in daily:
                out.append(f"| {day} | {daily[day]['posts']} | {daily[day]['avg_views']:,} |\n")
    return "".join(out)

def _generate_auto_reply_section():
    try:
        with open("logs/auto_reply_log.json", 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return ""
    out = ["\n--- \n\n## 🤖 Auto-Reply Log (Upgraded v2)\n\n"]
    status = "🚫 **DISABLED**" if not AUTO_COMMENT_ENABLED else "✅ **ACTIVE**"
    out.append(f"> Status: {status} | Last Updated: {data.get('last_updated', 'N/A')} | ")
    out.append(f"Total Replies: {data.get('total_replies', 0)} | "
               f"Skipped: {data.get('total_skipped', 0)}\n\n")
    replies = data.get("replies", [])
    if replies:
        friendly_count = sum(1 for r in replies if r.get("type") == "friendly")
        savage_count = sum(1 for r in replies if r.get("type") == "savage")
        out.append("### 📊 Stats\n\n| Metric | Value |\n|---|---|\n")
        out.append(f"| Friendly Replies | {friendly_count} |\n")
        out.append(f"| Savage Replies | {savage_count} |\n")
        out.append(f"| Total | {len(replies)} |\n\n")
        out.append("### 💬 Recent Replies (Last 20)\n\n")
        out.append("| # | Time | 👤 User | 💬 User Comment | 🤖 AI Reply | Type | Depth | Game | FB Post |\n")
        out.append("|---|---|---|---|---|---|---|---|---|\n")
        for idx, r in enumerate(list(reversed(replies[-20:])), 1):
            un = (r.get("user_name", "Unknown") or "Unknown").replace("|", "\\|")[:20]
            cm = (r.get("user_comment", "") or "").replace("\n", " ").replace("|", "\\|")[:60]
            rp = (r.get("openrouter_reply", "") or "").replace("\n", " ").replace("|", "\\|")[:80]
            ts = r.get("timestamp", "")[:20]
            rtype = "😎 Savage" if r.get("type") == "savage" else "✅ Friendly"
            depth = r.get("depth", 1)
            game = (r.get("game", "") or "").replace("|", "\\|")[:15]
            fb_md = f"[🔵]({r['fb_post_link']})" if r.get("fb_post_link") else "_N/A_"
            out.append(f"| {idx} | {ts} | **{un}** | {cm} | {rp} | {rtype} | {depth} | {game} | {fb_md} |\n")
    skipped = data.get("skipped", [])[-5:]
    if skipped:
        out.append("\n### ⏭️ Skipped (Last 5)\n\n| Comment | Reason |\n|---|---|\n")
        for s in reversed(skipped):
            cm = (s.get("comment_text", "") or "").replace("\n", " ").replace("|", "\\|")[:80]
            reason = s.get("reason", "").replace("_", " ")
            out.append(f"| {cm} | {reason} |\n")
    return "".join(out)

def _generate_rotation_section_readonly():
    """Rotation section — READ ONLY — no updates."""
    rotation_file = "logs/rotation_history.json"
    if not os.path.exists(rotation_file):
        return ""
    try:
        with open(rotation_file, 'r', encoding='utf-8') as f:
            rot = json.load(f)
    except Exception:
        return ""
    out = ["\n--- \n\n## 🔄 Game Rotation Queue (Read-Only)\n\n"]
    out.append(f"**📊 Total Games:** {rot.get('total_games', 0)} | "
               f"**🎯 Current:** `{rot.get('current_game', 'N/A')}` | "
               f"**⏭️ Next Game:** `{rot.get('next_game', 'N/A')}` "
               f"(Position #{rot.get('next_game_position', 0)}) | "
               f"**🔢 Total Runs:** {rot.get('total_runs', 0)}\n\n")
    out.append(f"**Last Updated:** {rot.get('last_updated', 'N/A')} IST\n\n")
    out.append("| # | Game Name | Uploaded | Last Run # | Next Turn In | Status |\n")
    out.append("|:---:|---|:---:|:---:|:---:|:---:|\n")
    for ginfo in rot.get("all_games", []):
        status = ginfo.get("status", "waiting")
        if status == "current":
            status_md = "🎯 **CURRENT**"
        elif status == "next_up":
            status_md = "⏭️ **NEXT UP**"
        else:
            status_md = f"⏳ Wait {ginfo.get('next_turn_in', 0)}"
        out.append(f"| {ginfo.get('position', 0)} | **{ginfo.get('game', '')}** | "
                   f"{ginfo.get('uploaded', 0)} | {ginfo.get('last_run', 0) or '—'} | "
                   f"{ginfo.get('next_turn_in', 0)} | {status_md} |\n")
    recent_logs = rot.get("rotation_log", [])[-5:]
    if recent_logs:
        out.append("\n### 📜 Recent Runs (Last 5)\n\n| Run # | Game | Timestamp (IST) |\n|:---:|---|---|\n")
        for entry in reversed(recent_logs):
            out.append(f"| {entry['run']} | {entry['game']} | {entry['timestamp']} |\n")
    return "".join(out)

def update_unified_dashboard(actual_posted_titles, game_views_summary, game_stats, file_mapping):
    dashboard_path = "GAMING_DASHBOARD.md"
    leaderboard_json = os.path.join("logs/leaderboard", "games_performance_leaderboard.json")
    os.makedirs("logs/leaderboard", exist_ok=True)

    sorted_analytics = _generate_visual_reports(game_views_summary, game_stats)

    try:
        with open(leaderboard_json, 'w', encoding='utf-8') as f:
            json.dump([
                {"rank": i + 1, "game_name": item["game"],
                 "total_views": item["total_views"],
                 "uploaded_videos": item["uploaded_count"],
                 "avg_views_per_video": item["avg_views"],
                 "view_share_percentage": item["share_pct"]}
                for i, item in enumerate(sorted_analytics)
            ], f, indent=4)
    except Exception as e:
        log(f"⚠️ Leaderboard error: {e}")

    source_links_map, _, _ = load_source_data()

    games_dir = "logs/games"
    os.makedirs(games_dir, exist_ok=True)
    game_file_links = {}

    for g_name in sorted(actual_posted_titles.keys()):
        videos = actual_posted_titles.get(g_name, [])
        if not videos:
            continue
        safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', g_name)
        game_filename = f"{safe_name}.md"
        game_filepath = os.path.join(games_dir, game_filename)
        game_file_links[g_name] = f"logs/games/{game_filename}"

        src_file_for_game = file_mapping.get(g_name, "")
        file_links = []
        if src_file_for_game and os.path.exists(src_file_for_game):
            try:
                with open(src_file_for_game, 'r', encoding='utf-8', errors='ignore') as f:
                    fc = f.read()
                file_links = [u.rstrip('.,;)\']"') for u in
                              re.findall(r'\|\s*Link:\s*(https?://[^\s\n\r\)\]\'"<>,;]+)', fc)]
            except Exception:
                pass

        gf_lines = [f"# 🎮 {g_name} — Full Video History\n\n",
                    f"[⬅️ Back to Dashboard](../../GAMING_DASHBOARD.md)\n\n",
                    f"**Total Videos:** {len(videos)} | **Last Updated:** {now_ist_ampm()} IST\n\n",
                    "---\n\n",
                    "## 📜 All Videos (Newest First)\n\n",
                    "| # | 📺 Title | 🔵 FB | 👁️ FB Views | 🟣 IG | 👁️ IG Views | 📂 Source |\n",
                    "|---|---|---|---|---|---|---|\n"]

        for idx, v in enumerate(videos, 1):
            title = (v.get("title") or "").replace("\n", " ").replace("|", "\\|")[:120] or "_Untitled_"
            fb_md = f"[🔵 FB]({v['fb_link']})" if v.get("fb_posted") and v.get("fb_link") else "⏳ Pending"
            fb_v_md = f"{v.get('fb_views', 0):,}" if v.get("fb_posted") else "_0_"
            ig_md = f"[🟣 IG]({v['ig_link']})" if v.get("ig_posted") and v.get("ig_link") else "⏳ Pending"
            ig_v_md = f"{v.get('ig_views', 0):,}" if v.get("ig_posted") else "_0_"
            src_link = v.get("source_link", "")
            if not src_link and file_links and idx - 1 < len(file_links):
                src_link = file_links[idx - 1]
            if not src_link:
                src_urls = source_links_map.get(g_name, [])
                if idx - 1 < len(src_urls):
                    src_link = src_urls[idx - 1]
            src_md = f"[📂]({src_link})" if src_link else "_N/A_"
            gf_lines.append(f"| {idx} | {title} | {fb_md} | {fb_v_md} | "
                            f"{ig_md} | {ig_v_md} | {src_md} |\n")

        try:
            with open(game_filepath, 'w', encoding='utf-8') as f:
                f.writelines(gf_lines)
        except Exception as e:
            log(f"⚠️ Failed to write {game_filepath}: {e}")

    md = ["# 🚀 GAMING AGENT DASHBOARD\n\n",
          f"> **Last Updated:** {now_ist_ampm()} IST | **Status:** All Systems Active\n\n",
          "--- \n\n## 🏆 Global Leaderboard\n\n",
          "| Rank | Game Name | Total Videos | Total Views | Avg Views / Video | Tier |\n",
          "| :---: | :--- | :---: | :---: | :---: | :---: |\n"]
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    for idx, item in enumerate(sorted_analytics):
        rank_icon = medals[idx] if idx < len(medals) else f"{idx + 1}"
        tier = ("🔥 Viral" if item['avg_views'] > 7000
                else "⚡ Trending" if item['avg_views'] > 4000
                else "📈 Stable")
        md.append(f"| {rank_icon} | **{item['game']}** | {item['uploaded_count']} | "
                  f"{item['total_views']:,} | {item['avg_views']:,} | {tier} |\n")

    md.append("\n--- \n\n## 📺 Live Post Titles (Latest per Game)\n\n")
    md.append("| Game | Latest Title | 🔵 FB | 👁️ FB Views | 🟣 IG | 👁️ IG Views | 📂 Source | 📜 All |\n")
    md.append("|---|---|---|---|---|---|---|---|\n")

    sorted_games = sorted(actual_posted_titles.keys(),
                          key=lambda g: max([v.get("timestamp", "") for v in actual_posted_titles.get(g, [])] + [""]),
                          reverse=True)

    for g_name in sorted_games:
        videos = actual_posted_titles.get(g_name, [])
        if not videos:
            continue
        latest_posted, latest_ts = None, ""
        for v in videos:
            if v.get("fb_posted") or v.get("ig_posted"):
                ts = v.get("timestamp", "")
                if ts > latest_ts:
                    latest_ts = ts
                    latest_posted = v
        latest = latest_posted or videos[0]
        title = (latest.get("title") or "").replace("\n", " ").replace("|", "\\|")[:80] or "_Untitled_"
        fb_md = f"[🔵 FB]({latest['fb_link']})" if latest.get("fb_posted") and latest.get("fb_link") else "⏳"
        fb_v_md = f"{latest.get('fb_views', 0):,}" if latest.get("fb_posted") else "_0_"
        ig_md = f"[🟣 IG]({latest['ig_link']})" if latest.get("ig_posted") and latest.get("ig_link") else "⏳"
        ig_v_md = f"{latest.get('ig_views', 0):,}" if latest.get("ig_posted") else "_0_"
        src_link = latest.get("source_link", "") or (videos[0].get("source_link", "") if videos else "")
        src_md = f"[📂]({src_link})" if src_link else "_N/A_"
        all_md = f"**[📜 View {len(videos)}]({game_file_links[g_name]})**" if g_name in game_file_links else f"_{len(videos)}_"
        md.append(f"| **{g_name}** | {title} | {fb_md} | {fb_v_md} | {ig_md} | {ig_v_md} | {src_md} | {all_md} |\n")

    for section_fn in [_generate_trending_section, _generate_best_time_section,
                       _generate_auto_reply_section, _generate_rotation_section_readonly]:
        section = section_fn()
        if section:
            md.append(section)

    md.append("\n--- \n\n## 📜 Full Video History\n\n")
    for g_name in sorted_games:
        videos = actual_posted_titles.get(g_name, [])
        if not videos:
            continue
        file_link = game_file_links.get(g_name, "")
        if file_link:
            md.append(f"- **🎮 {g_name}** — [📜 View All {len(videos)} Videos]({file_link})\n")

    with open(dashboard_path, 'w', encoding='utf-8') as f:
        f.writelines(md)

    git_commit_and_push([
        dashboard_path, leaderboard_json,
        "logs/auto_reply_log.json",
        "logs/replied_comment_ids.json",
        "logs/trending_cache.json",
        "logs/best_time_analysis.json",
        "logs/games/",
    ])


# ============================================================
# 🚀 MAIN
# ============================================================
def main():
    log("=" * 60)
    log("🚀 SPLIT AUTO-COMMENT + DASHBOARD (No Rotation Write)")
    log("=" * 60)

    # STEP 1: Auto-comment
    if AUTO_COMMENT_ENABLED:
        try:
            process_fb_comments()
        except Exception as e:
            log(f"⚠️ Auto-reply error: {e}")
    else:
        log("🚫 Auto-comment disabled")

    # STEP 2: Discover games (for dashboard)
    links_dir = "game_links_editor"
    os.makedirs("logs", exist_ok=True)
    os.makedirs(links_dir, exist_ok=True)

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

    # STEP 3: Fetch FB/IG data
    actual_posted_titles, game_views_summary = fetch_fb_ig_data(game_list)
    if not game_views_summary:
        game_views_summary = {g: 0 for g in game_list}

    # STEP 4: Trending + Best time
    try:
        detect_trending_games(actual_posted_titles, days=7)
    except Exception as e:
        log(f"⚠️ Trending error: {e}")
    try:
        analyze_best_time()
    except Exception as e:
        log(f"⚠️ Best time error: {e}")

    # STEP 5: Dashboard (READ-ONLY rotation)
    memory = {}
    if os.path.exists("logs/agent_memory.json"):
        try:
            with open("logs/agent_memory.json", 'r', encoding='utf-8') as f:
                memory = json.load(f)
        except Exception:
            pass
    game_stats = memory.get("game_stats", {})

    update_unified_dashboard(actual_posted_titles, game_views_summary, game_stats, file_mapping)

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