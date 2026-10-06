"""
💬 SPLIT AUTO-COMMENT SCRIPT (v9 — Schema + User Name Fix)
============================================================
✅ ONLY writes 2 JSON files:
   - logs/auto_reply_log.json
   - logs/replied_comment_ids.json
✅ NO dashboard / NO trending / NO best_time / NO games/ folder
✅ Full script handles ALL dashboard writing
✅ Shared log with full script (no duplicate replies)
✅ Recursive nested replies fetch
✅ Last reply check FIRST — no duplicate
✅ 🆕 JSON Schema (strict) + auto-fallback to json_object
✅ 🆕 User Name 5-layer fallback + LAST user reply se naam
"""

import os
import re
import json
import time
import sys
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

MAX_REPLIES_PER_RUN = 10
MAX_CONVERSATION_DEPTH = 3
MIN_COMMENT_AGE_MIN = 0
MAX_COMMENT_AGE_HOURS = 1440
POSTS_TO_SCAN = 25
COMMENT_FETCH_WORKERS = 10
MAX_JSON_RETRIES = 12

# 🔥 ONLY THESE 2 FILES WILL BE WRITTEN
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
# 🤖 OPENROUTER CLIENT (v9 — JSON Schema + Fallback)
# ============================================================
def _build_json_schema():
    """Strict JSON schema for batch replies."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "batch_replies",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "replies": {
                        "type": "object",
                        "description": "Map of comment_id to reply text",
                        "additionalProperties": {"type": "string"}
                    }
                },
                "required": ["replies"],
                "additionalProperties": False
            }
        }
    }


def _call_openrouter_single(model_name, api_key, prompt,
                             max_tokens=150, use_schema=False):
    """
    v9: Agar use_schema=True → strict json_schema try kare.
    Fail ho jaye (400/schema not supported) → auto fallback to json_object.
    """
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

    if use_schema:
        payload["response_format"] = _build_json_schema()
        mode_tag = "SCHEMA"
    else:
        payload["response_format"] = {"type": "json_object"}
        mode_tag = "JSON_OBJ"

    # ✅ response-healing plugin (only for json_object)
    if not use_schema:
        payload["plugins"] = [{"id": "response-healing"}]

    try:
        res = requests.post(OPENROUTER_URL, headers=headers,
                            json=payload, timeout=40)

        if res.status_code == 200:
            data = res.json()
            choices = data.get("choices", [])
            if choices:
                content = choices[0].get("message", {}).get("content", "")
                if content:
                    return content.strip()
            log(f"   ⚠️ [{mode_tag}] Empty choices")
            return None

        # 🔥 Auto-fallback: schema not supported
        if res.status_code == 400 and use_schema:
            err = res.text.lower()
            if ("json_schema" in err or "response_format" in err
                    or "schema" in err or "not supported" in err):
                log(f"   ⚠️ [{mode_tag}] Not supported — falling back to json_object")
                return _call_openrouter_single(
                    model_name, api_key, prompt,
                    max_tokens=max_tokens, use_schema=False
                )

        log(f"   ⚠️ [{mode_tag}] HTTP {res.status_code}: {res.text[:150]}")
        return None

    except Exception as e:
        log(f"   ⚠️ [{mode_tag}] Exception: {e}")
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


def _normalize_parsed_replies(parsed):
    """
    v9: Handle BOTH output shapes:
      Format A (schema):  {"replies": {"id1": "text1"}}
      Format B (old):     {"id1": "text1"}
    Returns flat dict {comment_id: reply_text}
    """
    if not isinstance(parsed, dict):
        return {}
    inner = parsed.get("replies")
    if isinstance(inner, dict):
        return {str(k): str(v) for k, v in inner.items() if v}
    skip = {"user safety: safe", "safe", "unsafe", "none"}
    flat = {}
    for k, v in parsed.items():
        if isinstance(v, str) and v.strip().lower() not in skip:
            flat[str(k)] = v
    return flat


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
  "replies": {{
    "COMMENT_ID_1": "reply 1",
    "COMMENT_ID_2": "reply 2"
  }}
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

        # 🔥 First 2 attempts → SCHEMA, then JSON_OBJ
        use_schema = attempt <= 2
        schema_tag = "SCHEMA" if use_schema else "JSON_OBJ"

        log(f"🔄 Attempt {attempt}/{max_retries} | {tag} | {schema_tag} | Key {key_index + 1}")

        response = _call_openrouter_single(
            model_to_use, current_key, prompt,
            max_tokens=1800,
            use_schema=use_schema
        )

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

        # 🔥 Normalize (schema-nested OR flat)
        flat_replies = _normalize_parsed_replies(parsed)

        result = {}
        for c in comments_batch:
            cid = c["comment_id"]
            if cid in flat_replies:
                reply = str(flat_replies[cid]).strip().strip('"').strip("'")
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
# 💬 AUTO-COMMENT — SHARED LOG (v9)
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


def fetch_comment_author(comment_id):
    """v9: Specific comment_id se from{name,id,username} fetch karo."""
    if not comment_id:
        return {}
    try:
        res = requests.get(
            f"{FB_GRAPH_URL}/{comment_id}",
            params={"fields": "from{name,id,username}",
                    "access_token": FB_ACCESS_TOKEN},
            timeout=8)
        if res.status_code == 200:
            return res.json().get("from", {}) or {}
    except Exception:
        pass
    return {}


def get_user_name(user_id, fallback_from_field=None, comment_obj=None):
    """
    v9: 5-layer user name fetch:
      1. fallback_from_field
      2. cache (skip User_XXXX placeholder)
      3. comment_obj.from.name
      4. API with multiple field combos (name/first_name/last_name/username)
      5. User_XXXXXX placeholder
    """
    global _user_name_cache

    # Layer 1: fallback from field
    if fallback_from_field and str(fallback_from_field).strip():
        name = str(fallback_from_field).strip()
        if name and name.lower() != "facebook user":
            if user_id:
                _user_name_cache[str(user_id)] = name
            return name

    # Layer 2: cache (skip placeholder)
    if user_id:
        user_id = str(user_id).strip()
        cached = _user_name_cache.get(user_id, "")
        if cached and not cached.startswith("User_"):
            return cached

    # Layer 3: from comment_obj
    if comment_obj:
        cfrom = comment_obj.get("from", {}) or {}
        cname = (cfrom.get("name") or "").strip()
        if cname:
            if user_id:
                _user_name_cache[str(user_id)] = cname
            return cname

    # Layer 4: API — multiple field combos
    if user_id:
        user_id = str(user_id).strip()
        for fields in ["name,first_name,last_name,username",
                       "name,first_name,last_name",
                       "name"]:
            try:
                res = requests.get(
                    f"{FB_GRAPH_URL}/{user_id}",
                    params={"fields": fields, "access_token": FB_ACCESS_TOKEN},
                    timeout=8)
                if res.status_code == 200:
                    data = res.json()
                    name = (data.get("name") or "").strip()
                    if not name:
                        first = (data.get("first_name") or "").strip()
                        last = (data.get("last_name") or "").strip()
                        name = f"{first} {last}".strip()
                    if not name:
                        uname = (data.get("username") or "").strip()
                        if uname:
                            name = f"@{uname}"
                    if name:
                        _user_name_cache[user_id] = name
                        return name
            except Exception:
                continue

    # Layer 5: placeholder
    if user_id:
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
    v9: Analyze thread with user name fix.
    - Recursive replies fetch
    - Last reply check FIRST
    - Log check SIRF fresh comment ke liye
    - 🔥 LAST user reply ka naam use karo (top comment ka nahi)
    """
    cid = top_comment.get("id", "")

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

    if our_count >= MAX_CONVERSATION_DEPTH:
        return {"should_reply": False, "depth": our_count, "reason": "max_depth"}

    if len(replies_sorted) == 0:
        if was_already_replied(cid):
            log(f"      ⏭️ Fresh on FB but IN SHARED LOG — skip")
            return {"should_reply": False, "depth": 0, "reason": "already_replied_log"}
        log(f"      🆕 Fresh comment — WILL REPLY")
    else:
        last = replies_sorted[-1]
        if _is_our_reply(last, page_name_lower):
            log(f"      ⏭️ Last reply is OURS — waiting for user")
            return {"should_reply": False, "depth": our_count, "reason": "waiting_user"}

        last_user_id = last.get("id", "")
        if last_user_id and was_already_replied(last_user_id):
            log(f"      ⏭️ Already replied to this user reply — skip")
            return {"should_reply": False, "depth": our_count,
                    "reason": "already_replied_this_reply"}

        log(f"      💬 NEW user reply — continuing (depth {our_count})")

    thread_ctx = ""
    for r in replies_sorted[-6:]:
        who = "US" if _is_our_reply(r, page_name_lower) else "USER"
        msg = (r.get("message", "") or "").replace("\n", " ")[:150]
        thread_ctx += f"  {who}: {msg}\n"

    user_msgs = [top_comment] + user_replies
    if not user_msgs:
        return {"should_reply": False, "depth": our_count, "reason": "no_user_msg"}

    # 🔥 FIX: LAST user reply ka from use karo
    last_user = user_msgs[-1]
    last_text = (last_user.get("message") or "").strip()
    if not last_text:
        return {"should_reply": False, "depth": our_count, "reason": "empty"}

    last_from = last_user.get("from", {}) or {}
    user_id = last_from.get("id", "")
    user_name_raw = last_from.get("name", "")

    # Agar last_user me from missing → direct fetch
    if not user_name_raw and not user_id:
        fetched = fetch_comment_author(last_user.get("id", ""))
        if fetched:
            user_id = fetched.get("id", "")
            user_name_raw = fetched.get("name", "")

    # Agar abhi bhi missing → top comment se try
    if not user_name_raw and not user_id:
        top_from = top_comment.get("from", {}) or {}
        user_id = top_from.get("id", "")
        user_name_raw = top_from.get("name", "")

    user_name = get_user_name(user_id, user_name_raw, comment_obj=last_user)

    log(f"      👤 User resolved: {user_name}")

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

    log("🤖 Auto-reply started (v9 — Schema + User Fix)...")
    log(f"📂 Shared log: {SHARED_REPLY_LOG}")
    log(f"📂 Shared IDs: {SHARED_REPLIED_IDS}")

    page_name = get_page_name()
    log(f"📄 Page name: {page_name or 'N/A'}")

    replied_data = {"replied": [], "last_updated": ""}
    if os.path.exists(SHARED_REPLIED_IDS):
        try:
            with open(SHARED_REPLIED_IDS, 'r', encoding='utf-8') as f:
                replied_data = json.load(f)
        except Exception:
            pass
    replied_ids = set(replied_data.get("replied", []))

    reply_log = {"total_replies": 0, "total_skipped": 0, "replies": [], "skipped": []}
    if os.path.exists(SHARED_REPLY_LOG):
        try:
            with open(SHARED_REPLY_LOG, 'r', encoding='utf-8') as f:
                reply_log = json.load(f)
            log(f"📂 Existing history: {len(reply_log.get('replies', []))} replies (SHARED)")
        except Exception:
            pass

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
        log(f"📦 Batch: {len(valid_comments)} comments → 12-retry loop (SCHEMA → JSON_OBJ)")
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
# 🔄 GIT PUSH — ONLY 2 JSON FILES
# ============================================================
def git_commit_and_push(file_paths, message="Auto-Reply: Update JSON logs [skip ci]"):
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
    log("🚀 SPLIT SCRIPT v9 — Schema + User Name Fix")
    log("=" * 60)
    log(f"📂 Writes ONLY: {SHARED_REPLY_LOG}")
    log(f"📂 Writes ONLY: {SHARED_REPLIED_IDS}")
    log(f"🚫 NO dashboard / NO trending / NO games/ folder")
    log("=" * 60)

    if AUTO_COMMENT_ENABLED:
        try:
            process_fb_comments()
        except Exception as e:
            log(f"⚠️ Auto-reply error: {e}")
            import traceback
            traceback.print_exc()
    else:
        log("🚫 Auto-comment disabled")

    try:
        git_commit_and_push([SHARED_REPLY_LOG, SHARED_REPLIED_IDS])
    except Exception as e:
        log(f"⚠️ Git push error: {e}")

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
