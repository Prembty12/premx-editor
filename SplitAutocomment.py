"""
💬 SPLIT AUTO-COMMENT SCRIPT (v13.2 — FIXED 404 + 400 ERRORS)
============================================================
✅ Direct FB se SAARE comments fetch (pagination + nested replies)
✅ SCHEMA har attempt pe try, fail hone pe auto JSON_OBJ fallback
✅ 5-layer JSON parser — broken JSON bhi recover
✅ FIXED: provider block hataya (404 fix)
✅ FIXED: top_p/frequency_penalty/presence_penalty hataye (400 fix)
✅ FIXED: strict:False schema (free models support)
✅ FIXED_MODEL = working chat model
✅ ONLY writes 2 JSON files:
   - logs/auto_reply_log.json
   - logs/replied_comment_ids.json
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

# 🔥 FIXED — working chat model
FIXED_MODEL = "meta-llama/llama-3.3-70b-instruct:free"
FALLBACK_MODEL = "openrouter/free"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

FB_PAGE_ID = os.environ.get("PAGE_ID")
FB_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")

FB_API_VERSION = "v24.0"
FB_GRAPH_URL = f"https://graph.facebook.com/{FB_API_VERSION}"

MAX_REPLIES_PER_RUN = 10
MAX_CONVERSATION_DEPTH = 3
MIN_COMMENT_AGE_MIN = 0

# ============================================================
# 🔥 YAHAN APNA TIME WINDOW SET KARO
# ============================================================
MAX_COMMENT_AGE_HOURS = 60 * 24    # 👈 CHANGE THIS (60 days)
# ============================================================

POSTS_TO_SCAN = 100
COMMENT_FETCH_WORKERS = 5
MAX_JSON_RETRIES = 12
MAX_COMMENT_PAGES = 20

SHARED_REPLY_LOG = "logs/auto_reply_log.json"
SHARED_REPLIED_IDS = "logs/replied_comment_ids.json"
BAD_POSTS_FILE = "logs/bad_posts.json"

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
# 🤖 OPENROUTER CLIENT (FIXED — Simple params only)
# ============================================================
def _build_json_schema():
    """Simple schema — strict=False taaki free models accept kare."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "batch_replies",
            "strict": False,
            "schema": {
                "type": "object",
                "properties": {
                    "replies": {
                        "type": "object",
                        "additionalProperties": {"type": "string"}
                    }
                },
                "required": ["replies"]
            }
        }
    }


def _call_openrouter_single(model_name, api_key, prompt,
                             max_tokens=1500, use_schema=True):
    """Simple call — sirf basic parameters, free models ke liye."""
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
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a JSON-only API. You MUST respond with valid JSON. "
                    "No markdown, no explanations, no text outside JSON."
                )
            },
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": max_tokens,
    }

    if use_schema:
        payload["response_format"] = _build_json_schema()
        mode_tag = "SCHEMA"
    else:
        payload["response_format"] = {"type": "json_object"}
        mode_tag = "JSON_OBJ"

    try:
        res = requests.post(OPENROUTER_URL, headers=headers,
                            json=payload, timeout=60)

        if res.status_code == 200:
            data = res.json()

            if "error" in data:
                err = data.get("error", {})
                log(f"   ⚠️ [{mode_tag}] API error in 200: {err.get('message', '')[:120]}")
                if use_schema:
                    return _call_openrouter_single(
                        model_name, api_key, prompt,
                        max_tokens=max_tokens, use_schema=False
                    )
                return None

            choices = data.get("choices", [])
            if choices:
                msg = choices[0].get("message", {})
                content = msg.get("content", "")
                finish_reason = choices[0].get("finish_reason", "")

                if not content:
                    content = msg.get("reasoning", "") or ""

                if content and content.strip():
                    return content.strip()

                log(f"   ⚠️ [{mode_tag}] Empty content (finish={finish_reason})")
            else:
                log(f"   ⚠️ [{mode_tag}] No choices in response")

            if use_schema:
                log(f"   🔄 [{mode_tag}] Empty — retry with JSON_OBJ")
                return _call_openrouter_single(
                    model_name, api_key, prompt,
                    max_tokens=max_tokens, use_schema=False
                )
            return None

        if res.status_code == 404 and use_schema:
            log(f"   🔄 [{mode_tag}] 404 — JSON_OBJ retry")
            return _call_openrouter_single(
                model_name, api_key, prompt,
                max_tokens=max_tokens, use_schema=False
            )

        if res.status_code == 400:
            err = res.text.lower()
            if use_schema and any(k in err for k in (
                "json_schema", "response_format", "schema",
                "not supported", "unsupported", "invalid",
                "top_p", "parameter", "provider"
            )):
                log(f"   🔄 [{mode_tag}] 400 — JSON_OBJ retry")
                return _call_openrouter_single(
                    model_name, api_key, prompt,
                    max_tokens=max_tokens, use_schema=False
                )

        if res.status_code == 422 and use_schema:
            log(f"   🔄 [{mode_tag}] 422 — JSON_OBJ retry")
            return _call_openrouter_single(
                model_name, api_key, prompt,
                max_tokens=max_tokens, use_schema=False
            )

        if res.status_code == 402:
            log(f"   💰 [{mode_tag}] 402 — No credits")
            return None

        if res.status_code == 429:
            log(f"   ⏳ [{mode_tag}] 429 — Rate limited")
            return None

        log(f"   ⚠️ [{mode_tag}] HTTP {res.status_code}: {res.text[:150]}")
        return None

    except requests.exceptions.Timeout:
        log(f"   ⚠️ [{mode_tag}] Timeout")
        return None
    except Exception as e:
        log(f"   ⚠️ [{mode_tag}] Exception: {e}")
        return None


