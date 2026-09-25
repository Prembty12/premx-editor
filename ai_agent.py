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


# 📦 PDF aur Graph ke liye imports
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


def log(msg):
    sys.stderr.write(f"{msg}\n")
    sys.stderr.flush()


def get_active_key():
    valid = [k for k in GEMINI_KEYS if k]
    if not valid:
        return None
    return random.choice(valid)


def normalize(s):
    """Game name matching ke liye normalize karo (spaces/underscores/special chars hatao)"""
    if not s:
        return ""
    return re.sub(r'[^a-z0-9]', '', s.lower())


def git_commit_and_push(file_paths_to_add, commit_message="Auto-Agent: Sync dashboard + rotation history [skip ci]"):
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
            "game": g_n,
            "total_views": g_v,
            "uploaded_count": uploaded_count,
            "avg_views": avg_views,
            "share_pct": share_pct
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

            elements.append(Paragraph("🎮 Multi-Platform Gaming Agent - Clean Analytics Report", title_style))
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
    """Game rotation ka COMPLETE history save karo — sab games included, number wise"""
    os.makedirs("logs", exist_ok=True)

    rotation_data = {
        "total_games": 0,
        "rotation_order": [],
        "current_index": 0,
        "current_game": "",
        "next_game": "",
        "next_game_position": 0,
        "last_updated": "",
        "total_runs": 0,
        "rotation_log": [],
        "all_games": []
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
            "position": i + 1,
            "game": g,
            "uploaded": uploaded,
            "last_run": last_run,
            "next_turn_in": next_turn_in,
            "status": status
        })

    rotation_data["all_games"] = all_games_list

    with open(memory_file, 'w', encoding='utf-8') as f:
        json.dump(rotation_data, f, indent=4)

    return rotation_data


def load_source_data():
    """Source files se: URLs + total videos count + video names fetch karo"""
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

                # URLs
                urls = re.findall(r'https?://[^\s\)\]]+', content)
                if urls:
                    source_links_map[gname] = urls

                # Total videos count
                source_videos_count[gname] = content.count("Video id :")

                # Titles (agar file mein ho)
                titles = re.findall(r'Title\s*:\s*(.+)', content)
                source_titles_map[gname] = [t.strip() for t in titles]
            except Exception:
                pass

    return source_links_map, source_videos_count, source_titles_map


def fetch_fb_ig_data(game_list):
    """
    FB + IG se saare recent videos fetch karo.
    Returns: dict {game: [list of videos with fb/ig data]}
    """
    result = {g: [] for g in game_list}

    if not FB_PAGE_ID or not FB_ACCESS_TOKEN:
        log("⚠️ FB_PAGE_ID / FB_ACCESS_TOKEN missing")
        return result, {}

    twenty_eight_days_ago = now_ist() - timedelta(days=28)
    since_timestamp = int(twenty_eight_days_ago.timestamp())

    game_views_summary = {g: 0 for g in game_list}
    fb_videos = []
    ig_medias = []

    # ---------- FACEBOOK ----------
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
            log(f"✅ FB: {len(fb_videos)} videos fetched")
        else:
            log(f"⚠️ FB fetch failed: {res.status_code} {res.text[:200]}")
    except Exception as e:
        log(f"❌ FB fetch error: {e}")

    # ---------- INSTAGRAM ----------
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

    # ---------- MATCH GAMES ----------
    for game in game_list:
        game_norm = normalize(game)
        videos_by_title = {}

        # FB match
        for v in fb_videos:
            title = (v.get("title") or v.get("description") or "").strip()
            if not title:
                continue
            if game_norm and game_norm in normalize(title):
                key = title[:40].lower().strip()
                if key not in videos_by_title:
                    videos_by_title[key] = {
                        "title": title,
                        "fb_link": "",
                        "fb_views": 0,
                        "fb_posted": False,
                        "ig_link": "",
                        "ig_views": 0,
                        "ig_posted": False,
                        "timestamp": v.get("created_time", ""),
                        "vid_id": v.get("id", ""),
                    }
                videos_by_title[key]["fb_link"] = v.get("permalink_url", f"https://facebook.com/{v.get('id','')}")
                videos_by_title[key]["fb_views"] = int(v.get("views", 0) or 0)
                videos_by_title[key]["fb_posted"] = True
                videos_by_title[key]["timestamp"] = max(
                    videos_by_title[key]["timestamp"], v.get("created_time", "")
                )
                game_views_summary[game] += int(v.get("views", 0) or 0)

        # IG match
        for m in ig_medias:
            caption = (m.get("caption") or "").strip()
            if not caption:
                continue
            if game_norm and game_norm in normalize(caption):
                key = caption[:40].lower().strip()
                if key not in videos_by_title:
                    videos_by_title[key] = {
                        "title": caption[:100],
                        "fb_link": "",
                        "fb_views": 0,
                        "fb_posted": False,
                        "ig_link": "",
                        "ig_views": 0,
                        "ig_posted": False,
                        "timestamp": m.get("timestamp", ""),
                        "vid_id": m.get("id", ""),
                    }
                ig_views = (m.get("like_count", 0) * 10) + (m.get("comments_count", 0) * 20)
                videos_by_title[key]["ig_link"] = m.get("permalink", "")
                videos_by_title[key]["ig_views"] = ig_views
                videos_by_title[key]["ig_posted"] = True
                if not videos_by_title[key]["title"]:
                    videos_by_title[key]["title"] = caption[:100]
                videos_by_title[key]["timestamp"] = max(
                    videos_by_title[key]["timestamp"], m.get("timestamp", "")
                )
                game_views_summary[game] += ig_views

        # Sort newest first
        result[game] = sorted(
            videos_by_title.values(),
            key=lambda x: x.get("timestamp", ""),
            reverse=True
        )

    return result, game_views_summary


