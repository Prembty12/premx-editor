import os
import glob
import json
import random
import requests
import sys
import subprocess
import re
from datetime import datetime, timedelta, timezone

# 🇮🇳 Indian Standard Time
try:
    from zoneinfo import ZoneInfo
    IST = ZoneInfo("Asia/Kolkata")
except Exception:
    IST = timezone(timedelta(hours=5, minutes=30))

def now_ist():
    return datetime.now(IST)

def now_ist_str():
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")

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


# 📦 PDF aur Graph
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


# 🔑 Gemini Keys (6 keys)
GEMINI_KEYS = [
    os.environ.get("GEMINI_API_KEY_1"),
    os.environ.get("GEMINI_API_KEY_2"),
    os.environ.get("GEMINI_API_KEY_3"),
    os.environ.get("GEMINI_API_KEY_4"),
    os.environ.get("GEMINI_API_KEY_5"),
    os.environ.get("GEMINI_API_KEY_6"),
]

FB_PAGE_ID = os.environ.get("PAGE_ID")
FB_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")

DAYS_LIMIT = 28
MAX_REPLIES_PER_RUN = 5
MIN_COMMENT_AGE_MIN = 2
MAX_COMMENT_AGE_HOURS = 48

AUTO_COMMENT_ENABLED = os.environ.get("AUTO_COMMENT", "true").lower() == "true"

# ✅ Live log file
LIVE_LOG_FILE = "logs/auto_reply_live.log"
os.makedirs("logs", exist_ok=True)


def log(msg):
    sys.stderr.write(f"{msg}\n")
    sys.stderr.flush()