def _extract_json(response):
    """5-layer JSON extraction."""
    if not response:
        return None

    cleaned = response.strip()

    if "```" in cleaned:
        cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned, flags=re.IGNORECASE)
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

    try:
        fixed = cleaned
        fixed = re.sub(r',\s*}', '}', fixed)
        fixed = re.sub(r',\s*]', ']', fixed)
        fixed = fixed.replace("'", '"')
        s, e = fixed.find("{"), fixed.rfind("}")
        if s != -1 and e != -1 and e > s:
            r = json.loads(fixed[s:e + 1])
            if isinstance(r, dict):
                return r
    except Exception:
        pass

    try:
        import ast
        s, e = cleaned.find("{"), cleaned.rfind("}")
        if s != -1 and e != -1 and e > s:
            r = ast.literal_eval(cleaned[s:e + 1])
            if isinstance(r, dict):
                return r
    except Exception:
        pass

    return None


def _normalize_parsed_replies(parsed):
    """Normalize nested {replies:{...}} and flat {id:reply} formats."""
    if not isinstance(parsed, dict):
        return {}

    inner = parsed.get("replies")
    if isinstance(inner, dict):
        return {str(k): str(v) for k, v in inner.items() if v and str(v).strip()}

    skip = {"user safety: safe", "safe", "unsafe", "none", "null", ""}
    flat = {}
    for k, v in parsed.items():
        if not isinstance(v, str):
            continue
        if v.strip().lower() in skip:
            continue
        if k.lower() in ("replies", "response", "data", "result"):
            continue
        flat[str(k)] = v
    return flat