def update_unified_dashboard(game_name, chosen_style, ai_title, specific_uploaded_link,
                             post_link, platform_name, views_count,
                             game_views_summary, game_stats, actual_posted_titles=None):
    if actual_posted_titles is None:
        actual_posted_titles = {}

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
        "timestamp": timestamp,
        "style": chosen_style,
        "ai_title": ai_title,
        "actual_posted_title": "",
        "views": views_count,
        "source_link": specific_uploaded_link,
        "post_link": post_link,
        "platform": platform_name,
    }

    # Latest FB title
    vids = actual_posted_titles.get(game_name, [])
    if vids:
        new_entry["actual_posted_title"] = vids[0].get("title", "")

    all_history[game_name].append(new_entry)

    # Backfill
    for g_name, entries in all_history.items():
        g_vids = actual_posted_titles.get(g_name, [])
        if isinstance(g_vids, list) and g_vids:
            live_title = g_vids[0].get("title", "")
            if live_title:
                for entry in entries:
                    if not entry.get("actual_posted_title"):
                        entry["actual_posted_title"] = live_title

    try:
        with open(history_json, 'w', encoding='utf-8') as f:
            json.dump(all_history, f, indent=4)
    except Exception:
        pass

    sorted_analytics = generate_visual_reports(game_views_summary, game_stats)

    try:
        with open(leaderboard_json, 'w', encoding='utf-8') as f:
            json.dump([
                {
                    "rank": i + 1,
                    "game_name": item["game"],
                    "total_views": item["total_views"],
                    "uploaded_videos": item["uploaded_count"],
                    "avg_views_per_video": item["avg_views"],
                    "view_share_percentage": item["share_pct"]
                } for i, item in enumerate(sorted_analytics)
            ], f, indent=4)
    except Exception as e:
        log(f"⚠️ Leaderboard error: {e}")

    # Load source data
    source_links_map, source_videos_count, _ = load_source_data()

    md_content = []
    md_content.append("# 🚀 GAMING AGENT COMMAND & ANALYTICS DASHBOARD\n\n")
    md_content.append(f"> **Last Updated:** {timestamp} IST | **Status:** All Systems Active & Synchronized\n\n")

    # ---------- GLOBAL LEADERBOARD ----------
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

    # ---------- LIVE TABLE (LATEST PER GAME) ----------
    md_content.append("\n--- \n\n## 📺 Live Post Titles + Views (Latest per Game)\n\n")
    md_content.append("> 🔵 FB = Facebook post live | 🟣 IG = Instagram post live | ⏳ = Pending\n\n")
    md_content.append("| Game Name | 📺 Latest Title | 🔵 Facebook | 👁️ FB Views | 🟣 Instagram | 👁️ IG Views | 📂 Source | 📜 All |\n")
    md_content.append("|---|---|---|---|---|---|---|---|\n")

    for g_name in sorted(actual_posted_titles.keys()):
        videos = actual_posted_titles.get(g_name, [])

        if not videos:
            md_content.append(
                f"| **{g_name}** | _Not Posted Yet_ | ⏳ Pending | _0_ | ⏳ Pending | _0_ | _N/A_ | — |\n"
            )
            continue

        latest = videos[0]
        title = (latest.get("title") or "").replace("\n", " ").replace("|", "\\|")[:80] or "_Untitled_"

        if latest.get("fb_posted") and latest.get("fb_link"):
            fb_md = f"[🔵 FB]({latest['fb_link']})"
            fb_v_md = f"{latest.get('fb_views', 0):,}"
        else:
            fb_md = "⏳ Pending"
            fb_v_md = "_0_"

        if latest.get("ig_posted") and latest.get("ig_link"):
            ig_md = f"[🟣 IG]({latest['ig_link']})"
            ig_v_md = f"{latest.get('ig_views', 0):,}"
        else:
            ig_md = "⏳ Pending"
            ig_v_md = "_0_"

        src_urls = source_links_map.get(g_name, [])
        src_link = src_urls[-1] if src_urls else ""
        src_md = f"[📂]({src_link})" if src_link else "_N/A_"

        all_md = (f"**[📜 View {len(videos)}](#{g_name.lower().replace(' ', '-')}-all)**"
                  if len(videos) > 1 else "_1_")

        md_content.append(
            f"| **{g_name}** | {title} | {fb_md} | {fb_v_md} | "
            f"{ig_md} | {ig_v_md} | {src_md} | {all_md} |\n"
        )

    # ---------- COLLAPSIBLE FULL LISTS ----------
    md_content.append("\n--- \n\n## 📜 Full Video History (Click to Expand)\n\n")

    for g_name in sorted(actual_posted_titles.keys()):
        videos = actual_posted_titles.get(g_name, [])
        if not videos:
            continue

        anchor = g_name.lower().replace(' ', '-')
        md_content.append(
            f'<details>\n<summary><b>🎮 {g_name} — All {len(videos)} Videos (Newest First)</b></summary>\n\n'
        )
        md_content.append(f'<a id="{anchor}-all"></a>\n\n')
        md_content.append("| # | 📺 Title | 🔵 Facebook | 👁️ FB Views | 🟣 Instagram | 👁️ IG Views | 📂 Source |\n")
        md_content.append("|---|---|---|---|---|---|---|\n")

        src_urls = source_links_map.get(g_name, [])
        src_urls_newest = list(reversed(src_urls))

        for idx, v in enumerate(videos, 1):
            title = (v.get("title") or "").replace("\n", " ").replace("|", "\\|")[:100] or "_Untitled_"

            if v.get("fb_posted") and v.get("fb_link"):
                fb_md = f"[🔵 FB]({v['fb_link']})"
                fb_v_md = f"{v.get('fb_views', 0):,}"
            else:
                fb_md = "⏳ Pending"
                fb_v_md = "_0_"

            if v.get("ig_posted") and v.get("ig_link"):
                ig_md = f"[🟣 IG]({v['ig_link']})"
                ig_v_md = f"{v.get('ig_views', 0):,}"
            else:
                ig_md = "⏳ Pending"
                ig_v_md = "_0_"

            src_link = src_urls_newest[idx - 1] if idx - 1 < len(src_urls_newest) else ""
            src_md = f"[📂]({src_link})" if src_link else "_N/A_"

            md_content.append(
                f"| {idx} | {title} | {fb_md} | {fb_v_md} | {ig_md} | {ig_v_md} | {src_md} |\n"
            )

        md_content.append("\n</details>\n\n")

    # ---------- ROTATION QUEUE ----------
    rotation_file = "logs/rotation_history.json"
    if os.path.exists(rotation_file):
        try:
            with open(rotation_file, 'r', encoding='utf-8') as f:
                rot = json.load(f)

            total_g = rot.get("total_games", 0)
            current_g = rot.get("current_game", "N/A")
            next_g = rot.get("next_game", "N/A")
            next_pos = rot.get("next_game_position", 0)
            total_runs = rot.get("total_runs", 0)

            md_content.append("\n--- \n\n## 🔄 Game Rotation Queue\n\n")
            md_content.append(
                f"**📊 Total Games:** {total_g} | **🎯 Current:** `{current_g}` | "
                f"**⏭️ Next Game:** `{next_g}` (Position #{next_pos}) | "
                f"**🔢 Total Runs:** {total_runs}\n\n"
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

                md_content.append(
                    f"| {pos} | **{gname}** | {uploaded} | {last_run} | {next_in} | {status_md} |\n"
                )

            recent_logs = rot.get("rotation_log", [])[-5:]
            if recent_logs:
                md_content.append("\n### 📜 Recent Runs (Last 5)\n\n")
                md_content.append("| Run # | Game | Timestamp (IST) |\n")
                md_content.append("|:---:|---|---|\n")
                for log_entry in reversed(recent_logs):
                    md_content.append(
                        f"| {log_entry['run']} | {log_entry['game']} | {log_entry['timestamp']} |\n"
                    )
        except Exception as e:
            log(f"⚠️ Rotation section error: {e}")

    with open(dashboard_path, 'w', encoding='utf-8') as f:
        f.writelines(md_content)

    git_commit_and_push([
        dashboard_path,
        leaderboard_json,
        history_json,
        "logs/agent_memory.json",
        "logs/rotation_history.json"
    ])


def get_game_video_stats(target_file, memory, game_name):
    total_links = 0
    if target_file and os.path.exists(target_file):
        try:
            with open(target_file, 'r', encoding='utf-8', errors='ignore') as f:
                lines = [line.strip() for line in f if line.strip() and ('http://' in line or 'https://' in line)]
                total_links = len(lines)
        except Exception:
            pass

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
        "last_used_style": "curiosity",
        "last_played_game": "",
        "processed_viral_ids": [],
        "game_stats": {},
        "actual_posted_titles": {}
    }

    if os.path.exists(memory_file):
        try:
            with open(memory_file, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    memory.update(loaded)
        except Exception:
            pass

    # Find game files
    all_files = glob.glob(os.path.join(links_dir, "*.txt"))
    if not all_files:
        all_files = glob.glob("game_links_editor/*.txt")

    all_files = [
        f for f in all_files
        if ("_uploaded_links" in f or "_links_editor" in f or "_posted_links" in f)
    ]

    if not all_files:
        log("❌ Error: No valid game text files found.")
        sys.exit(1)

    valid_game_files = [f for f in all_files if os.path.exists(f) and os.path.getsize(f) > 0]

    if not valid_game_files:
        log("❌ Error: All game files are empty.")
        sys.exit(1)

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

    log(f"📁 Found {len(game_list)} game file(s): {game_list}")

    # Fetch FB + IG data
    actual_posted_titles, game_views_summary = fetch_fb_ig_data(game_list)

    if not game_views_summary:
        game_views_summary = {g: 0 for g in game_list}

    # Rotation logic
    last_game = memory.get("last_played_game", "")
    if last_game in game_list:
        next_index = (game_list.index(last_game) + 1) % len(game_list)
        chosen_game = game_list[next_index]
    else:
        chosen_game = game_list[0] if game_list else "DefaultGame"

    target_file = file_mapping.get(chosen_game, "")
    if not target_file or not os.path.exists(target_file):
        log(f"❌ Target file for '{chosen_game}' not found.")
        sys.exit(1)

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
            lines = [line.strip() for line in f if line.strip() and ('http://' in line or 'https://' in line)]
            if lines:
                link_index = uploaded_links % len(lines)
                specific_uploaded_link = lines[link_index]
                for token in specific_uploaded_link.split():
                    if token.startswith("http://") or token.startswith("https://"):
                        specific_uploaded_link = token
                        break
    except Exception:
        pass

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

    # Save rotation history
    rotation_info = save_rotation_history(game_list, chosen_game, memory)
    log(f"🔄 Rotation saved. Next game: {rotation_info['next_game']}")

    # Latest FB/IG for chosen game
    latest_fb_link = ""
    latest_ig_link = ""
    latest_views = 0
    if actual_posted_titles.get(chosen_game):
        v = actual_posted_titles[chosen_game][0]
        latest_fb_link = v.get("fb_link", "")
        latest_ig_link = v.get("ig_link", "")
        latest_views = v.get("fb_views", 0) + v.get("ig_views", 0)

    update_unified_dashboard(
        game_name=chosen_game,
        chosen_style=chosen_style,
        ai_title=generated_ai_title,
        specific_uploaded_link=specific_uploaded_link,
        post_link=latest_fb_link or latest_ig_link or "N/A",
        platform_name="Facebook" if latest_fb_link else ("Instagram" if latest_ig_link else "Local / Pending"),
        views_count=latest_views,
        game_views_summary=game_views_summary,
        game_stats=memory.get("game_stats", {}),
        actual_posted_titles=actual_posted_titles,
    )

    log(f"""
🚀 GAMING AGENT COMMAND & ANALYTICS DASHBOARD
> Last Updated: {now_ist_str()} IST

📊 Current Execution Status:
• Current Upload Game : {chosen_game}
• AI Placeholder Title : {generated_ai_title}
• Detected Platform   : {"Facebook" if latest_fb_link else ("Instagram" if latest_ig_link else "Pending")}
• Live Post Link      : {latest_fb_link or latest_ig_link or "N/A"}
• Source File Link    : {specific_uploaded_link}
• Engagement Views    : {latest_views:,} views

📈 Progress Stats:
• Total Videos         : {total_links}
• Uploaded So Far      : {uploaded_links + 1}
• Remaining Videos     : {remaining_links}
""")

    # Only JSON to stdout — bash isi ko parse karegi
    latest_title = ""
    if actual_posted_titles.get(chosen_game):
        latest_title = actual_posted_titles[chosen_game][0].get("title", "")

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
