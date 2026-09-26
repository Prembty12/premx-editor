import os
import glob
import json
import random
import requests
import sys
import subprocess
import re
from datetime import datetime, timedelta

# 🇮🇳 Indian Standard Time
try:
    from zoneinfo import ZoneInfo
    IST = ZoneInfo("Asia/Kolkata")
except Exception:
    from datetime import timezone
    IST = timezone(timedelta(hours=5, minutes=30))

def now_ist():
    return datetime.now(IST)

def now_ist_str():
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")


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


FB_PAGE_ID = os.environ.get("PAGE_ID")
FB_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")

DAYS_LIMIT = 28


def log(msg):
    sys.stderr.write(f"{msg}\n")
    sys.stderr.flush()


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
    """game_links_editor/*.txt se saare videos parse karo."""
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
                    videos.append({
                        "video_name": video_name,
                        "source_link": link,
                    })

        if not videos:
            urls = extract_urls(content)
            for idx, u in enumerate(urls, 1):
                videos.append({
                    "video_name": f"Video_{idx}",
                    "source_link": u,
                })
    except Exception as e:
        log(f"⚠️ parse_game_links_file error: {e}")

    return videos


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

    if REPORTLAB_AVAILABLE:
        try:
            doc = SimpleDocTemplate(pdf_path, pagesize=letter)
            elements = []
            styles = getSampleStyleSheet()
            title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=18,
                                         textColor=colors.HexColor('#1A237E'), spaceAfter=15, alignment=1)
            heading_style = ParagraphStyle('HeadingStyle', parent=styles['Heading2'], fontSize=13,
                                           textColor=colors.HexColor('#3F51B5'), spaceBefore=10, spaceAfter=5)
            normal_style = styles['Normal']

            elements.append(Paragraph("🎮 Multi-Platform Gaming Agent - Analytics Report", title_style))
            elements.append(Paragraph(f"Generated on: {now_ist_str()} IST", normal_style))
            elements.append(Spacer(1, 15))

            elements.append(Paragraph("🏆 Performance & Efficiency Leaderboard", heading_style))
            table_data = [["Rank", "Game Name", "Total Views", "Videos", "Avg/Video", "View Share"]]
            for idx, item in enumerate(sorted_analytics, 1):
                table_data.append([str(idx), item["game"], f"{item['total_views']:,}",
                                   str(item['uploaded_count']), f"{item['avg_views']:,}",
                                   f"{item['share_pct']}%"])

            t = Table(table_data, colWidths=[40, 150, 90, 60, 90, 70])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3F51B5')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#F5F5F5')),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
            ]))
            elements.append(t)
            doc.build(elements)
        except Exception as e:
            log(f"⚠️ PDF error: {e}")

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

    rotation_data["last_updated"] = now_ist_str()
    rotation_data["total_runs"] = len(rotation_data.get("rotation_log", [])) + 1

    rotation_data.setdefault("rotation_log", []).append({
        "run": rotation_data["total_runs"],
        "game": chosen_game,
        "timestamp": now_ist_str(),
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
            vid_id = line.split('Video id :')[-1].strip()
            current_video['vid_id'] = vid_id
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

    # STEP 1: posted_links_editor se parse
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

                if fb_caption:
                    title = fb_caption
                elif post.get('title'):
                    title = post['title']
                else:
                    title = post.get('video_name', '').replace('_', ' ').strip()
                    if not title:
                        title = f"Video {vid_id[:8]}"

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
                            result[game].append({
                                "title": r.get('title', 'Untitled'),
                                "fb_link": fix_fb_url(r.get('fb_link', ''), r.get('vid_id', '')),
                                "fb_views": r.get('fb_views', 0),
                                "fb_posted": r.get('fb_posted', False),
                                "ig_link": "",
                                "ig_views": 0,
                                "ig_posted": False,
                                "timestamp": "",
                                "vid_id": r.get('vid_id', ''),
                                "source_link": r.get('link', ''),
                            })
                            game_views_summary[game] += r.get('fb_views', 0)
                    except Exception as e:
                        log(f"⚠️ Process error: {e}")

    # STEP 2: Page videos + IG media
    twenty_eight_days_ago = now_ist() - timedelta(days=DAYS_LIMIT)
    since_timestamp = int(twenty_eight_days_ago.timestamp())

    fb_videos = []
    ig_medias = []

    try:
        fb_url = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/videos"
        params = {
            "fields": "id,title,description,views,permalink_url,created_time",
            "since": since_timestamp,
            "access_token": FB_ACCESS_TOKEN,
            "limit": 100
        }
        res = requests.get(fb_url, params=params, timeout=20)
        if res.status_code == 200:
            fb_videos = res.json().get("data", [])
            log(f"✅ FB page: {len(fb_videos)} videos fetched")
    except Exception as e:
        log(f"❌ FB page fetch error: {e}")

    try:
        ig_url = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}"
        ig_params = {"fields": "instagram_business_account", "access_token": FB_ACCESS_TOKEN}
        res_ig_acc = requests.get(ig_url, params=ig_params, timeout=10)

        if res_ig_acc.status_code == 200:
            ig_id = res_ig_acc.json().get("instagram_business_account", {}).get("id")
            if ig_id:
                media_url = f"https://graph.facebook.com/v19.0/{ig_id}/media"
                media_params = {
                    "fields": "id,caption,permalink,timestamp,like_count,comments_count",
                    "access_token": FB_ACCESS_TOKEN,
                    "limit": 100
                }
                res_ig = requests.get(media_url, params=media_params, timeout=20)
                if res_ig.status_code == 200:
                    ig_medias = res_ig.json().get("data", [])
                    log(f"✅ IG: {len(ig_medias)} media fetched")
    except Exception as e:
        log(f"❌ IG fetch error: {e}")

    # Merge FB page videos
    for game in game_list:
        game_norm = normalize(game)
        existing_titles = set()
        for v in result[game]:
            existing_titles.add(normalize(v.get("title", ""))[:40])

        for v in fb_videos:
            title = (v.get("title") or v.get("description") or "").strip()
            if not title:
                continue
            if game_norm and game_norm in normalize(title):
                key = normalize(title)[:40]
                if key in existing_titles:
                    continue
                fb_link = fix_fb_url(v.get("permalink_url", ""), v.get("id", ""))
                entry = {
                    "title": title,
                    "fb_link": fb_link,
                    "fb_views": int(v.get("views", 0) or 0),
                    "fb_posted": True,
                    "ig_link": "",
                    "ig_views": 0,
                    "ig_posted": False,
                    "timestamp": v.get("created_time", ""),
                    "vid_id": v.get("id", ""),
                    "source_link": "",
                }
                result[game].append(entry)
                game_views_summary[game] += entry["fb_views"]
                existing_titles.add(key)

        for m in ig_medias:
            caption = (m.get("caption") or "").strip()
            if not caption:
                continue
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
                    result[game].append({
                        "title": caption[:100],
                        "fb_link": "",
                        "fb_views": 0,
                        "fb_posted": False,
                        "ig_link": fix_ig_url(m.get("permalink", "")),
                        "ig_views": ig_views,
                        "ig_posted": True,
                        "timestamp": m.get("timestamp", ""),
                        "vid_id": m.get("id", ""),
                        "source_link": "",
                    })
                    game_views_summary[game] += ig_views
                    existing_titles.add(caption_norm)

    # STEP 3: game_links_editor se SAARE videos add karo
    games_links_dir = "game_links_editor"
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
            log(f"⚠️ {game}: No source file found in {games_links_dir}")
            continue

        src_videos = parse_game_links_file(src_file)
        log(f"📂 {game}: {len(src_videos)} videos in source file")

        existing_vids_lower = {}
        for v in result[game]:
            vname = (v.get("vid_id") or "").lower()
            vtitle = (v.get("title") or "").lower()
            if vname:
                existing_vids_lower[vname] = v
            if vtitle:
                existing_vids_lower[vtitle[:30]] = v

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
                    matched = True
                    break

            if not matched:
                result[game].append({
                    "title": vname,
                    "fb_link": "",
                    "fb_views": 0,
                    "fb_posted": False,
                    "ig_link": "",
                    "ig_views": 0,
                    "ig_posted": False,
                    "timestamp": "",
                    "vid_id": vname,
                    "source_link": src_link,
                    "is_source_only": True,
                })

    # Sort: posted first (by timestamp), then source-only
    for game in game_list:
        def sort_key(x):
            ts = x.get("timestamp", "") or ""
            is_posted = x.get("fb_posted") or x.get("ig_posted")
            return (0 if is_posted else 1, ts, x.get("vid_id", ""))

        result[game] = sorted(result[game], key=sort_key, reverse=False)

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

    timestamp = now_ist_str()

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

    # 🔥 NEW: Latest post time per game
    def get_latest_post_time(g_name):
        videos = actual_posted_titles.get(g_name, [])
        latest_time = ""
        for v in videos:
            if v.get("fb_posted") or v.get("ig_posted"):
                ts = v.get("timestamp", "")
                if ts > latest_time:
                    latest_time = ts
        return latest_time

    # 🔥 NAYA: Har game ki alag file banao
    games_dir = "logs/games"
    os.makedirs(games_dir, exist_ok=True)
    game_file_links = {}

    for g_name in sorted(actual_posted_titles.keys()):
        videos = actual_posted_titles.get(g_name, [])
        if not videos:
            continue

        # Source file dhoondho
        src_file_for_game = file_mapping.get(g_name, "")
        if not src_file_for_game:
            for f in os.listdir("game_links_editor"):
                if f.startswith(g_name) and f.endswith(".txt"):
                    src_file_for_game = os.path.join("game_links_editor", f)
                    break

        # File se saare links pre-fetch karo
        file_links = []
        if src_file_for_game and os.path.exists(src_file_for_game):
            try:
                with open(src_file_for_game, 'r', encoding='utf-8', errors='ignore') as f:
                    fc = f.read()
                file_links = re.findall(r'\|\s*Link:\s*(https?://[^\s\n\r\)\]\'"<>,;]+)', fc)
                file_links = [u.rstrip('.,;)\']"') for u in file_links]
            except Exception:
                pass

        safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', g_name)
        game_filename = f"{safe_name}.md"
        game_filepath = os.path.join(games_dir, game_filename)
        game_file_links[g_name] = f"logs/games/{game_filename}"

        gf_lines = []
        gf_lines.append(f"# 🎮 {g_name} — Full Video History\n\n")
        gf_lines.append(f"[⬅️ Back to Dashboard](../../GAMING_DASHBOARD.md)\n\n")
        gf_lines.append(f"**Total Videos:** {len(videos)} | ")
        gf_lines.append(f"**Last Updated:** {now_ist_str()} IST\n\n")
        gf_lines.append("---\n\n")

        total_fb_views = sum(v.get('fb_views', 0) for v in videos)
        total_ig_views = sum(v.get('ig_views', 0) for v in videos)
        fb_count = sum(1 for v in videos if v.get('fb_posted'))
        ig_count = sum(1 for v in videos if v.get('ig_posted'))
        total_posted = sum(1 for v in videos if v.get('fb_posted') or v.get('ig_posted'))

        gf_lines.append("## 📊 Summary\n\n")
        gf_lines.append("| Metric | Value |\n|---|---|\n")
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

            # 🔥 FIX 2: Source link properly match karo
            src_link = v.get("source_link", "")
            if not src_link and file_links:
                if idx - 1 < len(file_links):
                    src_link = file_links[idx - 1]
                elif file_links:
                    src_link = file_links[-1]
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
    md_content.append(f"> **Last Updated:** {timestamp} IST | **Status:** All Systems Active & Synchronized\n\n")

    # Leaderboard
    md_content.append("--- \n\n## 🏆 Global Leaderboard & Performance Summary\n\n")
    md_content.append("| Rank | Game Name | Total Videos | Total Views | Avg Views / Video | Performance Tier |\n")
    md_content.append("| :---: | :--- | :---: | :---: | :---: | :---: |\n")

    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    for idx, item in enumerate(sorted_analytics):
        rank_icon = medals[idx] if idx < len(medals) else f"{idx + 1}"
        tier = ("🔥 Viral / Hype" if item['avg_views'] > 7000
                else "⚡ Trending" if item['avg_views'] > 4000
                else "📈 Stable")
        md_content.append(
            f"| {rank_icon} | **{item['game']}** | {item['uploaded_count']} | "
            f"{item['total_views']:,} | {item['avg_views']:,} | {tier} |\n"
        )

    # Live table
    md_content.append("\n--- \n\n## 📺 Live Post Titles + Views (Latest per Game)\n\n")
    md_content.append("> 🔵 FB = Facebook post live | 🟣 IG = Instagram post live | ⏳ = Pending\n\n")
    md_content.append("| Game Name | 📅 Last Posted | 📺 Latest Title | 🔵 Facebook | 👁️ FB Views | 🟣 Instagram | 👁️ IG Views | 📊 Remaining / Total | 📂 Source | 📜 All |\n")
    md_content.append("|---|---|---|---|---|---|---|---|---|---|\n")

    # 🔥 FIX 3: Sort by latest post time
    sorted_games = sorted(
        actual_posted_titles.keys(),
        key=lambda g: get_latest_post_time(g) or "0000",
        reverse=True
    )

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

        # Latest post date
        latest_post_time = get_latest_post_time(g_name)
        if latest_post_time:
            try:
                dt = datetime.fromisoformat(latest_post_time.replace("+0000", "+00:00"))
                date_str = dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                date_str = latest_post_time[:16]
        else:
            date_str = "—"

        if not videos:
            md_content.append(
                f"| **{g_name}** | {date_str} | _Not Posted Yet_ | ⏳ Pending | _0_ | ⏳ Pending | _0_ | {progress_md} | _N/A_ | — |\n"
            )
            continue

        latest_posted = None
        for v in videos:
            if v.get("fb_posted") or v.get("ig_posted"):
                latest_posted = v
                break

        latest = latest_posted if latest_posted else videos[0]
        title = (latest.get("title") or "").replace("\n", " ").replace("|", "\\|")[:80] or "_Untitled_"

        fb_md = f"[🔵 FB]({latest['fb_link']})" if latest.get("fb_posted") and latest.get("fb_link") else "⏳ Pending"
        fb_v_md = f"{latest.get('fb_views', 0):,}" if latest.get("fb_posted") else "_0_"
        ig_md = f"[🟣 IG]({latest['ig_link']})" if latest.get("ig_posted") and latest.get("ig_link") else "⏳ Pending"
        ig_v_md = f"{latest.get('ig_views', 0):,}" if latest.get("ig_posted") else "_0_"

        # 🔥 FIX 1: Source link latest video ka
        src_link = ""
        if latest_posted:
            src_link = latest_posted.get("source_link", "")
        if not src_link and videos:
            src_link = videos[0].get("source_link", "")
        if not src_link:
            src_urls = source_links_map.get(g_name, [])
            src_link = src_urls[0] if src_urls else ""
        src_md = f"[📂]({src_link})" if src_link else "_N/A_"

        if g_name in game_file_links:
            all_md = f"**[📜 View {len(videos)}]({game_file_links[g_name]})**"
        else:
            all_md = f"_{len(videos)}_"

        md_content.append(
            f"| **{g_name}** | {date_str} | {title} | {fb_md} | {fb_v_md} | {ig_md} | {ig_v_md} | {progress_md} | {src_md} | {all_md} |\n"
        )

    # Full history links
    md_content.append("\n--- \n\n## 📜 Full Video History\n\n")
    md_content.append("> Click any game below to view its complete video list with all FB/IG links:\n\n")

    for g_name in sorted_games:
        videos = actual_posted_titles.get(g_name, [])
        if not videos:
            continue
        file_link = game_file_links.get(g_name, "")
        if file_link:
            md_content.append(f"- **🎮 {g_name}** — [📜 View All {len(videos)} Videos]({file_link})\n")

    # Rotation
    rotation_file = "logs/rotation_history.json"
    if os.path.exists(rotation_file):
        try:
            with open(rotation_file, 'r', encoding='utf-8') as f:
                rot = json.load(f)

            md_content.append("\n--- \n\n## 🔄 Game Rotation Queue\n\n")
            md_content.append(
                f"**📊 Total Games:** {rot.get('total_games', 0)} | **🎯 Current:** `{rot.get('current_game', 'N/A')}` | "
                f"**⏭️ Next Game:** `{rot.get('next_game', 'N/A')}` (Position #{rot.get('next_game_position', 0)}) | "
                f"**🔢 Total Runs:** {rot.get('total_runs', 0)}\n\n"
            )
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
                if status == "current":
                    status_md = "🎯 **CURRENT**"
                elif status == "next_up":
                    status_md = "⏭️ **NEXT UP**"
                else:
                    status_md = f"⏳ Wait {next_in}"
                md_content.append(f"| {pos} | **{gname}** | {uploaded} | {last_run} | {next_in} | {status_md} |\n")

            recent_logs = rot.get("rotation_log", [])[-5:]
            if recent_logs:
                md_content.append("\n### 📜 Recent Runs (Last 5)\n\n")
                md_content.append("| Run # | Game | Timestamp (IST) |\n")
                md_content.append("|:---:|---|---|\n")
                for log_entry in reversed(recent_logs):
                    md_content.append(f"| {log_entry['run']} | {log_entry['game']} | {log_entry['timestamp']} |\n")
        except Exception as e:
            log(f"⚠️ Rotation section error: {e}")

    with open(dashboard_path, 'w', encoding='utf-8') as f:
        f.writelines(md_content)

    git_commit_and_push([
        dashboard_path, leaderboard_json, history_json,
        "logs/agent_memory.json", "logs/rotation_history.json",
        "logs/games/"
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

    # Auto-fix broken links
    for g_name, videos in memory.get("actual_posted_titles", {}).items():
        if not isinstance(videos, list):
            continue
        for v in videos:
            if not isinstance(v, dict):
                continue
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
        if not g_name:
            continue
        file_mapping[g_name] = f
        game_list.append(g_name)

    game_list = sorted(list(set(game_list)))
    log(f"📁 Found {len(game_list)} games: {game_list}")

    actual_posted_titles, game_views_summary = fetch_fb_ig_data(game_list)
    if not game_views_summary:
        game_views_summary = {g: 0 for g in game_list}

    last_game = memory.get("last_played_game", "")
    if last_game in game_list:
        next_index = (game_list.index(last_game) + 1) % len(game_list)
        chosen_game = game_list[next_index]
    else:
        chosen_game = game_list[0] if game_list else "DefaultGame"

    # Empty file skip
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
> Last Updated: {now_ist_str()} IST

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
    }))


if __name__ == "__main__":
    run_agent_brain()