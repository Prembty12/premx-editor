import os
import glob
import json
import random
import requests
import sys
import subprocess
from datetime import datetime, timedelta

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
    """Human-readable logs -> stderr (bash ke log file me jayenge, stdout ko pollute nahi karenge)"""
    sys.stderr.write(f"{msg}\n")
    sys.stderr.flush()


def get_active_key():
    valid = [k for k in GEMINI_KEYS if k]
    if not valid:
        return None
    return random.choice(valid)


# 🔄 Git Auto-Commit & Push Function — FIXED: no stdout leak
def git_commit_and_push(file_paths_to_add, commit_message="Auto-Agent: Sync dashboard + live titles [skip ci]"):
    try:
        # 🔇 Saare git commands ka output DEVNULL ya captured — stdout pe leak NA ho
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
            title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=18, textColor=colors.HexColor('#1A237E'), spaceAfter=15, alignment=1)
            heading_style = ParagraphStyle('HeadingStyle', parent=styles['Heading2'], fontSize=13, textColor=colors.HexColor('#3F51B5'), spaceBefore=10, spaceAfter=5)
            normal_style = styles['Normal']

            elements.append(Paragraph("🎮 Multi-Platform Gaming Agent - Clean Analytics Report", title_style))
            elements.append(Paragraph(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", normal_style))
            elements.append(Spacer(1, 15))

            elements.append(Paragraph("🏆 Performance & Efficiency Leaderboard", heading_style))
            table_data = [["Rank", "Game Name", "Total Views", "Videos", "Avg/Video", "View Share"]]
            for idx, item in enumerate(sorted_analytics, 1):
                table_data.append([str(idx), item["game"], f"{item['total_views']:,}", str(item['uploaded_count']), f"{item['avg_views']:,}", f"{item['share_pct']}%"])

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


def update_unified_dashboard(game_name, chosen_style, ai_title, specific_uploaded_link,
                             post_link, platform_name, views_count,
                             game_views_summary, game_stats, actual_posted_titles=None):
    if actual_posted_titles is None:
        actual_posted_titles = {}

    dashboard_path = "GAMING_DASHBOARD.md"
    leaderboard_json = os.path.join("logs/leaderboard", "games_performance_leaderboard.json")
    os.makedirs("logs/leaderboard", exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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
        "actual_posted_title": actual_posted_titles.get(game_name, ""),
        "views": views_count,
        "source_link": specific_uploaded_link,
        "post_link": post_link,
        "platform": platform_name,
    }
    all_history[game_name].append(new_entry)

    # Backfill live titles on all older entries
    for g_name, entries in all_history.items():
        live_title = actual_posted_titles.get(g_name, "")
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

    md_content = []
    md_content.append("# 🚀 GAMING AGENT COMMAND & ANALYTICS DASHBOARD\n\n")
    md_content.append(f"> **Last Updated:** {timestamp} | **Status:** All Systems Active & Synchronized\n\n")

    md_content.append("--- \n\n## 🏆 Global Leaderboard & Performance Summary\n\n")
    md_content.append("| Rank | Game Name | Total Videos | Total Views | Avg Views / Video | Performance Tier |\n")
    md_content.append("| :---: | :--- | :---: | :---: | :---: | :---: |\n")

    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    for idx, item in enumerate(sorted_analytics):
        rank_icon = medals[idx] if idx < len(medals) else f"{idx + 1}"
        tier = "🔥 Viral / Hype" if item['avg_views'] > 7000 else "⚡ Trending" if item['avg_views'] > 4000 else "📈 Stable"
        md_content.append(f"| {rank_icon} | **{item['game']}** | {item['uploaded_count']} | {item['total_views']:,} | {item['avg_views']:,} | {tier} |\n")

    md_content.append("\n--- \n\n## 📺 Live Post Titles (Fetched from Facebook / Instagram)\n\n")
    md_content.append("> These are the **actual titles/captions** currently live on your FB / IG posts.\n\n")
    md_content.append("| Game Name | 📺 Actual Live Title (FB / IG) | Platform |\n")
    md_content.append("|---|---|---|\n")
    for g_name in sorted(actual_posted_titles.keys()):
        live_title = actual_posted_titles.get(g_name, "").strip() or "_No live post detected yet_"
        live_title = live_title.replace("\n", " ").replace("|", "\\|")[:200]
        md_content.append(f"| **{g_name}** | {live_title} | FB / IG |\n")

    md_content.append("\n--- \n\n## 📊 Complete A to Z Upload & Execution History\n\n")
    md_content.append("| # | Game Name | Timestamp | 🤖 AI Planned Title | 📺 Actual Live Title (FB/IG) | Views | Source File Link | Live Post Link | Platform | Status |\n")
    md_content.append("|---|---|---|---|---|---|---|---|---|---|\n")

    global_counter = 1
    for g_name in sorted(all_history.keys()):
        for entry in all_history[g_name]:
            v_str = f"{entry['views']:,} views" if entry['views'] > 0 else "Pending"
            p_name = entry.get('platform', 'Facebook / Auto')
            p_link = entry.get('post_link', '#')

            if p_link != "N/A" and p_link != "#":
                link_markdown = f"[🔗 View Post]({p_link})"
            else:
                link_markdown = "Pending / Local"

            ai_planned = (entry.get('ai_title', '') or '').replace("\n", " ").replace("|", "\\|")[:120]
            actual_live = (entry.get('actual_posted_title', '') or '').replace("\n", " ").replace("|", "\\|")[:120]
            if not actual_live:
                actual_live = "_Pending fetch_"

            md_content.append(
                f"| {global_counter} | **{g_name}** | {entry['timestamp']} | "
                f"{ai_planned} | {actual_live} | {v_str} | "
                f"[Source]({entry['source_link']}) | {link_markdown} | {p_name} | ✅ Active |\n"
            )
            global_counter += 1

    with open(dashboard_path, 'w', encoding='utf-8') as f:
        f.writelines(md_content)

    git_commit_and_push([dashboard_path, leaderboard_json, history_json, "logs/agent_memory.json"])


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


def fetch_and_calculate_scores_multiplatform(game_list, memory):
    if not FB_PAGE_ID or not FB_ACCESS_TOKEN:
        return None, "", "", "Facebook", 0, {}, {}, memory

    try:
        twenty_eight_days_ago = datetime.now() - timedelta(days=28)
        since_timestamp = int(twenty_eight_days_ago.timestamp())

        fb_url = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/videos"
        params = {
            "fields": "id,title,description,views,permalink_url,created_time",
            "since": since_timestamp,
            "access_token": FB_ACCESS_TOKEN,
            "limit": 50
        }
        res_fb = requests.get(fb_url, params=params, timeout=15)

        ig_url = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}"
        ig_params = {"fields": "instagram_business_account", "access_token": FB_ACCESS_TOKEN}
        res_ig_acc = requests.get(ig_url, params=ig_params, timeout=10)

        ig_data_list = []
        if res_ig_acc.status_code == 200:
            ig_id = res_ig_acc.json().get("instagram_business_account", {}).get("id")
            if ig_id:
                media_url = f"https://graph.facebook.com/v19.0/{ig_id}/media"
                media_params = {"fields": "id,caption,media_url,permalink,timestamp,like_count,comments_count", "access_token": FB_ACCESS_TOKEN, "limit": 50}
                res_ig_media = requests.get(media_url, params=media_params, timeout=15)
                if res_ig_media.status_code == 200:
                    ig_data_list = res_ig_media.json().get("data", [])

        processed_viral_ids = memory.get("processed_viral_ids", [])
        game_scores = memory.get("game_scores", {})
        title_styles = memory.get("title_styles", {})

        best_views = 0
        winning_game = None
        winning_title = ""
        winning_link = ""
        platform_type = "Facebook"
        winning_views = 0

        temp_game_views = {g: 0 for g in game_list}
        temp_game_counts = {g: 0 for g in game_list}
        temp_viral_counts = {g: 0 for g in game_list}

        actual_posted_titles = {g: "" for g in game_list}
        actual_title_timestamps = {g: "" for g in game_list}

        # ---------- FACEBOOK ----------
        if res_fb.status_code == 200:
            for video in res_fb.json().get("data", []):
                vid_id = video.get("id", "")
                title = (video.get("title", "") or video.get("description", "") or "").strip()
                permalink = video.get("permalink_url", f"https://facebook.com/{vid_id}")
                views = video.get("views", 0)
                created = video.get("created_time", "")
                text = title.lower()

                for game in game_list:
                    if game.lower() in text:
                        temp_game_views[game] += views
                        temp_game_counts[game] += 1
                        if views >= 5000:
                            temp_viral_counts[game] += 1

                        if title and created > actual_title_timestamps[game]:
                            actual_posted_titles[game] = title
                            actual_title_timestamps[game] = created

                        if views > best_views and vid_id not in processed_viral_ids:
                            best_views = views
                            winning_game = game
                            winning_title = title
                            winning_link = permalink
                            platform_type = "Facebook"
                            winning_views = views

        # ---------- INSTAGRAM ----------
        for ig in ig_data_list:
            ig_id = ig.get("id", "")
            caption = (ig.get("caption", "") or "").strip()
            permalink = ig.get("permalink", "https://instagram.com")
            approx_views = (ig.get("like_count", 0) * 10) + (ig.get("comments_count", 0) * 20)
            created = ig.get("timestamp", "")
            text = caption.lower()

            for game in game_list:
                if game.lower() in text:
                    temp_game_views[game] += approx_views
                    temp_game_counts[game] += 1

                    if caption and created > actual_title_timestamps[game]:
                        actual_posted_titles[game] = caption
                        actual_title_timestamps[game] = created

                    if approx_views > best_views and ig_id not in processed_viral_ids:
                        best_views = approx_views
                        winning_game = game
                        winning_title = caption[:80]
                        winning_link = permalink
                        platform_type = "Instagram"
                        winning_views = approx_views

        for game in game_list:
            total_v = temp_game_views[game]
            count_v = temp_game_counts[game]
            viral_c = temp_viral_counts[game]
            if count_v > 0:
                avg_v = total_v / count_v
                calculated_score = int(10 + (avg_v / 500) + (viral_c * 25))
            else:
                calculated_score = 10
            game_scores[game] = max(10, calculated_score)

        memory["game_scores"] = game_scores
        memory["title_styles"] = title_styles
        memory["actual_posted_titles"] = actual_posted_titles

        return (winning_game, winning_title, winning_link, platform_type,
                winning_views, temp_game_views, actual_posted_titles, memory)

    except Exception as e:
        log(f"❌ Multi-platform Fetch Error: {e}")

    return None, "", "", "Facebook", 0, {}, {}, memory


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

    # ✅ Robust file finder with proper filter
    all_files = glob.glob(os.path.join(links_dir, "*.txt"))
    if not all_files:
        all_files = glob.glob("game_links_editor/*.txt")

    all_files = [
        f for f in all_files
        if ("_uploaded_links" in f
            or "_links_editor" in f
            or "_posted_links" in f)
    ]

    if not all_files:
        log("❌ Error: No valid game text files found anywhere in the repository.")
        sys.exit(1)

    valid_game_files = [f for f in all_files if os.path.exists(f) and os.path.getsize(f) > 0]

    if not valid_game_files:
        log("❌ Error: All game files are empty. Add links to at least one file.")
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

    (winning_game, winning_title, winning_link, platform_type,
     winning_views, game_views_summary, actual_posted_titles, memory) = \
        fetch_and_calculate_scores_multiplatform(game_list, memory)

    if not actual_posted_titles:
        actual_posted_titles = memory.get("actual_posted_titles", {}) or {}

    # 🔄 Game Rotation logic across runs
    last_game = memory.get("last_played_game", "")
    if last_game in game_list:
        next_index = (game_list.index(last_game) + 1) % len(game_list)
        chosen_game = game_list[next_index]
    else:
        chosen_game = game_list[0] if game_list else "DefaultGame"

    # 🛡️ STRICT TARGET FILE RESOLUTION
    target_file = file_mapping.get(chosen_game, "")
    if not target_file or not os.path.exists(target_file):
        log(f"❌ Critical Error: Target file for chosen game '{chosen_game}' not found. Halting pipeline execution.")
        sys.exit(1)

    styles = memory.get("title_styles", {})
    chosen_style = random.choices(list(styles.keys()), weights=list(styles.values()), k=1)[0]

    # 🎯 Title banane ka kaam MAIN BASH SCRIPT (Step 7, Gemini) karegi.
    #    Yahan sirf placeholder rakha hai dashboard/history ke liye.
    game_hashtag = f"#{chosen_game.replace(' ', '')}"
    generated_ai_title = f"🎮 {chosen_game} Gameplay | {game_hashtag}"

    total_links, uploaded_links, remaining_links, game_stats = get_game_video_stats(target_file, memory, chosen_game)

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

    try:
        with open(memory_file, 'w', encoding='utf-8') as f:
            json.dump(memory, f, indent=4)
    except Exception:
        pass

    update_unified_dashboard(
        game_name=chosen_game,
        chosen_style=chosen_style,
        ai_title=generated_ai_title,
        specific_uploaded_link=specific_uploaded_link,
        post_link=winning_link if winning_link else "N/A",
        platform_name=platform_type if winning_link else "Local / Pending",
        views_count=winning_views,
        game_views_summary=game_views_summary,
        game_stats=memory.get("game_stats", {}),
        actual_posted_titles=actual_posted_titles,
    )

    # Human-readable → stderr
    log(f"""
🚀 GAMING AGENT COMMAND & ANALYTICS DASHBOARD (MULTI-PLATFORM)
> Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Status: Smart Sync Active

📊 Current Execution Status:
• Current Upload Game : {chosen_game}
• Dashboard Placeholder Title : {generated_ai_title}
• Detected Platform   : {platform_type if winning_link else "Pending"}
• Live Post Link      : {winning_link if winning_link else "N/A"}
• Source File Link    : {specific_uploaded_link}
• Engagement Views    : {winning_views:,} views

📈 Progress Stats:
• Total Videos         : {total_links}
• Uploaded So Far      : {uploaded_links + 1}
• Remaining Videos     : {remaining_links}
""")

    # ✅ ONLY JSON to stdout — bash isi ko parse karegi
    print(json.dumps({
        "target_file": target_file,
        "game_name": chosen_game,
        "chosen_style": chosen_style,
        "ai_title": generated_ai_title,
        "actual_posted_title": actual_posted_titles.get(chosen_game, ""),
        "source_url": specific_uploaded_link,
        "total_links": total_links,
        "uploaded_count": uploaded_links + 1,
        "remaining_links": remaining_links,
    }))


if __name__ == "__main__":
    run_agent_brain()