def generate_batch_replies(comments_batch, max_retries=MAX_JSON_RETRIES):
    if not comments_batch:
        return {}

    # 🔥 SIMPLER PROMPT
    formatted = ""
    for c in comments_batch:
        tone = "SAVAGE" if c["is_abuse"] else "FRIENDLY"
        safe_text = c["comment_text"].replace('"', "'").replace("\n", " ")[:200]
        caption_safe = c.get("post_title", "").replace('"', "'").replace("\n", " ")[:100]
        hashtags_safe = ", ".join(c.get("post_hashtags", []))[:80]

        formatted += (
            f'ID: "{c["comment_id"]}"\n'
            f'  Game: {c["game_name"]}\n'
            f'  Caption: "{caption_safe}"\n'
            f'  Comment: "{safe_text}"\n'
            f'  Tone: {tone}\n\n'
        )

    ids_list = ", ".join(f'"{c["comment_id"]}"' for c in comments_batch)

    prompt = f"""Reply to each Facebook comment as a gaming creator.

LANGUAGE: Same as comment (English/Hinglish).
LENGTH: Max 20 words.
TONE: Casual, funny, human. Use bhai/bro/yaar/lol/OP/fire.
EMOJI: 1-2 max.
If comment is abusive → savage comeback (no abuse back).
If asks game name → mention it.

Output JSON only:
{{
  "replies": {{
    "COMMENT_ID": "reply text"
  }}
}}

Reply to ALL these IDs: [{ids_list}]

COMMENTS:
{formatted}

JSON:"""

    valid_keys = [k for k in OPENROUTER_KEYS if k]
    if not valid_keys:
        log("❌ No OpenRouter API keys found.")
        return {}

    for attempt in range(1, max_retries + 1):
        key_index = (attempt - 1) % len(valid_keys)
        current_key = valid_keys[key_index]

        # 🔥 Attempt 1-3 → FIXED, Attempt 4-12 → FALLBACK
        model_to_use = FIXED_MODEL if attempt <= 3 else FALLBACK_MODEL
        tag = "FIXED" if attempt <= 3 else "FALLBACK"

        log(f"🔄 Attempt {attempt}/{max_retries} | {tag} | "
            f"{model_to_use.split('/')[0]} | SCHEMA | Key {key_index + 1}")

        response = _call_openrouter_single(
            model_to_use, current_key, prompt,
            max_tokens=1500,
            use_schema=True
        )

        if not response:
            log("   ⚠️ Empty response — retry")
            time.sleep(1.5)
            continue

        if response.strip().lower() in ["user safety: safe", "safe", "unsafe", "none"]:
            log("   ⚠️ Safety model response — retry")
            time.sleep(1)
            continue

        parsed = _extract_json(response)
        if parsed is None:
            log(f"   ⚠️ Invalid JSON — retry. Preview: {response[:120]}")
            time.sleep(1)
            continue

        flat_replies = _normalize_parsed_replies(parsed)

        result = {}
        for c in comments_batch:
            cid = c["comment_id"]
            if cid in flat_replies:
                reply = str(flat_replies[cid]).strip().strip('"').strip("'")
                if reply and reply.lower() not in ["user safety: safe", "safe",
                                                     "unsafe", "none", "null"]:
                    result[cid] = reply

        if result:
            log(f"   ✅ Valid JSON on attempt {attempt} ({tag}): "
                f"{len(result)}/{len(comments_batch)} replies")
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
# ⏰ AGE CHECK
# ============================================================
def is_within_time_window(timestamp_str):
    if not timestamp_str:
        return True
    try:
        dt = datetime.fromisoformat(timestamp_str.replace("+0000", "+00:00"))
        ts = dt.timestamp()
        cutoff = (now_ist() - timedelta(hours=MAX_COMMENT_AGE_HOURS)).timestamp()
        max_allowed = (now_ist() - timedelta(minutes=MIN_COMMENT_AGE_MIN)).timestamp()
        return cutoff <= ts <= max_allowed
    except Exception:
        return True


# ============================================================
# 🚫 BAD POSTS CACHE
# ============================================================
def load_bad_posts():
    if os.path.exists(BAD_POSTS_FILE):
        try:
            with open(BAD_POSTS_FILE, 'r', encoding='utf-8') as f:
                return set(json.load(f).get("bad", []))
        except Exception:
            pass
    return set()


def mark_bad_post(post_id):
    if not post_id:
        return
    bad = load_bad_posts()
    if post_id in bad:
        return
    bad.add(post_id)
    os.makedirs("logs", exist_ok=True)
    try:
        with open(BAD_POSTS_FILE, 'w', encoding='utf-8') as f:
            json.dump({"bad": list(bad)[-500:],
                       "updated": now_ist_ampm()}, f, indent=2)
        log(f"      📝 Marked bad post: {post_id}")
    except Exception:
        pass