def log_live(msg, also_file=True):
    """Console + file dono pe likhta hai"""
    ts = now_ist_ampm()
    line = f"[{ts}] {msg}"
    sys.stderr.write(f"{line}\n")
    sys.stderr.flush()
    if also_file:
        try:
            with open(LIVE_LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(line + "\n")
        except Exception:
            pass


def normalize(s):
    if not s:
        return ""
    return re.sub(r'[^a-z0-9]', '', s.lower())


def extract_urls(text):
    urls = re.findall(r'https?://[^\s\)\]\'"<>,;]+', text)
    cleaned = []
    seen = set()
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
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if url.startswith("/"):
        return f"https://www.facebook.com{url}"
    return f"https://www.facebook.com/{url}"


def fix_ig_url(url):
    if not url:
        return ""
    url = str(url).strip()
    if url.startswith("http://") or url.startswith("https://"):
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


# ============================================================
# 🤖 GEMINI INTEGRATION
# ============================================================
def call_gemini_api(api_key, prompt, max_tokens=600):
    """Gemini API call — detailed logging with key info"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.9,
            "maxOutputTokens": max_tokens,
            "topP": 0.95,
        }
    }
    key_short = (api_key[:10] + "...") if api_key else "NONE"
    log_live(f"🌐 Gemini call | Key: {key_short} | Prompt: {len(prompt)} chars")

    try:
        res = requests.post(url, json=payload, timeout=30)
        log_live(f"📡 HTTP {res.status_code} (key {key_short})")

        if res.status_code == 200:
            data = res.json()
            text = data['candidates'][0]['content']['parts'][0]['text']
            log_live(f"✅ Gemini OK | Reply len: {len(text)}")
            return text.strip()
        else:
            try:
                err_data = res.json()
                err_code = err_data.get("error", {}).get("code", "?")
                err_msg = err_data.get("error", {}).get("message", "")[:150]
                log_live(f"❌ Gemini FAIL | HTTP {res.status_code} | code={err_code} | {err_msg}")
            except Exception:
                log_live(f"❌ Gemini FAIL | HTTP {res.status_code} | {res.text[:150]}")
    except Exception as e:
        log_live(f"💥 Gemini EXCEPTION | Key: {key_short} | {e}")
    return None


# ============================================================
# 🚫 ABUSE DETECTION
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

FORBIDDEN_REPLY_WORDS = [
    "maa", "ma", "mata", "behen", "behan", "baap", "beti", "biwi",
    "caste", "religion", "hindu", "muslim", "christian", "sikh",
    "kill", "die", "death", "murder", "rape", "suicide",
]


def detect_abuse(text):
    text_lower = text.lower()
    for pattern in FAMILY_ABUSE_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return "family_abuse"
    for pattern in ABUSE_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return "general_abuse"
    return "none"


def is_spam(text):
    text_lower = text.lower()
    spam_indicators = [
        "http://", "https://", ".com", ".xyz", "click here",
        "follow me", "dm me", "join my", "subscribe my",
    ]
    for indicator in spam_indicators:
        if indicator in text_lower:
            return True
    return False


# ============================================================
# 🤖 BATCH GEMINI REPLY (Ek call mein 5, 4, 3...)
# ============================================================
def generate_batch_replies(comments_batch, game_name, post_title):
    """
    comments_batch: list of dicts [{id, text, is_abuse}, ...]
    Returns: list of dicts [{id, reply}, ...] or None
    """
    if not comments_batch:
        return None

    keys = [k for k in GEMINI_KEYS if k]
    if not keys:
        log_live("🚫 Koi Gemini key nahi mili")
        return None

    batch_size = len(comments_batch)

    log_live("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    log_live(f"📦 BATCH: {batch_size} comments | Game: {game_name}")
    log_live(f"📝 Post: {post_title[:60]}")

    # ✅ Har comment ko prompt mein daalo
    comments_lines = []
    for idx, c in enumerate(comments_batch, 1):
        abuse_tag = " [HATER/ABUSE]" if c.get("is_abuse") else ""
        comments_lines.append(f'{idx}. id="{c["id"]}"{abuse_tag} | comment: "{c["text"]}"')
    comments_block = "\n".join(comments_lines)

    prompt = f"""You are a witty gaming content creator replying to comments on Facebook/Instagram Reels.

CONTEXT:
- Game: {game_name}
- Post: {post_title}

COMMENTS TO REPLY ({batch_size} total):
{comments_block}

RULES:
- For EACH comment, write a short, engaging, human-like reply (1-2 lines max).
- Match the tone of each comment (funny, hype, question, hater, etc.).
- If marked [HATER/ABUSE]: be SAVAGE but RESPECTFUL. Never abuse back. Never insult family/religion/caste.
- Use 0-2 emojis max per reply.
- Never repeat the same reply for different comments.
- Reply in the SAME language as the comment (Hinglish/English/Hindi).
- Keep it natural, like a real gamer.

⚠️ CRITICAL:
- Return EXACTLY {batch_size} replies — no more, no less.
- Each reply MUST use the EXACT 'id' string from the input above.
- Do NOT invent new ids.
- Return ONLY a valid JSON array, no markdown, no extra text:

[
  {{"id": "<exact_id_1>", "reply": "<reply_1>"}},
  {{"id": "<exact_id_2>", "reply": "<reply_2>"}}
]
"""

    log_live(f"📝 Prompt length: {len(prompt)} chars")

    # ✅ Key rotation with retry
    tried_keys = set()
    max_attempts = len(keys) * 2

    for attempt in range(1, max_attempts + 1):
        available = [k for k in keys if k not in tried_keys]
        if not available:
            log_live(f"❌ Saari {len(keys)} keys try ho chuki hain")
            break
        key = random.choice(available)
        tried_keys.add(key)
        key_short = key[:10] + "..."

        log_live(f"🎯 Attempt {attempt}/{max_attempts} | Key: {key_short}")

        response = call_gemini_api(key, prompt, max_tokens=800)

        if response:
            # ✅ Markdown wrapper hatao
            cleaned = re.sub(r'^```json\s*', '', response.strip())
            cleaned = re.sub(r'^```\s*', '', cleaned)
            cleaned = re.sub(r'\s*```$', '', cleaned).strip()

            try:
                replies = json.loads(cleaned)
                if isinstance(replies, list) and len(replies) > 0:
                    log_live(f"✅ Batch JSON parsed | {len(replies)} replies")
                    for r in replies:
                        log_live(f"   💬 {r.get('id', '?')[:30]} → {r.get('reply', '')[:80]}")
                    return replies
                else:
                    log_live(f"⚠️ JSON list nahi mila ya khali hai")
            except json.JSONDecodeError as e:
                log_live(f"⚠️ JSON parse fail: {e}")
                log_live(f"   Raw (first 200): {cleaned[:200]}")
        else:
            log_live(f"⚠️ Key {key_short} fail — agli key try")

    log_live(f"❌ Saari {len(tried_keys)} keys fail — koi reply nahi")
    return None


def is_reply_safe(reply_text, is_abuse=False):
    if not reply_text or len(reply_text.strip()) < 3:
        return False, "too_short"
    if len(reply_text) > 300:
        return False, "too_long"
    reply_lower = reply_text.lower()
    if "http" in reply_lower or ".com" in reply_lower:
        return False, "contains_link"
    for word in FORBIDDEN_REPLY_WORDS:
        if word in reply_lower:
            return False, f"forbidden_word_{word}"
    for pattern in ABUSE_PATTERNS:
        if re.search(pattern, reply_lower, re.IGNORECASE):
            return False, "reply_contains_abuse"
    return True, "safe"


# ============================================================
# 🤖 AUTO-REPLY FUNCTIONS (FB ONLY)
# ============================================================
def fetch_fb_comments(post_id, since_timestamp=None):
    url = f"https://graph.facebook.com/v24.0/{post_id}/comments"
    params = {
        "fields": "id,message,from,created_time,can_reply",
        "access_token": FB_ACCESS_TOKEN,
        "limit": 50,
    }
    if since_timestamp:
        params["since"] = since_timestamp
    try:
        res = requests.get(url, params=params, timeout=15)
        if res.status_code == 200:
            return res.json().get("data", [])
        else:
            log(f"⚠️ FB comments fetch error: {res.status_code} {res.text[:200]}")
    except Exception as e:
        log(f"⚠️ FB comments fetch exception: {e}")
    return []


def check_if_already_replied(comment_id):
    url = f"https://graph.facebook.com/v24.0/{comment_id}/comments"
    params = {"fields": "id,from", "access_token": FB_ACCESS_TOKEN, "limit": 10}
    try:
        res = requests.get(url, params=params, timeout=10)
        if res.status_code == 200:
            replies = res.json().get("data", [])
            for reply in replies:
                if reply.get("from", {}).get("id") == FB_PAGE_ID:
                    return True
    except Exception:
        pass
    return False


def post_fb_reply(comment_id, reply_text):
    if not AUTO_COMMENT_ENABLED:
        log(f"🚫 [AUTO_COMMENT OFF] Would post: {reply_text[:80]}")
        return f"disabled_{comment_id}"

    url = f"https://graph.facebook.com/v24.0/{comment_id}/comments"
    payload = {"message": reply_text, "access_token": FB_ACCESS_TOKEN}
    try:
        res = requests.post(url, data=payload, timeout=15)
        if res.status_code == 200:
            return res.json().get("id")
        else:
            log_live(f"❌ Reply post fail: HTTP {res.status_code} | {res.text[:150]}")
    except Exception as e:
        log_live(f"💥 Reply post exception: {e}")
    return None


def process_fb_comments(actual_posted_titles):
    if not AUTO_COMMENT_ENABLED:
        log("🚫 Auto-comment disabled — skipping reply processing")
        return None

    log_live("🤖 Auto-reply processing started...")

    # ✅ Live log reset (har run fresh)
    try:
        with open(LIVE_LOG_FILE, 'w', encoding='utf-8') as f:
            f.write(f"=== Auto-Reply Live Log: {now_ist_ampm()} IST ===\n\n")
    except Exception:
        pass

    # ✅ Replied IDs load
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
        except Exception:
            pass

    replies_count = 0
    cutoff_time = (now_ist() - timedelta(hours=MAX_COMMENT_AGE_HOURS)).timestamp()
    min_age_time = (now_ist() - timedelta(minutes=MIN_COMMENT_AGE_MIN)).timestamp()

    # ✅ Ek batch mein jitne comment mil sakte hain (max 5)
    batch = []   # [{id, text, is_abuse, video, post_id}, ...]

    for game_name, videos in actual_posted_titles.items():
        if replies_count >= MAX_REPLIES_PER_RUN:
            break
        for video in videos:
            if replies_count + len(batch) >= MAX_REPLIES_PER_RUN:
                break
            if not video.get("fb_posted"):
                continue
            fb_link = video.get("fb_link", "")
            if not fb_link:
                continue
            post_id_match = re.search(r'/(\d+)/?$', fb_link)
            if not post_id_match:
                continue
            post_id = post_id_match.group(1)
            comments = fetch_fb_comments(post_id)
            log_live(f"📥 Post {post_id}: {len(comments)} comments fetched")

            for comment in comments:
                if replies_count + len(batch) >= MAX_REPLIES_PER_RUN:
                    break
                comment_id = comment.get("id", "")
                comment_text = comment.get("message", "").strip()
                comment_time = comment.get("created_time", "")
                can_reply = comment.get("can_reply", True)

                if not comment_id or not comment_text:
                    continue
                if comment_id in replied_ids:
                    continue
                if not can_reply:
                    continue
                from_data = comment.get("from", {})
                if from_data.get("id") == FB_PAGE_ID:
                    continue
                try:
                    dt = datetime.fromisoformat(comment_time.replace("+0000", "+00:00"))
                    comment_ts = dt.timestamp()
                    if comment_ts < cutoff_time:
                        continue
                    if comment_ts > min_age_time:
                        continue
                except Exception:
                    pass

                abuse_type = detect_abuse(comment_text)
                if abuse_type == "family_abuse":
                    log_live(f"🚫 FAMILY ABUSE — skip {comment_id}")
                    reply_log["skipped"].append({
                        "comment_id": comment_id, "comment_text": comment_text[:100],
                        "reason": "family_abuse", "timestamp": now_ist_ampm(),
                    })
                    reply_log["total_skipped"] = reply_log.get("total_skipped", 0) + 1
                    replied_ids.add(comment_id)
                    continue

                if is_spam(comment_text):
                    log_live(f"🚫 SPAM — skip {comment_id}")
                    reply_log["skipped"].append({
                        "comment_id": comment_id, "comment_text": comment_text[:100],
                        "reason": "spam", "timestamp": now_ist_ampm(),
                    })
                    reply_log["total_skipped"] = reply_log.get("total_skipped", 0) + 1
                    replied_ids.add(comment_id)
                    continue

                if check_if_already_replied(comment_id):
                    log_live(f"⏭️ Already replied (FB verify) — {comment_id}")
                    replied_ids.add(comment_id)
                    continue

                # ✅ Batch mein add karo
                batch.append({
                    "id": comment_id,
                    "text": comment_text,
                    "is_abuse": (abuse_type == "general_abuse"),
                    "game": game_name,
                    "post_id": post_id,
                    "video": video,
                })
                log_live(f"➕ Added to batch: {comment_id} | \"{comment_text[:60]}\"")

    # ✅ Ab ek saath Gemini ko bhejo
    if not batch:
        log_live("⚠️ Batch khali — koi fresh comment nahi mila")
    else:
        log_live(f"📦 Sending {len(batch)} comments to Gemini in ONE call...")

        # Game name pehle comment se lo (ya "Mixed")
        batch_game = batch[0]["game"] if len(set(b["game"] for b in batch)) == 1 else "Mixed Games"
        batch_title = batch[0]["video"].get("title", "")

        replies = generate_batch_replies(batch, batch_game, batch_title)

        if replies:
            # ✅ Replies ko map karo id → reply
            reply_map = {}
            for r in replies:
                rid = str(r.get("id", "")).strip()
                rtext = str(r.get("reply", "")).strip()
                if rid and rtext:
                    reply_map[rid] = rtext

            log_live(f"📨 {len(reply_map)} replies mapped | Batch size: {len(batch)}")

            # ✅ Ab har comment pe post karo
            for c in batch:
                cid = c["id"]
                ctext = c["text"]
                cgame = c["game"]
                cpost = c["post_id"]
                cvideo = c["video"]
                cis_abuse = c["is_abuse"]

                reply_text = reply_map.get(cid)

                if not reply_text:
                    log_live(f"❌ Gemini ne is comment ka reply nahi diya: {cid}")
                    reply_log["skipped"].append({
                        "comment_id": cid, "comment_text": ctext[:100],
                        "reason": "no_reply_from_gemini",
                        "timestamp": now_ist_ampm(),
                    })
                    continue

                safe, reason = is_reply_safe(reply_text, is_abuse=cis_abuse)
                if not safe:
                    log_live(f"⚠️ Reply UNSAFE ({reason}) for {cid} — skip")
                    reply_log["skipped"].append({
                        "comment_id": cid, "comment_text": ctext[:100],
                        "reason": f"unsafe_{reason}",
                        "timestamp": now_ist_ampm(),
                    })
                    replied_ids.add(cid)
                    continue

                log_live(f"📤 Posting reply → {cid} | \"{reply_text[:70]}\"")
                reply_id = post_fb_reply(cid, reply_text)

                if reply_id:
                    replies_count += 1
                    log_live(f"✅ POSTED | {cid} | reply_id={reply_id}")
                    reply_log["replies"].append({
                        "reply_id": reply_id,
                        "comment_id": cid,
                        "post_id": cpost,
                        "user_comment": ctext[:200],
                        "gemini_reply": reply_text,
                        "type": "savage" if cis_abuse else "friendly",
                        "game": cgame,
                        "post_title": cvideo.get("title", "")[:100],
                        "fb_post_link": cvideo.get("fb_link", ""),
                        "source_link": cvideo.get("source_link", ""),
                        "timestamp": now_ist_ampm(),
                        "status": "posted",
                    })
                    reply_log["total_replies"] = reply_log.get("total_replies", 0) + 1
                    replied_ids.add(cid)
                else:
                    log_live(f"❌ Reply post FAIL for {cid}")

    # ✅ Save files
    os.makedirs("logs", exist_ok=True)
    replied_data["replied"] = list(replied_ids)[-5000:]
    replied_data["last_updated"] = now_ist_ampm()
    with open(replied_file, 'w', encoding='utf-8') as f:
        json.dump(replied_data, f, indent=2)

    reply_log["replies"] = reply_log.get("replies", [])[-200:]
    reply_log["skipped"] = reply_log.get("skipped", [])[-100:]
    reply_log["last_updated"] = now_ist_ampm()
    with open(reply_log_file, 'w', encoding='utf-8') as f:
        json.dump(reply_log, f, indent=2)

    log_live(f"🤖 Auto-reply done. {replies_count} replies posted.")
    return reply_log


# ============================================================
# 📈 TRENDING GAMES
# ============================================================
def detect_trending_games(actual_posted_titles, game_views_summary, days=7):
    game_stats = {}
    for g_name, videos in actual_posted_titles.items():
        total_views = 0
        video_count = 0
        latest_post = ""
        latest_fb_link = ""
        latest_source = ""
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
        result = {"last_updated": now_ist_ampm(), "period_days": days, "trending": [], "below_avg": [], "recommendation": None}
        os.makedirs("logs", exist_ok=True)
        with open("logs/trending_cache.json", 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2)
        return result

    all_avgs = [s["avg_views"] for s in game_stats.values()]
    overall_avg = sum(all_avgs) / len(all_avgs) if all_avgs else 1

    trending_list = []
    for g, s in game_stats.items():
        ratio = s["avg_views"] / overall_avg if overall_avg > 0 else 0
        if ratio >= 2.0: trend = "viral"
        elif ratio >= 1.5: trend = "trending"
        elif ratio >= 1.0: trend = "steady"
        elif ratio >= 0.5: trend = "slow"
        else: trend = "below_avg"
        trending_list.append({
            "game": g, "views_7d": s["total_views"],
            "avg_per_video": s["avg_views"], "trend": trend, "ratio": ratio,
            "fb_link": s["fb_link"], "source_link": s["source_link"],
        })

    trending_list.sort(key=lambda x: x["avg_per_video"], reverse=True)
    top = [t for t in trending_list if t["trend"] in ("viral", "trending", "steady")][:5]
    below = [t for t in trending_list if t["trend"] in ("slow", "below_avg")][:5]
    best = trending_list[0] if trending_list else None

    result = {
        "last_updated": now_ist_ampm(), "period_days": days,
        "trending": top, "below_avg": below, "recommendation": best,
    }
    os.makedirs("logs", exist_ok=True)
    with open("logs/trending_cache.json", 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2)
    return result


# ============================================================
# 🎯 BEST TIME TO POST
# ============================================================
def analyze_best_time(all_history):
    if not all_history:
        try:
            with open("logs/dashboard_history.json", 'r', encoding='utf-8') as f:
                all_history = json.load(f)
        except Exception:
            all_history = {}

    hourly = {}
    daily = {}

    for game, entries in all_history.items():
        for entry in entries:
            ts = entry.get("timestamp", "")
            views = entry.get("views", 0)
            if not ts:
                continue
            dt = utc_to_ist(ts)
            if dt is None:
                try:
                    dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                except Exception:
                    try:
                        dt = datetime.strptime(ts, "%Y-%m-%d %I:%M:%S %p")
                    except Exception:
                        continue
            hour = dt.hour
            day_name = dt.strftime("%A")
            hourly.setdefault(hour, []).append(views)
            daily.setdefault(day_name, []).append(views)

    hourly_stats = []
    for hour, views_list in hourly.items():
        if len(views_list) < 2:
            continue
        avg = sum(views_list) // len(views_list)
        hourly_stats.append({"hour": hour, "posts": len(views_list), "avg_views": avg})

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
            daily_stats[day] = {"avg_views": sum(views_list) // len(views_list), "posts": len(views_list)}

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
# 🎨 DASHBOARD SECTIONS
# ============================================================
def generate_trending_section():
    try:
        with open("logs/trending_cache.json", 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return ""
    lines = []
    lines.append("\n--- \n\n## 📈 Trending Games (Last 7 Days)\n\n")
    lines.append(f"> Auto-detected based on views performance | Last Updated: {data.get('last_updated', 'N/A')}\n\n")
    trending = data.get("trending", [])
    if trending:
        lines.append("| Rank | Game Name | Views (7d) | Avg / Video | Trend | FB Post | Source |\n")
        lines.append("|:---:|---|---|---|---|---|---|\n")
        for idx, t in enumerate(trending, 1):
            medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
            rank_icon = medals[idx-1] if idx <= 5 else str(idx)
            trend_icon = {"viral": "🚀 **VIRAL**", "trending": "🔥 Trending", "steady": "⚡ Steady"}.get(t["trend"], "📈")
            fb_link = t.get("fb_link", "")
            fb_md = f"[🔵]({fb_link})" if fb_link else "_N/A_"
            src_link = t.get("source_link", "")
            src_md = f"[📂]({src_link})" if src_link else "_N/A_"
            lines.append(f"| {rank_icon} | **{t['game']}** | {t['views_7d']:,} | {t['avg_per_video']:,} | {trend_icon} | {fb_md} | {src_md} |\n")
    below = data.get("below_avg", [])
    if below:
        lines.append("\n### 📉 Below Average This Week\n\n")
        lines.append("| Game | Views (7d) | Avg |\n|---|---|---|\n")
        for b in below:
            lines.append(f"| {b['game']} | {b['views_7d']:,} | {b['avg_per_video']:,} |\n")
    rec = data.get("recommendation")
    if rec:
        lines.append("\n### 💡 Recommendation\n\n")
        lines.append(f"**Best game to post next:** 🚀 **{rec['game']}** (Avg {rec['avg_per_video']:,} views/video)\n")
    return "".join(lines)


def generate_best_time_section():
    try:
        with open("logs/best_time_analysis.json", 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return ""
    lines = []
    lines.append("\n--- \n\n## 🎯 Best Time to Post (IST)\n\n")
    lines.append(f"> Analysis from {data.get('total_posts_analyzed', 0)} posts | Last Updated: {data.get('last_updated', 'N/A')}\n\n")
    slots = data.get("top_slots", [])
    if slots:
        lines.append("| Rank | Time (IST) | Posts | Avg Views | Recommendation |\n")
        lines.append("|:---:|---|:---:|:---:|---|\n")
        for s in slots:
            rec_icon = {"BEST": "🔥 **BEST**", "Great": "⚡ **Great**", "Good": "✅ **Good**", "Average": "📊 Average", "Below avg": "📉 Below avg"}.get(s["recommendation"], s["recommendation"])
            lines.append(f"| {s['icon']} | **{s['time_slot']}** | {s['posts']} | **{s['avg_views']:,}** | {rec_icon} |\n")
    today = data.get("today_suggestion")
    if today:
        lines.append(f"\n### 💡 Today's Suggestion\n\n**Aaj post karo:** ⏰ **{today['time_slot']} IST**\n")
    daily = data.get("daily", {})
    if daily:
        lines.append("\n### 📅 Weekly Pattern\n\n| Day | Posts | Avg Views |\n|---|---|---|\n")
        for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]:
            if day in daily:
                lines.append(f"| {day} | {daily[day]['posts']} | {daily[day]['avg_views']:,} |\n")
    return "".join(lines)


def generate_auto_reply_section():
    try:
        with open("logs/auto_reply_log.json", 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return ""
    lines = []
    lines.append("\n--- \n\n## 🤖 Auto-Reply Log (Facebook Only)\n\n")
    status = "🚫 **DISABLED**" if not AUTO_COMMENT_ENABLED else "✅ **ACTIVE**"
    lines.append(f"> Auto-Comment Status: {status} | Last Updated: {data.get('last_updated', 'N/A')} | ")
    lines.append(f"Total Replies: {data.get('total_replies', 0)} | Skipped: {data.get('total_skipped', 0)}\n\n")
    replies = data.get("replies", [])
    if replies:
        friendly_count = sum(1 for r in replies if r.get("type") == "friendly")
        savage_count = sum(1 for r in replies if r.get("type") == "savage")
        lines.append("### 📊 Stats\n\n| Metric | Value |\n|---|---|\n")
        lines.append(f"| Friendly Replies | {friendly_count} |\n")
        lines.append(f"| Savage Replies | {savage_count} |\n")
        lines.append(f"| Total | {len(replies)} |\n\n")
        lines.append("### 💬 Recent Replies (Last 20)\n\n")
        lines.append("| # | Time | User Comment | Gemini Reply | Type | FB Post | Source |\n")
        lines.append("|---|---|---|---|---|---|---|\n")
        for idx, r in enumerate(list(reversed(replies[-20:])), 1):
            comment = (r.get("user_comment", "") or "").replace("\n", " ").replace("|", "\\|")[:60]
            reply = (r.get("gemini_reply", "") or "").replace("\n", " ").replace("|", "\\|")[:80]
            ts = r.get("timestamp", "")[:20]
            rtype = "😎 Savage" if r.get("type") == "savage" else "✅ Friendly"
            fb_link = r.get("fb_post_link", "")
            fb_md = f"[🔵]({fb_link})" if fb_link else "_N/A_"
            src_link = r.get("source_link", "")
            src_md = f"[📂]({src_link})" if src_link else "_N/A_"
            lines.append(f"| {idx} | {ts} | {comment} | {reply} | {rtype} | {fb_md} | {src_md} |\n")
        savages = [r for r in replies if r.get("type") == "savage"][-5:]
        if savages:
            lines.append("\n### 😎 Savage Replies (Last 5)\n\n| User Abuse | Gemini Reply | FB Link |\n|---|---|---|\n")
            for s in reversed(savages):
                comment = (s.get("user_comment", "") or "").replace("\n", " ").replace("|", "\\|")[:80]
                reply = (s.get("gemini_reply", "") or "").replace("\n", " ").replace("|", "\\|")[:100]
                fb_link = s.get("fb_post_link", "")
                fb_md = f"[🔵]({fb_link})" if fb_link else "_N/A_"
                lines.append(f"| {comment} | {reply} | {fb_md} |\n")
    skipped = data.get("skipped", [])[-5:]
    if skipped:
        lines.append("\n### ⏭️ Skipped Comments (Last 5)\n\n| Comment | Reason |\n|---|---|\n")
        for s in reversed(skipped):
            comment = (s.get("comment_text", "") or "").replace("\n", " ").replace("|", "\\|")[:80]
            reason = s.get("reason", "").replace("_", " ")
            lines.append(f"| {comment} | {reason} |\n")
    return "".join(lines)


# ============================================================
# 📦 EXISTING FUNCTIONS
# ============================================================
def git_commit_and_push(file_paths_to_add, commit_message="Auto-Agent: Sync dashboard [skip ci]"):
    try:
        subprocess.run(["git", "config", "--global", "user.name", "github-actions[bot]"],
                       check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "config", "--global", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"],
                       check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for path in file_paths_to_add:
            if os.path.exists(path):
                subprocess.run(["git", "add", path],
                               check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        commit_res = subprocess.run(["git", "commit", "-m", commit_message],
                                    capture_output=True, text=True, check=False)
        log(f"🔄 Git Commit: {commit_res.stdout.strip()} {commit_res.stderr.strip()}")
        push_res = subprocess.run(["git", "push"],
                                  capture_output=True, text=True, check=False)
        log(f"🔄 Git Push: {push_res.stdout.strip()} {push_res.stderr.strip()}")
    except Exception as e:
        log(f"⚠️ Git auto-push error: {e}")


def generate_visual_reports(game_views_summary, game_stats):
    reports_dir = "logs/reports"
    os.makedirs(reports_dir, exist_ok=True)
    chart_path = os.path.join(reports_dir, "views_chart.png")
    pdf_path = os.path.join(reports_dir, "gaming_agent_report.pdf")
    total_platform_views = sum(game_views_summary.values()) or 1
    analytics_data = []
    for g_n, g_v in game_views_summary.items():
        uploaded_count = game_stats.get(g_n, {}).get("uploaded_count", 0)
        avg_views = int(g_v / uploaded_count) if uploaded_count > 0 else 0
        share_pct = round((g_v / total_platform_views) * 100, 2)
        analytics_data.append({
            "game": g_n, "total_views": g_v, "uploaded_count": uploaded_count,
            "avg_views": avg_views, "share_pct": share_pct
        })
    sorted_analytics = sorted(analytics_data, key=lambda x: x["total_views"], reverse=True)
    if MATPLOTLIB_AVAILABLE and sorted_analytics:
        try:
            games = [item["game"] for item in sorted_analytics]
            total_v = [item["total_views"] for item in sorted_analytics]
            avg_v = [item["avg_views"] for item in sorted_analytics]
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
            ax1.bar(games, total_v, color='#4A90E2')
            ax1.set_title("Total Views Leaderboard", fontsize=12, fontweight='bold')
            ax1.set_ylabel("Views", fontsize=10, fontweight='bold')
            ax1.tick_params(axis='x', rotation=30)
            ax2.bar(games, avg_v, color='#50E3C2')
            ax2.set_title("Efficiency: Avg Views per Video", fontsize=12, fontweight='bold')
            ax2.set_ylabel("Avg Views / Video", fontsize=10, fontweight='bold')
            ax2.tick_params(axis='x', rotation=30)
            plt.suptitle("Advanced Gaming Performance Analytics", fontsize=14, fontweight='bold')
            plt.tight_layout()
            plt.savefig(chart_path, dpi=300)
            plt.close()
        except Exception as e:
            log(f"⚠️ Chart error: {e}")
    return sorted_analytics


def save_rotation_history(game_list, chosen_game, memory, memory_file="logs/rotation_history.json"):
    os.makedirs("logs", exist_ok=True)
    rotation_data = {
        "total_games": 0, "rotation_order": [], "current_index": 0,
        "current_game": "", "next_game": "", "next_game_position": 0,
        "last_updated": "", "total_runs": 0, "rotation_log": [], "all_games": []
    }
    if os.path.exists(memory_file):
        try:
            with open(memory_file, 'r', encoding='utf-8') as f:
                existing = json.load(f)
                if isinstance(existing, dict):
                    rotation_data.update(existing)
        except Exception:
            pass
    rotation_data["rotation_order"] = list(game_list)
    rotation_data["total_games"] = len(game_list)
    if chosen_game in game_list:
        current_idx = game_list.index(chosen_game)
        next_idx = (current_idx + 1) % len(game_list)
        rotation_data["current_index"] = current_idx
        rotation_data["current_game"] = chosen_game
        rotation_data["next_game"] = game_list[next_idx]
        rotation_data["next_game_position"] = next_idx + 1
    rotation_data["last_updated"] = now_ist_ampm()
    rotation_data["total_runs"] = len(rotation_data.get("rotation_log", [])) + 1
    rotation_data.setdefault("rotation_log", []).append({
        "run": rotation_data["total_runs"],
        "game": chosen_game,
        "timestamp": now_ist_ampm(),
    })
    all_games_list = []
    current_idx = rotation_data["current_index"]
    for i, g in enumerate(game_list):
        uploaded = memory.get("game_stats", {}).get(g, {}).get("uploaded_count", 0)
        last_run = 0
        for log_entry in rotation_data.get("rotation_log", []):
            if log_entry["game"] == g:
                last_run = log_entry["run"]
        if i == current_idx:
            next_turn_in = 0
            status = "current"
        elif i > current_idx:
            next_turn_in = i - current_idx
            status = "next_up" if next_turn_in == 1 else "waiting"
        else:
            next_turn_in = len(game_list) - current_idx + i
            status = "next_up" if next_turn_in == 1 else "waiting"
        all_games_list.append({
            "position": i + 1, "game": g, "uploaded": uploaded,
            "last_run": last_run, "next_turn_in": next_turn_in, "status": status
        })
    rotation_data["all_games"] = all_games_list
    with open(memory_file, 'w', encoding='utf-8') as f:
        json.dump(rotation_data, f, indent=4)
    return rotation_data


def load_source_data():
    source_links_map = {}
    source_videos_count = {}
    source_titles_map = {}
    posted_dir = "posted_links_editor"
    if not os.path.exists(posted_dir):
        return source_links_map, source_videos_count, source_titles_map
    for fname in os.listdir(posted_dir):
        if fname.endswith("_posted_links_editor.txt"):
            gname = fname.replace("_posted_links_editor.txt", "")
            try:
                with open(os.path.join(posted_dir, fname), 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                urls = extract_urls(content)
                if urls:
                    source_links_map[gname] = urls
                vid_count = content.count("Video id :")
                if vid_count == 0:
                    vid_count = len(urls)
                source_videos_count[gname] = vid_count
                titles = re.findall(r'Title\s*:\s*(.+)', content)
                source_titles_map[gname] = [t.strip() for t in titles]
            except Exception:
                pass
    return source_links_map, source_videos_count, source_titles_map


def parse_posted_file(filepath, game_name):
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    lines = content.split('\n')
    posts = []
    current_video = {}
    for line in lines:
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
                'video_name': video_name, 'platform': 'FB + IG', 'game': game_name
            }
        elif 'Video id :' in line:
            current_video['vid_id'] = line.split('Video id :')[-1].strip()
        elif 'Title :' in line:
            current_video['title'] = line.split('Title :')[-1].strip()
    if current_video.get('vid_id'):
        posts.append(current_video)
    return posts


def fetch_fb_caption(vid_id, page_token):
    url = f"https://graph.facebook.com/v24.0/{vid_id}?fields=description&access_token={page_token}"
    try:
        res = requests.get(url, timeout=5).json()
        caption = res.get('description', '').strip()
        if caption:
            return caption.split('\n')[0].strip()
    except Exception:
        pass
    return None


def fetch_fb_views_by_id(vid_id, page_token):
    url = f"https://graph.facebook.com/v24.0/{vid_id}/video_insights?access_token={page_token}"
    try:
        res = requests.get(url, timeout=5).json()
        for metric in res.get('data', []):
            if metric.get('name') == 'total_video_views':
                values = metric.get('values', [{}])
                return values[0].get('value', 0)
    except Exception:
        pass
    return 0


def fetch_fb_ig_data(game_list):
    from concurrent.futures import ThreadPoolExecutor, as_completed
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
            fpath = os.path.join(posted_dir, fname)
            try:
                with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                blocks = re.split(r'\n\s*\n', content)
                for block in blocks:
                    block_id = ""
                    block_link = ""
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
                file_mtime = datetime.fromtimestamp(os.path.getmtime(filepath), tz=IST)
                if file_mtime < cutoff_date:
                    continue
            except Exception:
                pass
            try:
                posts = parse_posted_file(filepath, game_name)
                for p in posts:
                    all_tasks.append(p)
            except Exception as e:
                log(f"⚠️ Parse error {game_name}: {e}")
        if all_tasks:
            log(f"📊 Total {len(all_tasks)} videos processing (parallel)...")
            def process_video_task(post):
                vid_id = post.get('vid_id')
                if not vid_id:
                    return post
                fb_caption = fetch_fb_caption(vid_id, FB_ACCESS_TOKEN)
                fb_views = fetch_fb_views_by_id(vid_id, FB_ACCESS_TOKEN)
                if fb_caption: title = fb_caption
                elif post.get('title'): title = post['title']
                else:
                    title = post.get('video_name', '').replace('_', ' ').strip()
                    if not title: title = f"Video {vid_id[:8]}"
                post['title'] = title
                post['fb_views'] = fb_views
                post['fb_posted'] = fb_views > 0
                post['fb_link'] = f"https://www.facebook.com/{vid_id}" if fb_views > 0 else ""
                post['status'] = "✅ Live" if fb_views > 0 else "⏳ Pending"
                return post
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = {executor.submit(process_video_task, p): p for p in all_tasks}
                for future in as_completed(futures):
                    try:
                        r = future.result()
                        game = r.get('game')
                        if game in result:
                            vid_id = str(r.get('vid_id', '')).strip()
                            matched_source = id_to_source_map.get(vid_id, "")
                            if not matched_source:
                                matched_source = r.get('link', '')
                            result[game].append({
                                "title": r.get('title', 'Untitled'),
                                "fb_link": fix_fb_url(r.get('fb_link', ''), vid_id),
                                "fb_views": r.get('fb_views', 0),
                                "fb_posted": r.get('fb_posted', False),
                                "ig_link": "", "ig_views": 0, "ig_posted": False,
                                "timestamp": "", "vid_id": vid_id,
                                "video_name": r.get('video_name', ''),
                                "source_link": matched_source,
                            })
                            game_views_summary[game] += r.get('fb_views', 0)
                    except Exception as e:
                        log(f"⚠️ Process error: {e}")
    twenty_eight_days_ago = now_ist() - timedelta(days=DAYS_LIMIT)
    since_timestamp = int(twenty_eight_days_ago.timestamp())
    fb_videos = []
    ig_medias = []
    try:
        fb_url = f"https://graph.facebook.com/v24.0/{FB_PAGE_ID}/videos"
        params = {"fields": "id,title,description,views,permalink_url,created_time",
                  "since": since_timestamp, "access_token": FB_ACCESS_TOKEN, "limit": 100}
        res = requests.get(fb_url, params=params, timeout=20)
        if res.status_code == 200:
            fb_videos = res.json().get("data", [])
            log(f"✅ FB page: {len(fb_videos)} videos fetched")
    except Exception as e:
        log(f"❌ FB page fetch error: {e}")
    try:
        ig_url = f"https://graph.facebook.com/v24.0/{FB_PAGE_ID}"
        ig_params = {"fields": "instagram_business_account", "access_token": FB_ACCESS_TOKEN}
        res_ig_acc = requests.get(ig_url, params=ig_params, timeout=10)
        if res_ig_acc.status_code == 200:
            ig_id = res_ig_acc.json().get("instagram_business_account", {}).get("id")
            if ig_id:
                media_url = f"https://graph.facebook.com/v24.0/{ig_id}/media"
                media_params = {"fields": "id,caption,permalink,timestamp,like_count,comments_count",
                                "access_token": FB_ACCESS_TOKEN, "limit": 100}
                res_ig = requests.get(media_url, params=media_params, timeout=20)
                if res_ig.status_code == 200:
                    ig_medias = res_ig.json().get("data", [])
                    log(f"✅ IG: {len(ig_medias)} media fetched")
    except Exception as e:
        log(f"❌ IG fetch error: {e}")
    for game in game_list:
        game_norm = normalize(game)
        existing_titles = set()
        for v in result[game]:
            existing_titles.add(normalize(v.get("title", ""))[:40])
        for v in fb_videos:
            title = (v.get("title") or v.get("description") or "").strip()
            if not title: continue
            if game_norm and game_norm in normalize(title):
                key = normalize(title)[:40]
                if key in existing_titles: continue
                fb_vid_id = str(v.get("id", "")).strip()
                fb_link = fix_fb_url(v.get("permalink_url", ""), fb_vid_id)
                matched_source = id_to_source_map.get(fb_vid_id, "")
                entry = {
                    "title": title, "fb_link": fb_link,
                    "fb_views": int(v.get("views", 0) or 0),
                    "fb_posted": True, "ig_link": "", "ig_views": 0, "ig_posted": False,
                    "timestamp": v.get("created_time", ""),
                    "vid_id": fb_vid_id, "video_name": "",
                    "source_link": matched_source,
                }
                result[game].append(entry)
                game_views_summary[game] += entry["fb_views"]
                existing_titles.add(key)
        for m in ig_medias:
            caption = (m.get("caption") or "").strip()
            if not caption: continue
            if game_norm and game_norm in normalize(caption):
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
                    matched_source = id_to_source_map.get(ig_media_id, "")
                    result[game].append({
                        "title": caption[:100], "fb_link": "", "fb_views": 0, "fb_posted": False,
                        "ig_link": fix_ig_url(m.get("permalink", "")),
                        "ig_views": ig_views, "ig_posted": True,
                        "timestamp": m.get("timestamp", ""),
                        "vid_id": ig_media_id, "video_name": "",
                        "source_link": matched_source,
                    })
                    game_views_summary[game] += ig_views
                    existing_titles.add(caption_norm)
    games_links_dir = "game_links_editor"
    for game in game_list:
        src_file = None
        for f in os.listdir(games_links_dir):
            if not f.endswith(".txt"): continue
            base = (f.replace(".txt", "").replace("_links_editor", "").replace("_uploaded_links", ""))
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
        log(f"📂 {game}: {len(src_videos)} videos in source file")
        existing_vids_lower = {}
        for v in result[game]:
            vname = (v.get("vid_id") or "").lower()
            vtitle = (v.get("title") or "").lower()
            if vname: existing_vids_lower[vname] = v
            if vtitle: existing_vids_lower[vtitle[:30]] = v
        for sv in src_videos:
            vname = sv["video_name"]
            vname_lower = vname.lower()
            src_link = sv["source_link"]
            matched = False
            for key, v in list(existing_vids_lower.items()):
                v_title_lower = (v.get("title") or "").lower()
                v_vid_lower = (v.get("vid_id") or "").lower()
                if (vname_lower == v_vid_lower
                    or vname_lower in v_title_lower
                    or v_title_lower[:20] == vname_lower[:20]
                    or (len(vname) > 5 and vname_lower[-5:] in v_title_lower)):
                    if not v.get("source_link"):
                        v["source_link"] = src_link
                    if not v.get("video_name"):
                        v["video_name"] = vname
                    matched = True
                    break
            if not matched:
                result[game].append({
                    "title": vname, "fb_link": "", "fb_views": 0, "fb_posted": False,
                    "ig_link": "", "ig_views": 0, "ig_posted": False,
                    "timestamp": "", "vid_id": vname, "video_name": vname,
                    "source_link": src_link, "is_source_only": True,
                })

    for game in game_list:
        posted_v = [x for x in result[game] if x.get("fb_posted") or x.get("ig_posted")]
        pending_v = [x for x in result[game] if not (x.get("fb_posted") or x.get("ig_posted"))]
        posted_v_sorted = sorted(posted_v, key=lambda x: x.get("timestamp", "") or "0000", reverse=True)

        def pending_key(x):
            vname = x.get("video_name") or x.get("vid_id") or ""
            digits = re.findall(r'\d+', vname)
            if digits:
                try:
                    return (0, -int(digits[-1]))
                except ValueError:
                    pass
            return (1, vname)
        pending_v_sorted = sorted(pending_v, key=pending_key)
        result[game] = posted_v_sorted + pending_v_sorted

    return result, game_views_summary


def update_unified_dashboard(game_name, chosen_style, ai_title, specific_uploaded_link,
                             post_link, platform_name, views_count,
                             game_views_summary, game_stats, actual_posted_titles=None,
                             file_mapping=None):
    if actual_posted_titles is None:
        actual_posted_titles = {}
    if file_mapping is None:
        file_mapping = {}
    dashboard_path = "GAMING_DASHBOARD.md"
    leaderboard_json = os.path.join("logs/leaderboard", "games_performance_leaderboard.json")
    os.makedirs("logs/leaderboard", exist_ok=True)
    timestamp = now_ist_ampm()
    history_json = "logs/dashboard_history.json"
    all_history = {}
    if os.path.exists(history_json):
        try:
            with open(history_json, 'r', encoding='utf-8') as f:
                all_history = json.load(f)
        except Exception:
            pass
    if game_name not in all_history:
        all_history[game_name] = []
    new_entry = {
        "timestamp": timestamp, "style": chosen_style, "ai_title": ai_title,
        "actual_posted_title": "", "views": views_count,
        "source_link": specific_uploaded_link, "post_link": post_link,
        "platform": platform_name,
    }
    vids = actual_posted_titles.get(game_name, [])
    if vids:
        for v in vids:
            if v.get("fb_posted") or v.get("ig_posted"):
                new_entry["actual_posted_title"] = v.get("title", "")
                break
    all_history[game_name].append(new_entry)
    try:
        with open(history_json, 'w', encoding='utf-8') as f:
            json.dump(all_history, f, indent=4)
    except Exception:
        pass
    sorted_analytics = generate_visual_reports(game_views_summary, game_stats)
    try:
        with open(leaderboard_json, 'w', encoding='utf-8') as f:
            json.dump([
                {"rank": i + 1, "game_name": item["game"], "total_views": item["total_views"],
                 "uploaded_videos": item["uploaded_count"], "avg_views_per_video": item["avg_views"],
                 "view_share_percentage": item["share_pct"]}
                for i, item in enumerate(sorted_analytics)
            ], f, indent=4)
    except Exception as e:
        log(f"⚠️ Leaderboard error: {e}")
    source_links_map, source_videos_count, _ = load_source_data()
    def get_latest_post_time(g_name):
        videos = actual_posted_titles.get(g_name, [])
        latest_time = ""
        for v in videos:
            if v.get("fb_posted") or v.get("ig_posted"):
                ts = v.get("timestamp", "")
                if ts > latest_time: latest_time = ts
        return latest_time
    games_dir = "logs/games"
    os.makedirs(games_dir, exist_ok=True)
    game_file_links = {}
    for g_name in sorted(actual_posted_titles.keys()):
        videos = actual_posted_titles.get(g_name, [])
        if not videos: continue

        posted_v = [x for x in videos if x.get("fb_posted") or x.get("ig_posted")]
        pending_v = [x for x in videos if not (x.get("fb_posted") or x.get("ig_posted"))]
        posted_v_sorted = sorted(posted_v, key=lambda x: x.get("timestamp", "") or "0000", reverse=True)

        def pending_key(x):
            vname = x.get("video_name") or x.get("vid_id") or ""
            digits = re.findall(r'\d+', vname)
            if digits:
                try:
                    return (0, -int(digits[-1]))
                except ValueError:
                    pass
            return (1, vname)
        pending_v_sorted = sorted(pending_v, key=pending_key)
        videos = posted_v_sorted + pending_v_sorted

        src_file_for_game = file_mapping.get(g_name, "")
        if not src_file_for_game:
            for f in os.listdir("game_links_editor"):
                if f.startswith(g_name) and f.endswith(".txt"):
                    src_file_for_game = os.path.join("game_links_editor", f)
                    break
        file_links = []
        if src_file_for_game and os.path.exists(src_file_for_game):
            try:
                with open(src_file_for_game, 'r', encoding='utf-8', errors='ignore') as f:
                    fc = f.read()
                file_links = re.findall(r'\|\s*Link:\s*(https?://[^\s\n\r\)\]\'"<>,;]+)', fc)
                file_links = [u.rstrip('.,;)\']"') for u in file_links]
            except Exception:
                pass
        posted_file_inner = os.path.join("posted_links_editor", f"{g_name}_posted_links_editor.txt")
        posted_links_inner = []
        if os.path.exists(posted_file_inner):
            try:
                with open(posted_file_inner, 'r', encoding='utf-8', errors='ignore') as pf:
                    pcontent = pf.read()
                posted_links_inner = re.findall(r'\|\s*Link:\s*(https?://[^\s\n\r\)\]\'"<>,;]+)', pcontent)
                posted_links_inner = [u.rstrip('.,;)\']"') for u in posted_links_inner]
            except Exception:
                pass

        safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', g_name)
        game_filename = f"{safe_name}.md"
        game_filepath = os.path.join(games_dir, game_filename)
        game_file_links[g_name] = f"logs/games/{game_filename}"
        gf_lines = []
        gf_lines.append(f"# 🎮 {g_name} — Full Video History\n\n")
        gf_lines.append(f"[⬅️ Back to Dashboard](../../GAMING_DASHBOARD.md)\n\n")
        gf_lines.append(f"**Total Videos:** {len(videos)} | **Last Updated:** {now_ist_ampm()} IST\n\n")
        gf_lines.append("---\n\n")
        total_fb_views = sum(v.get('fb_views', 0) for v in videos)
        total_ig_views = sum(v.get('ig_views', 0) for v in videos)
        fb_count = sum(1 for v in videos if v.get('fb_posted'))
        ig_count = sum(1 for v in videos if v.get('ig_posted'))
        total_posted = sum(1 for v in videos if v.get('fb_posted') or v.get('ig_posted'))
        gf_lines.append("## 📊 Summary\n\n| Metric | Value |\n|---|---|\n")
        gf_lines.append(f"| Total Videos | **{len(videos)}** |\n")
        gf_lines.append(f"| Posted (FB or IG) | {total_posted} / {len(videos)} |\n")
        gf_lines.append(f"| FB Posted | {fb_count} / {len(videos)} |\n")
        gf_lines.append(f"| IG Posted | {ig_count} / {len(videos)} |\n")
        gf_lines.append(f"| Total FB Views | **{total_fb_views:,}** |\n")
        gf_lines.append(f"| Total IG Views | **{total_ig_views:,}** |\n\n")
        gf_lines.append("---\n\n## 📜 All Videos (Newest First)\n\n")
        gf_lines.append("| # | 📺 Title | 🔵 Facebook | 👁️ FB Views | 🟣 Instagram | 👁️ IG Views | 📂 Source |\n")
        gf_lines.append("|---|---|---|---|---|---|---|\n")
        for idx, v in enumerate(videos, 1):
            title = (v.get("title") or "").replace("\n", " ").replace("|", "\\|")[:120] or "_Untitled_"
            fb_md = f"[🔵 FB]({v['fb_link']})" if v.get("fb_posted") and v.get("fb_link") else "⏳ Pending"
            fb_v_md = f"{v.get('fb_views', 0):,}" if v.get("fb_posted") else "_0_"
            ig_md = f"[🟣 IG]({v['ig_link']})" if v.get("ig_posted") and v.get("ig_link") else "⏳ Pending"
            ig_v_md = f"{v.get('ig_views', 0):,}" if v.get("ig_posted") else "_0_"

            src_link = v.get("source_link", "")
            if not src_link:
                v_name = (v.get("video_name") or v.get("vid_id") or "").lower().strip()
                v_digits = re.findall(r'\d+', v_name)
                v_num = v_digits[-1] if v_digits else ""
                game_clean = re.sub(r'[^a-z0-9]', '', g_name.lower())

                if v_num and file_links:
                    for fl in file_links:
                        fl_clean = re.sub(r'[^a-z0-9]', '', fl.lower())
                        if game_clean in fl_clean and v_num in fl:
                            src_link = fl
                            break
                if not src_link and v_num and posted_links_inner:
                    for pl in posted_links_inner:
                        pl_clean = re.sub(r'[^a-z0-9]', '', pl.lower())
                        if game_clean in pl_clean and v_num in pl:
                            src_link = pl
                            break
                if not src_link and file_links and idx - 1 < len(file_links):
                    src_link = file_links[idx - 1]
                if not src_link and posted_links_inner and idx - 1 < len(posted_links_inner):
                    src_link = posted_links_inner[idx - 1]
                if not src_link:
                    src_urls = source_links_map.get(g_name, [])
                    if idx - 1 < len(src_urls):
                        src_link = src_urls[idx - 1]
                    elif src_urls:
                        src_link = src_urls[-1]

            src_md = f"[📂]({src_link})" if src_link else "_N/A_"
            gf_lines.append(f"| {idx} | {title} | {fb_md} | {fb_v_md} | {ig_md} | {ig_v_md} | {src_md} |\n")
        try:
            with open(game_filepath, 'w', encoding='utf-8') as f:
                f.writelines(gf_lines)
        except Exception as e:
            log(f"⚠️ Failed to write {game_filepath}: {e}")
    md_content = []
    md_content.append("# 🚀 GAMING AGENT COMMAND & ANALYTICS DASHBOARD\n\n")
    md_content.append(f"> **Last Updated:** {now_ist_ampm()} IST | **Status:** All Systems Active & Synchronized\n\n")
    md_content.append("--- \n\n## 🏆 Global Leaderboard & Performance Summary\n\n")
    md_content.append("| Rank | Game Name | Total Videos | Total Views | Avg Views / Video | Performance Tier |\n")
    md_content.append("| :---: | :--- | :---: | :---: | :---: | :---: |\n")
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    for idx, item in enumerate(sorted_analytics):
        rank_icon = medals[idx] if idx < len(medals) else f"{idx + 1}"
        tier = ("🔥 Viral / Hype" if item['avg_views'] > 7000
                else "⚡ Trending" if item['avg_views'] > 4000
                else "📈 Stable")
        md_content.append(f"| {rank_icon} | **{item['game']}** | {item['uploaded_count']} | "
                          f"{item['total_views']:,} | {item['avg_views']:,} | {tier} |\n")
    md_content.append("\n--- \n\n## 📺 Live Post Titles + Views (Latest per Game)\n\n")
    md_content.append("> 🔵 FB = Facebook post live | 🟣 IG = Instagram post live | ⏳ = Pending\n\n")
    md_content.append("| Game Name | 📅 Last Posted | 📺 Latest Title | 🔵 Facebook | 👁️ FB Views | 🟣 Instagram | 👁️ IG Views | 📊 Remaining / Total | 📂 Source | 📜 All |\n")
    md_content.append("|---|---|---|---|---|---|---|---|---|---|\n")
    sorted_games = sorted(actual_posted_titles.keys(), key=lambda g: get_latest_post_time(g) or "0000", reverse=True)
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
            if remaining_vids == 0: progress_md = f"✅ {total_vids} / {total_vids}"
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
            md_content.append(f"| **{g_name}** | {date_str} | _Not Posted Yet_ | ⏳ Pending | _0_ | ⏳ Pending | _0_ | {progress_md} | _N/A_ | — |\n")
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
        src_link = latest.get("source_link", "") if latest else ""
        if not src_link and videos: src_link = videos[0].get("source_link", "")
        if not src_link:
            src_urls = source_links_map.get(g_name, [])
            src_link = src_urls[0] if src_urls else ""
        src_md = f"[📂]({src_link})" if src_link else "_N/A_"
        all_md = f"**[📜 View {len(videos)}]({game_file_links[g_name]})**" if g_name in game_file_links else f"_{len(videos)}_"
        md_content.append(f"| **{g_name}** | {date_str} | {title} | {fb_md} | {fb_v_md} | {ig_md} | {ig_v_md} | {progress_md} | {src_md} | {all_md} |\n")
    for section_func in [generate_trending_section, generate_best_time_section, generate_auto_reply_section]:
        section = section_func()
        if section: md_content.append(section)
    md_content.append("\n--- \n\n## 📜 Full Video History\n\n")
    md_content.append("> Click any game below to view its complete video list with all FB/IG links:\n\n")
    for g_name in sorted_games:
        videos = actual_posted_titles.get(g_name, [])
        if not videos: continue
        file_link = game_file_links.get(g_name, "")
        if file_link:
            md_content.append(f"- **🎮 {g_name}** — [📜 View All {len(videos)} Videos]({file_link})\n")
    rotation_file = "logs/rotation_history.json"
    if os.path.exists(rotation_file):
        try:
            with open(rotation_file, 'r', encoding='utf-8') as f:
                rot = json.load(f)
            md_content.append("\n--- \n\n## 🔄 Game Rotation Queue\n\n")
            md_content.append(f"**📊 Total Games:** {rot.get('total_games', 0)} | **🎯 Current:** `{rot.get('current_game', 'N/A')}` | "
                              f"**⏭️ Next Game:** `{rot.get('next_game', 'N/A')}` (Position #{rot.get('next_game_position', 0)}) | "
                              f"**🔢 Total Runs:** {rot.get('total_runs', 0)}\n\n")
            md_content.append(f"**Last Updated:** {rot.get('last_updated', 'N/A')} IST\n\n")
            md_content.append("| # | Game Name | Uploaded | Last Run # | Next Turn In | Status |\n")
            md_content.append("|:---:|---|:---:|:---:|:---:|:---:|\n")
            for ginfo in rot.get("all_games", []):
                pos = ginfo.get("position", 0)
                gname = ginfo.get("game", "")
                uploaded = ginfo.get("uploaded", 0)
                last_run = ginfo.get("last_run", 0) or "—"
                next_in = ginfo.get("next_turn_in", 0)
                status = ginfo.get("status", "waiting")
                if status == "current": status_md = "🎯 **CURRENT**"
                elif status == "next_up": status_md = "⏭️ **NEXT UP**"
                else: status_md = f"⏳ Wait {next_in}"
                md_content.append(f"| {pos} | **{gname}** | {uploaded} | {last_run} | {next_in} | {status_md} |\n")
            recent_logs = rot.get("rotation_log", [])[-5:]
            if recent_logs:
                md_content.append("\n### 📜 Recent Runs (Last 5)\n\n| Run # | Game | Timestamp (IST) |\n|:---:|---|---|\n")
                for log_entry in reversed(recent_logs):
                    md_content.append(f"| {log_entry['run']} | {log_entry['game']} | {log_entry['timestamp']} |\n")
        except Exception as e:
            log(f"⚠️ Rotation section error: {e}")
    with open(dashboard_path, 'w', encoding='utf-8') as f:
        f.writelines(md_content)
    git_commit_and_push([
        dashboard_path, leaderboard_json, history_json,
        "logs/agent_memory.json", "logs/rotation_history.json",
        "logs/games/", "logs/auto_reply_log.json",
        "logs/replied_comment_ids.json", "logs/trending_cache.json",
        "logs/best_time_analysis.json", "logs/auto_reply_live.log"
    ])


def get_game_video_stats(target_file, memory, game_name):
    total_links = 0
    if target_file and os.path.exists(target_file):
        try:
            with open(target_file, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            pipe_count = len(re.findall(r'\|\s*Link:', content))
            url_count = len(extract_urls(content))
            vid_count = content.count("Video id :")
            total_links = max(pipe_count, url_count, vid_count)
            log(f"📊 {game_name}: total={total_links} (pipe={pipe_count}, urls={url_count}, vid_ids={vid_count})")
        except Exception as e:
            log(f"⚠️ Stats error: {e}")
    game_stats = memory.get("game_stats", {})
    if game_name not in game_stats:
        game_stats[game_name] = {"uploaded_count": 0}
    uploaded_links = game_stats[game_name]["uploaded_count"]
    remaining_links = max(0, total_links - uploaded_links)
    return total_links, uploaded_links, remaining_links, game_stats


def run_agent_brain():
    links_dir = "game_links_editor"
    memory_file = "logs/agent_memory.json"
    os.makedirs("logs", exist_ok=True)
    os.makedirs(links_dir, exist_ok=True)

    if not AUTO_COMMENT_ENABLED:
        log("🚫 AUTO_COMMENT=false — Auto-reply will be SKIPPED (analytics only)")

    memory = {
        "game_scores": {},
        "title_styles": {
            "curiosity": 10, "aggressive": 10, "question": 10, "emoji_heavy": 10,
            "gaming_hype": 10, "clickbait": 10, "informative": 10, "epic_cinematic": 10,
            "funny_roast": 10, "secret_hidden": 10, "exposed": 10, "unbelievable": 10,
            "crazy": 10, "secret": 10, "shocking": 10
        },
        "last_used_style": "curiosity", "last_played_game": "",
        "processed_viral_ids": [], "game_stats": {}, "actual_posted_titles": {}
    }
    if os.path.exists(memory_file):
        try:
            with open(memory_file, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    memory.update(loaded)
        except Exception:
            pass
    for g_name, videos in memory.get("actual_posted_titles", {}).items():
        if not isinstance(videos, list): continue
        for v in videos:
            if not isinstance(v, dict): continue
            fb = v.get("fb_link", "")
            if fb and not str(fb).startswith("http"):
                v["fb_link"] = fix_fb_url(fb, v.get("vid_id", ""))
            ig = v.get("ig_link", "")
            if ig and not str(ig).startswith("http"):
                v["ig_link"] = fix_ig_url(ig)
    all_files = glob.glob(os.path.join(links_dir, "*.txt"))
    if not all_files:
        all_files = glob.glob("game_links_editor/*.txt")
    all_files = [f for f in all_files if ("_uploaded_links" in f or "_links_editor" in f or "_posted_links" in f)]
    if not all_files:
        log("❌ No valid game files found.")
        sys.exit(1)
    valid_game_files = [f for f in all_files if os.path.exists(f)]
    game_list = []
    file_mapping = {}
    for f in valid_game_files:
        g_name = (os.path.basename(f)
                  .replace("_uploaded_links.txt", "")
                  .replace("_links_editor.txt", "")
                  .replace("_posted_links_editor.txt", "")
                  .replace(".txt", "").strip())
        if not g_name: continue
        file_mapping[g_name] = f
        game_list.append(g_name)
    game_list = sorted(list(set(game_list)))
    log(f"📁 Found {len(game_list)} games: {game_list}")
    actual_posted_titles, game_views_summary = fetch_fb_ig_data(game_list)
    if not game_views_summary:
        game_views_summary = {g: 0 for g in game_list}

    if AUTO_COMMENT_ENABLED:
        try:
            process_fb_comments(actual_posted_titles)
        except Exception as e:
            log(f"⚠️ Auto-reply error: {e}")
    else:
        log("🚫 Auto-comment disabled — skipping")

    try:
        detect_trending_games(actual_posted_titles, game_views_summary, days=7)
    except Exception as e:
        log(f"⚠️ Trending error: {e}")
    try:
        analyze_best_time({})
    except Exception as e:
        log(f"⚠️ Best time error: {e}")

    last_game = memory.get("last_played_game", "")
    if last_game in game_list:
        next_index = (game_list.index(last_game) + 1) % len(game_list)
        chosen_game = game_list[next_index]
    else:
        chosen_game = game_list[0] if game_list else "DefaultGame"
    target_file = file_mapping.get(chosen_game, "")
    original_chosen = chosen_game
    attempts = 0
    max_attempts = len(game_list)
    while attempts < max_attempts:
        if target_file and os.path.exists(target_file):
            try:
                with open(target_file, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                pipe_links = re.findall(r'\|\s*Link:\s*(https?://[^\s\n\r]+)', content)
                urls = extract_urls(content)
                if pipe_links or urls:
                    log(f"✅ {chosen_game}: {len(pipe_links)} pipe links, {len(urls)} urls — proceeding")
                    break
                else:
                    log(f"⚠️ {chosen_game}: File has no URLs — trying next game")
            except Exception as e:
                log(f"⚠️ {chosen_game}: Read error — {e}")
        else:
            log(f"⚠️ {chosen_game}: File not found — trying next game")
        current_idx = game_list.index(chosen_game)
        next_idx = (current_idx + 1) % len(game_list)
        chosen_game = game_list[next_idx]
        target_file = file_mapping.get(chosen_game, "")
        attempts += 1
    if attempts >= max_attempts:
        log(f"❌ All game files empty. Cannot proceed.")
        sys.exit(1)
    if chosen_game != original_chosen:
        log(f"🔄 Switched from {original_chosen} to {chosen_game}")
    styles = memory.get("title_styles", {})
    chosen_style = random.choices(list(styles.keys()), weights=list(styles.values()), k=1)[0]
    game_hashtag = f"#{chosen_game.replace(' ', '')}"
    generated_ai_title = f"🎮 {chosen_game} Gameplay | {game_hashtag}"
    total_links, uploaded_links, remaining_links, game_stats = get_game_video_stats(
        target_file, memory, chosen_game
    )
    specific_uploaded_link = "N/A"
    try:
        with open(target_file, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        pipe_links = re.findall(r'\|\s*Link:\s*(https?://[^\s\n\r\)\]\'"<>,;]+)', content)
        pipe_links = [u.rstrip('.,;)\']"') for u in pipe_links]
        direct_urls = extract_urls(content)
        all_urls = pipe_links if pipe_links else direct_urls
        log(f"🔍 {chosen_game}: {len(pipe_links)} pipe + {len(direct_urls)} direct URLs")
        if all_urls:
            link_index = uploaded_links % len(all_urls)
            specific_uploaded_link = all_urls[link_index]
            log(f"✅ Source link: {specific_uploaded_link}")
    except Exception as e:
        log(f"⚠️ Link extraction error: {e}")
    game_stats[chosen_game]["uploaded_count"] = uploaded_links + 1
    memory["game_stats"] = game_stats
    memory["last_used_style"] = chosen_style
    memory["last_played_game"] = chosen_game
    memory["actual_posted_titles"] = actual_posted_titles
    try:
        with open(memory_file, 'w', encoding='utf-8') as f:
            json.dump(memory, f, indent=4)
    except Exception:
        pass
    rotation_info = save_rotation_history(game_list, chosen_game, memory)
    log(f"🔄 Rotation saved. Next: {rotation_info['next_game']}")
    latest_fb_link = ""
    latest_ig_link = ""
    latest_views = 0
    if actual_posted_titles.get(chosen_game):
        for v in actual_posted_titles[chosen_game]:
            if v.get("fb_posted") or v.get("ig_posted"):
                latest_fb_link = v.get("fb_link", "")
                latest_ig_link = v.get("ig_link", "")
                latest_views = v.get("fb_views", 0) + v.get("ig_views", 0)
                break
    update_unified_dashboard(
        game_name=chosen_game, chosen_style=chosen_style, ai_title=generated_ai_title,
        specific_uploaded_link=specific_uploaded_link,
        post_link=latest_fb_link or latest_ig_link or "N/A",
        platform_name="Facebook" if latest_fb_link else ("Instagram" if latest_ig_link else "Local / Pending"),
        views_count=latest_views, game_views_summary=game_views_summary,
        game_stats=memory.get("game_stats", {}), actual_posted_titles=actual_posted_titles,
        file_mapping=file_mapping,
    )
    log(f"""
🚀 GAMING AGENT DASHBOARD
> Last Updated: {now_ist_ampm()} IST
> Auto-Comment: {"✅ ENABLED" if AUTO_COMMENT_ENABLED else "🚫 DISABLED"}

📊 Status:
• Game: {chosen_game}
• Platform: {"Facebook" if latest_fb_link else ("Instagram" if latest_ig_link else "Pending")}
• Source Link: {specific_uploaded_link}
• Views: {latest_views:,}

📈 Progress:
• Total Videos: {total_links}
• Uploaded: {uploaded_links + 1}
• Remaining: {remaining_links}
""")
    latest_title = ""
    if actual_posted_titles.get(chosen_game):
        for v in actual_posted_titles[chosen_game]:
            if v.get("fb_posted") or v.get("ig_posted"):
                latest_title = v.get("title", "")
                break
    print(json.dumps({
        "target_file": target_file,
        "game_name": chosen_game,
        "chosen_style": chosen_style,
        "ai_title": generated_ai_title,
        "actual_posted_title": latest_title,
        "source_url": specific_uploaded_link,
        "total_links": total_links,
        "uploaded_count": uploaded_links + 1,
        "remaining_links": remaining_links,
        "next_game": rotation_info.get("next_game", ""),
        "auto_comment": AUTO_COMMENT_ENABLED,
    }))


if __name__ == "__main__":
    run_agent_brain()