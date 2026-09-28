"""
📊 GAME ANALYTICS MODULE
------------------------
FB/IG data fetch, dashboard generation, trending, best-time analysis, charts.

Usage:
    from game_analytics import AnalyticsEngine
    engine = AnalyticsEngine(game_list, fb_page_id, fb_token)
    posted_titles, views_summary = engine.fetch_fb_ig_data()
    engine.update_unified_dashboard(...)
"""

import os
import glob
import json
import re
import sys
import subprocess
import requests
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from zoneinfo import ZoneInfo
    IST = ZoneInfo("Asia/Kolkata")
except Exception:
    IST = timezone(timedelta(hours=5, minutes=30))

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


# ---------- HELPERS ----------
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
    lines = content.split('\n')
    posts, current_video = [], {}
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
# 📈 ANALYTICS ENGINE
# ============================================================
class AnalyticsEngine:
    """
    Handles FB/IG fetching, dashboard generation, trending,
    best-time analysis, charts, git commit.
    """

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

    def __init__(self, game_list, fb_page_id=None, fb_access_token=None,
                 openrouter_keys=None, auto_comment_enabled=True,
                 days_limit=28):
        self.game_list = game_list
        self.fb_page_id = fb_page_id or os.environ.get("PAGE_ID")
        self.fb_access_token = fb_access_token or os.environ.get("PAGE_ACCESS_TOKEN")
        self.auto_comment_enabled = auto_comment_enabled
        self.days_limit = days_limit

        self.fb_api_version = "v24.0"
        self.fb_graph_url = f"https://graph.facebook.com/{self.fb_api_version}"

    # ---------- GIT ----------
    @staticmethod
    def git_commit_and_push(file_paths, message="Auto-Agent: Sync dashboard [skip ci]"):
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
            p = subprocess.run(["git", "push"], capture_output=True, text=True, check=False)
            log(f"🔄 Git Push: {p.stdout.strip()} {p.stderr.strip()}")
        except Exception as e:
            log(f"⚠️ Git auto-push error: {e}")

    # ---------- FB / IG FETCH ----------
    def fetch_fb_caption(self, vid_id):
        url = f"{self.fb_graph_url}/{vid_id}?fields=description&access_token={self.fb_access_token}"
        try:
            res = requests.get(url, timeout=5).json()
            caption = res.get('description', '').strip()
            if caption:
                return caption.split('\n')[0].strip()
        except Exception:
            pass
        return None

    def fetch_fb_views_by_id(self, vid_id):
        url = f"{self.fb_graph_url}/{vid_id}/video_insights?access_token={self.fb_access_token}"
        try:
            res = requests.get(url, timeout=5).json()
            for metric in res.get('data', []):
                if metric.get('name') == 'total_video_views':
                    return metric.get('values', [{}])[0].get('value', 0)
        except Exception:
            pass
        return 0

    def fetch_fb_ig_data(self):
        """Return (actual_posted_titles, game_views_summary)."""
        posted_dir = 'posted_links_editor'
        result = {g: [] for g in self.game_list}
        game_views_summary = {g: 0 for g in self.game_list}

        if not self.fb_access_token:
            log("⚠️ FB_ACCESS_TOKEN missing")
            return result, game_views_summary

        # Build vid_id -> source_link map
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

        # Parse local posted files
        if os.path.exists(posted_dir):
            cutoff_date = now_ist() - timedelta(days=self.days_limit)
            all_tasks = []
            for filename in os.listdir(posted_dir):
                if not filename.endswith('_posted_links_editor.txt'):
                    continue
                game_name = filename.replace('_posted_links_editor.txt', '')
                if game_name not in self.game_list:
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
                    fb_caption = self.fetch_fb_caption(vid_id)
                    fb_views = self.fetch_fb_views_by_id(vid_id)
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
                    post['status'] = "✅ Live" if fb_views > 0 else "⏳ Pending"
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

        # FB page videos
        since_ts = int((now_ist() - timedelta(days=self.days_limit)).timestamp())
        fb_videos, ig_medias = [], []
        try:
            res = requests.get(
                f"{self.fb_graph_url}/{self.fb_page_id}/videos",
                params={"fields": "id,title,description,views,permalink_url,created_time",
                        "since": since_ts, "access_token": self.fb_access_token, "limit": 100},
                timeout=20)
            if res.status_code == 200:
                fb_videos = res.json().get("data", [])
                log(f"✅ FB page: {len(fb_videos)} videos fetched")
        except Exception as e:
            log(f"❌ FB page fetch error: {e}")

        try:
            res_ig_acc = requests.get(
                f"{self.fb_graph_url}/{self.fb_page_id}",
                params={"fields": "instagram_business_account",
                        "access_token": self.fb_access_token},
                timeout=10)
            if res_ig_acc.status_code == 200:
                ig_id = res_ig_acc.json().get("instagram_business_account", {}).get("id")
                if ig_id:
                    res_ig = requests.get(
                        f"{self.fb_graph_url}/{ig_id}/media",
                        params={"fields": "id,caption,permalink,timestamp,like_count,comments_count",
                                "access_token": self.fb_access_token, "limit": 100},
                        timeout=20)
                    if res_ig.status_code == 200:
                        ig_medias = res_ig.json().get("data", [])
                        log(f"✅ IG: {len(ig_medias)} media fetched")
        except Exception as e:
            log(f"❌ IG fetch error: {e}")

        for game in self.game_list:
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

        # Merge source file videos
        games_links_dir = "game_links_editor"
        if os.path.exists(games_links_dir):
            for game in self.game_list:
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

        # Sort: posted first (newest), pending last (numeric ascending)
        for game in self.game_list:
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

    # ---------- TRENDING ----------
    def detect_trending_games(self, actual_posted_titles, game_views_summary, days=7):
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

    # ---------- BEST TIME ----------
    def analyze_best_time(self, all_history=None):
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

    # ---------- DASHBOARD SECTIONS ----------
    def _generate_trending_section(self):
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

    def _generate_best_time_section(self):
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

    def _generate_auto_reply_section(self):
        try:
            with open("logs/auto_reply_log.json", 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            return ""
        out = ["\n--- \n\n## 🤖 Auto-Reply Log (Direct FB Mode)\n\n"]
        status = "🚫 **DISABLED**" if not self.auto_comment_enabled else "✅ **ACTIVE**"
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
            out.append("| # | Time | 👤 User | 💬 User Comment | 🤖 AI Reply | Type | Game | FB Post |\n")
            out.append("|---|---|---|---|---|---|---|---|\n")
            for idx, r in enumerate(list(reversed(replies[-20:])), 1):
                un = (r.get("user_name", "Unknown") or "Unknown").replace("|", "\\|")[:20]
                cm = (r.get("user_comment", "") or "").replace("\n", " ").replace("|", "\\|")[:60]
                rp = (r.get("openrouter_reply", "") or "").replace("\n", " ").replace("|", "\\|")[:80]
                ts = r.get("timestamp", "")[:20]
                rtype = "😎 Savage" if r.get("type") == "savage" else "✅ Friendly"
                game = (r.get("game", "") or "").replace("|", "\\|")[:15]
                fb_md = f"[🔵]({r['fb_post_link']})" if r.get("fb_post_link") else "_N/A_"
                out.append(f"| {idx} | {ts} | **{un}** | {cm} | {rp} | {rtype} | {game} | {fb_md} |\n")
            savages = [r for r in replies if r.get("type") == "savage"][-5:]
            if savages:
                out.append("\n### 😎 Savage Replies (Last 5)\n\n| 👤 User | 💬 Abuse | 🤖 AI Reply | Game | FB Link |\n|---|---|---|---|---|\n")
                for s in reversed(savages):
                    un = (s.get("user_name", "Unknown") or "Unknown").replace("|", "\\|")[:20]
                    cm = (s.get("user_comment", "") or "").replace("\n", " ").replace("|", "\\|")[:80]
                    rp = (s.get("openrouter_reply", "") or "").replace("\n", " ").replace("|", "\\|")[:100]
                    game = (s.get("game", "") or "").replace("|", "\\|")[:15]
                    fb_md = f"[🔵]({s['fb_post_link']})" if s.get("fb_post_link") else "_N/A_"
                    out.append(f"| **{un}** | {cm} | {rp} | {game} | {fb_md} |\n")
        skipped = data.get("skipped", [])[-5:]
        if skipped:
            out.append("\n### ⏭️ Skipped Comments (Last 5)\n\n| Comment | Reason |\n|---|---|\n")
            for s in reversed(skipped):
                cm = (s.get("comment_text", "") or "").replace("\n", " ").replace("|", "\\|")[:80]
                reason = s.get("reason", "").replace("_", " ")
                out.append(f"| {cm} | {reason} |\n")
        return "".join(out)

    # ---------- CHARTS ----------
    def _generate_visual_reports(self, game_views_summary, game_stats):
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

    # ---------- DASHBOARD ----------
    def update_unified_dashboard(self, game_name, chosen_style, ai_title,
                                 specific_uploaded_link, post_link, platform_name,
                                 views_count, game_views_summary, game_stats,
                                 actual_posted_titles=None, file_mapping=None):
        if actual_posted_titles is None:
            actual_posted_titles = {}
        if file_mapping is None:
            file_mapping = {}

        dashboard_path = "GAMING_DASHBOARD.md"
        leaderboard_json = os.path.join("logs/leaderboard", "games_performance_leaderboard.json")
        os.makedirs("logs/leaderboard", exist_ok=True)
        timestamp = now_ist_ampm()

        # History append
        history_json = "logs/dashboard_history.json"
        all_history = {}
        if os.path.exists(history_json):
            try:
                with open(history_json, 'r', encoding='utf-8') as f:
                    all_history = json.load(f)
            except Exception:
                pass
        all_history.setdefault(game_name, [])
        new_entry = {
            "timestamp": timestamp, "style": chosen_style, "ai_title": ai_title,
            "actual_posted_title": "", "views": views_count,
            "source_link": specific_uploaded_link, "post_link": post_link,
            "platform": platform_name,
        }
        for v in actual_posted_titles.get(game_name, []):
            if v.get("fb_posted") or v.get("ig_posted"):
                new_entry["actual_posted_title"] = v.get("title", "")
                break
        all_history[game_name].append(new_entry)
        try:
            with open(history_json, 'w', encoding='utf-8') as f:
                json.dump(all_history, f, indent=4)
        except Exception:
            pass

        sorted_analytics = self._generate_visual_reports(game_views_summary, game_stats)

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

        # Per-game files
        games_dir = "logs/games"
        os.makedirs(games_dir, exist_ok=True)
        game_file_links = {}

        for g_name in sorted(actual_posted_titles.keys()):
            videos = actual_posted_titles.get(g_name, [])
            if not videos:
                continue

            src_file_for_game = file_mapping.get(g_name, "")
            if not src_file_for_game and os.path.exists("game_links_editor"):
                for f in os.listdir("game_links_editor"):
                    if f.startswith(g_name) and f.endswith(".txt"):
                        src_file_for_game = os.path.join("game_links_editor", f)
                        break

            file_links = []
            if src_file_for_game and os.path.exists(src_file_for_game):
                try:
                    with open(src_file_for_game, 'r', encoding='utf-8', errors='ignore') as f:
                        fc = f.read()
                    file_links = [u.rstrip('.,;)\']"') for u in
                                  re.findall(r'\|\s*Link:\s*(https?://[^\s\n\r\)\]\'"<>,;]+)', fc)]
                except Exception:
                    pass

            posted_file_inner = os.path.join("posted_links_editor", f"{g_name}_posted_links_editor.txt")
            posted_links_inner = []
            if os.path.exists(posted_file_inner):
                try:
                    with open(posted_file_inner, 'r', encoding='utf-8', errors='ignore') as pf:
                        pcontent = pf.read()
                    posted_links_inner = [u.rstrip('.,;)\']"') for u in
                                          re.findall(r'\|\s*Link:\s*(https?://[^\s\n\r\)\]\'"<>,;]+)', pcontent)]
                except Exception:
                    pass

            safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', g_name)
            game_filename = f"{safe_name}.md"
            game_filepath = os.path.join(games_dir, game_filename)
            game_file_links[g_name] = f"logs/games/{game_filename}"

            gf_lines = [f"# 🎮 {g_name} — Full Video History\n\n",
                        f"[⬅️ Back to Dashboard](../../GAMING_DASHBOARD.md)\n\n",
                        f"**Total Videos:** {len(videos)} | **Last Updated:** {now_ist_ampm()} IST\n\n",
                        "---\n\n"]

            total_fb_views = sum(v.get('fb_views', 0) for v in videos)
            total_ig_views = sum(v.get('ig_views', 0) for v in videos)
            fb_count = sum(1 for v in videos if v.get('fb_posted'))
            ig_count = sum(1 for v in videos if v.get('ig_posted'))
            total_posted = sum(1 for v in videos if v.get('fb_posted') or v.get('ig_posted'))

            gf_lines.append("## 📊 Summary\n\n| Metric | Value |\n|---|---|\n")
            gf_lines.append(f"| Total Videos | **{len(videos)}** |\n")
            gf_lines.append(f"| Posted | {total_posted} / {len(videos)} |\n")
            gf_lines.append(f"| FB Posted | {fb_count} / {len(videos)} |\n")
            gf_lines.append(f"| IG Posted | {ig_count} / {len(videos)} |\n")
            gf_lines.append(f"| Total FB Views | **{total_fb_views:,}** |\n")
            gf_lines.append(f"| Total IG Views | **{total_ig_views:,}** |\n\n")
            gf_lines.append("---\n\n## 📜 All Videos (Newest First)\n\n")
            gf_lines.append("| # | 📺 Title | 🔵 FB | 👁️ FB Views | 🟣 IG | 👁️ IG Views | 📂 Source |\n")
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
                            if game_clean in re.sub(r'[^a-z0-9]', '', fl.lower()) and v_num in fl:
                                src_link = fl
                                break
                    if not src_link and v_num and posted_links_inner:
                        for pl in posted_links_inner:
                            if game_clean in re.sub(r'[^a-z0-9]', '', pl.lower()) and v_num in pl:
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
                gf_lines.append(f"| {idx} | {title} | {fb_md} | {fb_v_md} | "
                                f"{ig_md} | {ig_v_md} | {src_md} |\n")

            try:
                with open(game_filepath, 'w', encoding='utf-8') as f:
                    f.writelines(gf_lines)
            except Exception as e:
                log(f"⚠️ Failed to write {game_filepath}: {e}")

        # Main dashboard
        md = ["# 🚀 GAMING AGENT COMMAND & ANALYTICS DASHBOARD\n\n",
              f"> **Last Updated:** {now_ist_ampm()} IST | **Status:** All Systems Active\n\n",
              "--- \n\n## 🏆 Global Leaderboard & Performance Summary\n\n",
              "| Rank | Game Name | Total Videos | Total Views | Avg Views / Video | Performance Tier |\n",
              "| :---: | :--- | :---: | :---: | :---: | :---: |\n"]
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
        for idx, item in enumerate(sorted_analytics):
            rank_icon = medals[idx] if idx < len(medals) else f"{idx + 1}"
            tier = ("🔥 Viral / Hype" if item['avg_views'] > 7000
                    else "⚡ Trending" if item['avg_views'] > 4000
                    else "📈 Stable")
            md.append(f"| {rank_icon} | **{item['game']}** | {item['uploaded_count']} | "
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

        for g_name in sorted_games:
            videos = actual_posted_titles.get(g_name, [])
            src_file = file_mapping.get(g_name, "")
            total_vids = len(videos)
            if src_file and os.path.exists(src_file):
                try:
                    with open(src_file, 'r', encoding='utf-8', errors='ignore') as f:
                        c = f.read()
                    total_vids = max(len(re.findall(r'\|\s*Link:', c)), total_vids,
                                     len(extract_urls(c)))
                except Exception:
                    pass

            uploaded_vids = game_stats.get(g_name, {}).get("uploaded_count", 0)
            remaining_vids = max(0, total_vids - uploaded_vids)
            progress_md = (f"✅ {total_vids} / {total_vids}" if remaining_vids == 0 and total_vids > 0
                           else f"**{remaining_vids}** / {total_vids}" if total_vids > 0
                           else "_N/A_")

            latest_post_time = get_latest_post_time(g_name)
            date_str = "—"
            if latest_post_time:
                dt_ist = utc_to_ist(latest_post_time)
                date_str = dt_ist.strftime("%Y-%m-%d %I:%M %p") if dt_ist else str(latest_post_time)[:16]

            if not videos:
                md.append(f"| **{g_name}** | {date_str} | _Not Posted Yet_ | ⏳ Pending | "
                          f"_0_ | ⏳ Pending | _0_ | {progress_md} | _N/A_ | — |\n")
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
            fb_md = f"[🔵 FB]({latest['fb_link']})" if latest.get("fb_posted") and latest.get("fb_link") else "⏳ Pending"
            fb_v_md = f"{latest.get('fb_views', 0):,}" if latest.get("fb_posted") else "_0_"
            ig_md = f"[🟣 IG]({latest['ig_link']})" if latest.get("ig_posted") and latest.get("ig_link") else "⏳ Pending"
            ig_v_md = f"{latest.get('ig_views', 0):,}" if latest.get("ig_posted") else "_0_"

            src_link = latest.get("source_link", "") or (videos[0].get("source_link", "") if videos else "")
            if not src_link:
                src_urls = source_links_map.get(g_name, [])
                src_link = src_urls[0] if src_urls else ""
            src_md = f"[📂]({src_link})" if src_link else "_N/A_"
            all_md = (f"**[📜 View {len(videos)}]({game_file_links[g_name]})**"
                      if g_name in game_file_links else f"_{len(videos)}_")

            md.append(f"| **{g_name}** | {date_str} | {title} | {fb_md} | {fb_v_md} | "
                      f"{ig_md} | {ig_v_md} | {progress_md} | {src_md} | {all_md} |\n")

        for fn in (self._generate_trending_section, self._generate_best_time_section,
                   self._generate_auto_reply_section):
            section = fn()
            if section:
                md.append(section)

        md.append("\n--- \n\n## 📜 Full Video History\n\n")
        md.append("> Click any game below to view its complete video list:\n\n")
        for g_name in sorted_games:
            videos = actual_posted_titles.get(g_name, [])
            if not videos:
                continue
            file_link = game_file_links.get(g_name, "")
            if file_link:
                md.append(f"- **🎮 {g_name}** — [📜 View All {len(videos)} Videos]({file_link})\n")

        # Rotation section (read-only from rotation_history.json)
        rotation_file = "logs/rotation_history.json"
        if os.path.exists(rotation_file):
            try:
                with open(rotation_file, 'r', encoding='utf-8') as f:
                    rot = json.load(f)
                md.append("\n--- \n\n## 🔄 Game Rotation Queue\n\n")
                md.append(f"**📊 Total Games:** {rot.get('total_games', 0)} | "
                          f"**🎯 Current:** `{rot.get('current_game', 'N/A')}` | "
                          f"**⏭️ Next Game:** `{rot.get('next_game', 'N/A')}` "
                          f"(Position #{rot.get('next_game_position', 0)}) | "
                          f"**🔢 Total Runs:** {rot.get('total_runs', 0)}\n\n")
                md.append(f"**Last Updated:** {rot.get('last_updated', 'N/A')} IST\n\n")
                md.append("| # | Game Name | Uploaded | Last Run # | Next Turn In | Status |\n")
                md.append("|:---:|---|:---:|:---:|:---:|:---:|\n")
                for ginfo in rot.get("all_games", []):
                    status = ginfo.get("status", "waiting")
                    if status == "current":
                        status_md = "🎯 **CURRENT**"
                    elif status == "next_up":
                        status_md = "⏭️ **NEXT UP**"
                    else:
                        status_md = f"⏳ Wait {ginfo.get('next_turn_in', 0)}"
                    md.append(f"| {ginfo.get('position', 0)} | **{ginfo.get('game', '')}** | "
                              f"{ginfo.get('uploaded', 0)} | {ginfo.get('last_run', 0) or '—'} | "
                              f"{ginfo.get('next_turn_in', 0)} | {status_md} |\n")
                recent_logs = rot.get("rotation_log", [])[-5:]
                if recent_logs:
                    md.append("\n### 📜 Recent Runs (Last 5)\n\n| Run # | Game | Timestamp (IST) |\n|:---:|---|---|\n")
                    for entry in reversed(recent_logs):
                        md.append(f"| {entry['run']} | {entry['game']} | {entry['timestamp']} |\n")
            except Exception as e:
                log(f"⚠️ Rotation section error: {e}")

        with open(dashboard_path, 'w', encoding='utf-8') as f:
            f.writelines(md)

        self.git_commit_and_push([
            dashboard_path, leaderboard_json, history_json,
            "logs/agent_memory.json", "logs/rotation_history.json",
            "logs/games/", "logs/auto_reply_log.json",
            "logs/replied_comment_ids.json", "logs/trending_cache.json",
            "logs/best_time_analysis.json",
        ])