# ============================================================
# 💬 FB HELPERS
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
    global _user_name_cache

    if fallback_from_field and str(fallback_from_field).strip():
        name = str(fallback_from_field).strip()
        if name and name.lower() != "facebook user":
            if user_id:
                _user_name_cache[str(user_id)] = name
            return name

    if user_id:
        user_id = str(user_id).strip()
        cached = _user_name_cache.get(user_id, "")
        if cached and not cached.startswith("User_"):
            return cached

    if comment_obj:
        cfrom = comment_obj.get("from", {}) or {}
        cname = (cfrom.get("name") or "").strip()
        if cname:
            if user_id:
                _user_name_cache[str(user_id)] = cname
            return cname

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


# ============================================================
# 🔥 FETCH POST COMMENTS — FULL WITH PAGINATION + NESTED
# ============================================================
def fetch_fb_comments(post_id, retries=2, max_pages=MAX_COMMENT_PAGES):
    """Direct FB se SAARE comments fetch with pagination + nested replies."""
    all_comments = []
    url = f"{FB_GRAPH_URL}/{post_id}/comments"
    params = {
        "fields": (
            "id,message,from{name,id},created_time,can_reply,"
            "comments.limit(100){"
                "id,message,from{name,id},created_time,can_reply,"
                "comments.limit(100){"
                    "id,message,from{name,id},created_time,can_reply"
                "}"
            "}"
        ),
        "access_token": FB_ACCESS_TOKEN,
        "limit": 100,
        "filter": "stream",
        "order": "chronological",
    }

    page = 0
    for attempt in range(retries + 1):
        try:
            res = requests.get(url, params=params, timeout=20)

            if res.status_code == 200:
                data = res.json()

                if "error" in data:
                    err = data.get("error", {})
                    err_msg = err.get("message", "")[:120]
                    err_code = err.get("code", 0)
                    log(f"      ⚠️ API error post={post_id}: {err_msg}")
                    if err_code == 100:
                        mark_bad_post(post_id)
                    return all_comments

                batch = data.get("data", [])
                all_comments.extend(batch)
                log(f"      📥 Page {page + 1}: {len(batch)} comments "
                    f"(total: {len(all_comments)})")

                paging = data.get("paging", {})
                next_url = paging.get("next")

                if not next_url or not batch:
                    break

                page += 1
                if page >= max_pages:
                    log(f"      ⚠️ Max pages ({max_pages}) reached")
                    break

                url = next_url
                params = None
                time.sleep(0.5)
                continue

            if res.status_code == 400 and '"code":100' in res.text.replace(" ", ""):
                log(f"      🚫 Post {post_id} inaccessible (#100) — skip")
                mark_bad_post(post_id)
                return all_comments

            if res.status_code in (429, 500, 502, 503):
                wait = (2 ** attempt) + random.uniform(0, 1)
                log(f"      ⏳ Transient {res.status_code} — retry in {wait:.1f}s")
                time.sleep(wait)
                continue

            log(f"      ⚠️ comments error ({res.status_code}) post={post_id}: {res.text[:150]}")
            return all_comments

        except requests.exceptions.Timeout:
            log(f"      ⚠️ Timeout post={post_id} (attempt {attempt+1})")
            if attempt < retries:
                time.sleep(1)
        except Exception as e:
            log(f"      ⚠️ comments exception post={post_id}: {e}")
            return all_comments

    log(f"      ✅ Total {len(all_comments)} comments for post {post_id}")
    return all_comments


def fetch_comment_replies(comment_id, depth=0, max_depth=3):
    """Comment ke saare replies fetch karo (nested)."""
    if depth >= max_depth:
        return []
    params = {
        "fields": "id,message,from{name,id},created_time,can_reply",
        "access_token": FB_ACCESS_TOKEN,
        "limit": 100,
        "filter": "stream",
    }
    all_replies = []
    try:
        res = requests.get(f"{FB_GRAPH_URL}/{comment_id}/comments",
                           params=params, timeout=15)
        if res.status_code == 200:
            data = res.json()
            if "error" in data:
                return []
            replies = data.get("data", [])
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


def get_effective_reply_time(comment, replies_sorted, page_name_lower):
    """Agar koi user reply hai → last user reply ka time. Warna top comment ka time."""
    user_replies = [r for r in replies_sorted
                    if not _is_our_reply(r, page_name_lower)]

    if user_replies:
        last_user = max(user_replies, key=lambda x: x.get("created_time", ""))
        return last_user.get("created_time", ""), "last_user_reply"

    return comment.get("created_time", ""), "top_comment"


def analyze_thread(top_comment):
    """v13.2: Embedded nested replies use karo (fast), warna alag fetch."""
    cid = top_comment.get("id", "")

    embedded = []
    embedded_raw = top_comment.get("comments")
    if embedded_raw and isinstance(embedded_raw, dict):
        embedded = embedded_raw.get("data", []) or []

    if embedded:
        replies = []
        for r in embedded:
            replies.append(r)
            nested_raw = r.get("comments")
            if nested_raw and isinstance(nested_raw, dict):
                for r2 in nested_raw.get("data", []) or []:
                    replies.append(r2)
                    nested2 = r2.get("comments")
                    if nested2 and isinstance(nested2, dict):
                        for r3 in nested2.get("data", []) or []:
                            replies.append(r3)
    else:
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

    effective_time, time_source = get_effective_reply_time(
        top_comment, replies_sorted, page_name_lower
    )

    if not is_within_time_window(effective_time):
        log(f"      ⏰ Outside {MAX_COMMENT_AGE_HOURS}h window "
            f"({time_source}={effective_time[:10]})")
        return {"should_reply": False, "depth": our_count,
                "reason": "outside_time_window"}

    if len(replies_sorted) == 0:
        if was_already_replied(cid):
            log(f"      ⏭️ Fresh on FB but IN LOG — skip")
            return {"should_reply": False, "depth": 0,
                    "reason": "already_replied_log"}
        log(f"      🆕 Fresh comment — WILL REPLY")
    else:
        last = replies_sorted[-1]
        if _is_our_reply(last, page_name_lower):
            log(f"      ⏭️ Last reply is OURS — waiting for user")
            return {"should_reply": False, "depth": our_count,
                    "reason": "waiting_user"}

        last_user_id = last.get("id", "")
        if last_user_id and was_already_replied(last_user_id):
            log(f"      ⏭️ Already replied to this user reply — skip")
            return {"should_reply": False, "depth": our_count,
                    "reason": "already_replied_this_reply"}

        log(f"      💬 NEW user reply (depth {our_count}) — WILL REPLY")

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

    last_from = last_user.get("from", {}) or {}
    user_id = last_from.get("id", "")
    user_name_raw = last_from.get("name", "")

    if not user_name_raw and not user_id:
        fetched = fetch_comment_author(last_user.get("id", ""))
        if fetched:
            user_id = fetched.get("id", "")
            user_name_raw = fetched.get("name", "")

    if not user_name_raw and not user_id:
        top_from = top_comment.get("from", {}) or {}
        user_id = top_from.get("id", "")
        user_name_raw = top_from.get("name", "")

    user_name = get_user_name(user_id, user_name_raw, comment_obj=last_user)
    log(f"      👤 User: {user_name} | effective_time={effective_time[:10]} ({time_source})")

    return {
        "should_reply": True,
        "depth": our_count,
        "reason": "ok",
        "reply_to_id": last_user.get("id") or cid,
        "reply_to_text": last_text,
        "user_id": user_id,
        "user_name": user_name,
        "thread_context": thread_ctx,
        "effective_time": effective_time,
    }


def fetch_posts_with_fallback():
    candidates = [POSTS_TO_SCAN]
    for n in (40, 35, 30, 25):
        if n < POSTS_TO_SCAN and n not in candidates:
            candidates.append(n)

    for scan_count in candidates:
        log(f"📥 Trying to fetch {scan_count} posts...")
        try:
            res = requests.get(
                f"{FB_GRAPH_URL}/{FB_PAGE_ID}/posts",
                params={"fields": "id,message,created_time,permalink_url",
                        "access_token": FB_ACCESS_TOKEN,
                        "limit": scan_count},
                timeout=20)
            if res.status_code == 200:
                data = res.json()
                if "error" in data:
                    log(f"⚠️ API error: {data['error'].get('message','')[:150]}")
                else:
                    posts = data.get("data", [])
                    log(f"✅ Got {len(posts)} posts (requested {scan_count})")
                    return posts
            else:
                log(f"⚠️ HTTP {res.status_code}: {res.text[:150]}")
        except Exception as e:
            log(f"⚠️ Exception: {e}")
        time.sleep(2)

    log("❌ All post-fetch attempts failed")
    return []


# ============================================================
# 🚀 MAIN PROCESS
# ============================================================
def process_fb_comments(actual_posted_titles=None):
    if not AUTO_COMMENT_ENABLED:
        log("🚫 Auto-comment disabled")
        return None

    window_days = MAX_COMMENT_AGE_HOURS // 24
    log(f"🤖 Auto-reply started (v13.2 — FIXED 404+400: "
        f"{window_days} days / {MAX_COMMENT_AGE_HOURS} hours)...")
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

    reply_log = {"total_replies": 0, "total_skipped": 0,
                 "replies": [], "skipped": []}
    if os.path.exists(SHARED_REPLY_LOG):
        try:
            with open(SHARED_REPLY_LOG, 'r', encoding='utf-8') as f:
                reply_log = json.load(f)
            log(f"📂 Existing history: {len(reply_log.get('replies', []))} replies")
        except Exception:
            pass

    history = load_replied_history()
    for hid in history.keys():
        replied_ids.add(hid)
    log(f"📂 Replied history cache: {len(history)} IDs")

    posts = fetch_posts_with_fallback()
    if not posts:
        return None

    bad_posts = load_bad_posts()
    if bad_posts:
        before = len(posts)
        posts = [p for p in posts if p.get("id") not in bad_posts]
        log(f"🧹 Filtered bad posts: {before} → {len(posts)}")

    if not posts:
        log("ℹ️ No posts after filtering")
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
    log(f"✅ {total_comments} comments fetched from {len(posts)} posts")

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

        log(f"🔍 Post {post_id} | {post_message} | {len(comments)} comments | 🎮 {game_name}")

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

            if not is_within_time_window(comment_time):
                continue

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

    log(f"\n📊 Total valid comments: {len(valid_comments)}")

    if not valid_comments:
        replies_map = {}
    else:
        log(f"📦 Batch: {len(valid_comments)} comments")
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
                "time_window_hours": MAX_COMMENT_AGE_HOURS,
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
        log(f"💾 Saved {len(replied_data['replied'])} IDs")
    except Exception as e:
        log(f"⚠️ replied_file save error: {e}")

    reply_log["replies"] = reply_log.get("replies", [])[-500:]
    reply_log["skipped"] = reply_log.get("skipped", [])[-200:]
    reply_log["last_updated"] = now_ist_ampm()
    reply_log["time_window_hours"] = MAX_COMMENT_AGE_HOURS
    try:
        with open(SHARED_REPLY_LOG, 'w', encoding='utf-8') as f:
            json.dump(reply_log, f, indent=2, ensure_ascii=False)
        log(f"💾 Shared log updated")
    except Exception as e:
        log(f"⚠️ reply_log save error: {e}")

    log(f"🤖 Done. {replies_count} new replies | window={window_days}d")
    return reply_log


# ============================================================
# 🔄 GIT PUSH
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
    window_days = MAX_COMMENT_AGE_HOURS // 24
    log("=" * 60)
    log("🚀 SPLIT SCRIPT v13.2 — FIXED 404 + 400")
    log("=" * 60)
    log(f"📂 Writes ONLY: {SHARED_REPLY_LOG}")
    log(f"📂 Writes ONLY: {SHARED_REPLIED_IDS}")
    log(f"⏰ Time window: {MAX_COMMENT_AGE_HOURS}h ({window_days} days)")
    log(f"📊 Posts to scan: {POSTS_TO_SCAN} | Workers: {COMMENT_FETCH_WORKERS}")
    log(f"📄 Max comment pages: {MAX_COMMENT_PAGES} (100/page)")
    log(f"🤖 FIXED: {FIXED_MODEL}")
    log(f"🤖 FALLBACK: {FALLBACK_MODEL}")
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

    files_to_push = [SHARED_REPLY_LOG, SHARED_REPLIED_IDS]
    if os.path.exists(BAD_POSTS_FILE):
        files_to_push.append(BAD_POSTS_FILE)

    try:
        git_commit_and_push(files_to_push)
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
