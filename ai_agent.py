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
    sys.stderr.write(f"{msg}\n")

def get_active_key():
    valid = [k for k in GEMINI_KEYS if k]
    if not valid:
        raise ValueError("No valid Gemini API keys found.")
    return random.choice(valid)

# 🔄 Git Auto-Commit & Push Function
def git_commit_and_push(file_paths_to_add, commit_message="Auto-Agent: Update A-Z unified gaming dashboard [skip ci]"):
    try:
        subprocess.run(["git", "config", "--global", "user.name", "github-actions[bot]"], check=False)
        subprocess.run(["git", "config", "--global", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"], check=False)
        
        for path in file_paths_to_add:
            if os.path.exists(path):
                subprocess.run(["git", "add", path], check=False)
            
        subprocess.run(["git", "commit", "-m", commit_message], check=False)
        push_res = subprocess.run(["git", "push"], capture_output=True, text=True, check=False)
        log(f"🔄 Git Push Result: {push_res.stdout} {push_res.stderr}")
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
            
            elements.append(Paragraph("🎮 Facebook Gaming Agent - Clean Analytics Report", title_style))
            elements.append(Paragraph(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", normal_style))
            elements.append(Spacer(1, 15))
            
            elements.append(Paragraph("🏆 Performance & Efficiency Leaderboard", heading_style))
            table_data = [["Rank", "Game Name", "Total Views", "Videos", "Avg/Video", "View Share"]]
            for idx, item in enumerate(sorted_analytics, 1):
                table_data.append([str(idx), item["game"], f"{item['total_views']:,}", str(item['uploaded_count']), f"{item['avg_views']:,}", f"{item['share_pct']}%"])
                
            t = Table(table_data, colWidths=[40, 150, 90, 60, 90, 70])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#3F51B5')),
                ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('BOTTOMPADDING', (0,0), (-1,0), 8),
                ('BACKGROUND', (0,1), (-1,-1), colors.HexColor('#F5F5F5')),
                ('GRID', (0,0), (-1,-1), 0.5, colors.grey)
            ]))
            elements.append(t)
            doc.build(elements)
        except Exception as e:
            log(f"⚠️ PDF error: {e}")
            
    return sorted_analytics

# ✨ A-Z SINGLE TABLE UNIFIED DASHBOARD RECORDING FUNCTION
def update_unified_dashboard(game_name, chosen_style, ai_title, specific_uploaded_link, facebook_video_link, views_count, game_views_summary, game_stats):
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
        
    all_history[game_name].append({
        "timestamp": timestamp,
        "style": chosen_style,
        "ai_title": ai_title,
        "views": views_count,
        "source_link": specific_uploaded_link,
        "fb_link": facebook_video_link
    })
    
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
                    "rank": i+1, 
                    "game_name": item["game"], 
                    "total_views": item["total_views"], 
                    "uploaded_videos": item["uploaded_count"],
                    "avg_views_per_video": item["avg_views"],
                    "view_share_percentage": item["share_pct"]
                } for i, item in enumerate(sorted_analytics)
            ], f, indent=4)
    except Exception as e:
        log(f"⚠️ Leaderboard error: {e}")

    # Markdown Content A to Z Single Table Format
    md_content = []
    md_content.append("# 🚀 GAMING AGENT COMMAND & ANALYTICS DASHBOARD\n\n")
    md_content.append(f"> **Last Updated:** {timestamp} | **Status:** All Systems Active & Synchronized\n\n")
    
    md_content.append("--- \n\n## 🏆 Global Leaderboard & Performance Summary\n\n")
    md_content.append("| Rank | Game Name | Total Videos | Total Views | Avg Views / Video | Performance Tier |\n")
    md_content.append("| :---: | :--- | :---: | :---: | :---: | :---: |\n")
    
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    for idx, item in enumerate(sorted_analytics):
        rank_icon = medals[idx] if idx < len(medals) else f"{idx+1}"
        tier = "🔥 Viral / Hype" if item['avg_views'] > 7000 else "⚡ Trending" if item['avg_views'] > 4000 else "📈 Stable"
        md_content.append(f"| {rank_icon} | **{item['game']}** | {item['uploaded_count']} | {item['total_views']:,} | {item['avg_views']:,} | {tier} |\n")
        
    md_content.append("\n--- \n\n## 📊 Complete A to Z Upload & Execution History\n\n")
    md_content.append("| # | Game Name | Timestamp | AI Generated Title | Views | Source File Link | Clickable Facebook Video Link | Status |\n")
    md_content.append("|---|---|---|---|---|---|---|---|\n")

    global_counter = 1
    for g_name in sorted(all_history.keys()):
        for entry in all_history[g_name]:
            v_str = f"{entry['views']:,} views" if entry['views'] > 0 else "Pending"
            md_content.append(f"| {global_counter} | **{g_name}** | {entry['timestamp']} | {entry['ai_title']} | {v_str} | [Source]({entry['source_link']}) | [🔥 Watch on FB]({entry['fb_link']}) | ✅ Active |\n")
            global_counter += 1

    with open(dashboard_path, 'w', encoding='utf-8') as f:
        f.writelines(md_content)
        
    git_commit_and_push([dashboard_path, leaderboard_json, history_json, "logs/agent_memory.json"])


def get_game_video_stats(target_file, memory, game_name):
    total_links = 0
    if target_file and os.path.exists(target_file):
        try:
            with open(target_file, 'r', encoding='utf-8', errors='ignore') as f:
                lines = [line.strip() for line in f if line.strip() and line.strip().startswith("http")]
                total_links = len(lines)
        except Exception:
            pass
            
    game_stats = memory.get("game_stats", {})
    if game_name not in game_stats:
        game_stats[game_name] = {"uploaded_count": 0}
    
    uploaded_links = game_stats[game_name]["uploaded_count"]
    remaining_links = max(0, total_links - uploaded_links)
    
    return total_links, uploaded_links, remaining_links, game_stats


def fetch_and_calculate_scores(game_list, memory):
    if not FB_PAGE_ID or not FB_ACCESS_TOKEN:
        return None, "", "", "", 0, {}, memory
    
    try:
        twenty_eight_days_ago = datetime.now() - timedelta(days=28)
        since_timestamp = int(twenty_eight_days_ago.timestamp())

        url = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/videos"
        params = {
            "fields": "id,title,description,views,permalink_url,created_time",
            "since": since_timestamp,
            "access_token": FB_ACCESS_TOKEN,
            "limit": 100
        }
        response = requests.get(url, params=params, timeout=15)
        
        if response.status_code != 200:
            return None, "", "", "", 0, {}, memory
            
        data = response.json().get("data", [])
        
        processed_viral_ids = memory.get("processed_viral_ids", [])
        game_scores = memory.get("game_scores", {})
        title_styles = memory.get("title_styles", {})
        
        best_views = 7000
        winning_game = None
        winning_title = ""
        winning_video_id = ""
        winning_video_link = ""
        winning_video_views = 0

        temp_game_views = {g: 0 for g in game_list}
        temp_game_counts = {g: 0 for g in game_list}
        temp_viral_counts = {g: 0 for g in game_list}
        
        for video in data:
            video_id = video.get("id", "")
            title = video.get("title", "")
            description = video.get("description", "")
            permalink = video.get("permalink_url", f"https://www.facebook.com/{video_id}")
            text = (title + " " + description).lower()
            views = video.get("views", 0)

            for game in game_list:
                if game.lower() in text:
                    temp_game_views[game] += views
                    temp_game_counts[game] += 1
                    
                    if views >= 7000:
                        temp_viral_counts[game] += 1
                    
                    if views >= 7000 and video_id not in processed_viral_ids:
                        if views > best_views or winning_game is None:
                            best_views = views
                            winning_game = game
                            winning_title = title if title else description
                            winning_video_id = video_id
                            winning_video_link = permalink
                            winning_video_views = views

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

        return winning_game, winning_title, winning_video_id, winning_video_link, winning_video_views, temp_game_views, memory
        
    except Exception as e:
        log(f"❌ ERROR: {e}")
        
    return None, "", "", "", 0, {}, memory

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
        "winning_title_context": "",
        "winning_video_id": "",
        "winning_video_link": "",
        "winning_video_views": 0,
        "processed_viral_ids": [],
        "style_history": {},
        "game_stats": {}
    }
    
    if os.path.exists(memory_file):
        try:
            with open(memory_file, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    memory.update(loaded)
        except Exception:
            pass

    # 🛑 SAFE CHECK: Error handling for missing files
    all_files = glob.glob(os.path.join(links_dir, "*.txt"))
    if not all_files:
        all_files = glob.glob("*.txt") + glob.glob("game_links_editor/*.txt")

    if not all_files:
        log("❌ Error: No valid game files found anywhere.")
        sys.exit(0)

    valid_game_files = [f for f in all_files if os.path.exists(f)]

    game_list = []
    file_mapping = {}
    for f in valid_game_files:
        g_name = os.path.basename(f).replace("_uploaded_links.txt", "").replace(".txt", "").strip()
        if not g_name:
            continue
        file_mapping[g_name] = f
        game_list.append(g_name)

    game_list = sorted(list(set(game_list)))

    high_perf_game, winning_title, current_video_id, current_video_link, current_video_views, game_views_summary, memory = fetch_and_calculate_scores(game_list, memory)
    
    last_game = memory.get("last_played_game", "")
    if last_game in game_list:
        next_index = (game_list.index(last_game) + 1) % len(game_list)
        chosen_game = game_list[next_index]
    else:
        chosen_game = game_list[0] if game_list else "DefaultGame"

    # 🛑 SAFE FALLBACK CHECK (Error fix for missing target files)
    target_file = file_mapping.get(chosen_game, "")
    if not target_file or not os.path.exists(target_file):
        log(f"⚠️ Warning: Target file for {chosen_game} not found. Using fallback file.")
        if valid_game_files:
            target_file = valid_game_files[0]
            chosen_game = os.path.basename(target_file).replace(".txt", "").strip()
        else:
            sys.exit(0)

    styles = memory.get("title_styles", {})
    style_names = list(styles.keys())
    style_weights = list(styles.values())
    chosen_style = random.choices(style_names, weights=style_weights, k=1)[0]
    
    generated_ai_title = f"🔥 Insane {chosen_game} Gameplay Highlights!"

    try:
        api_key = get_active_key()
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        prompt = f"""You are an advanced AI Social Media Manager.
Target Game: {chosen_game}
Selected Style: {chosen_style}
Generate a catchy, viral social media video title for this game.
Respond ONLY in strict JSON format:
{{"chosen_game": "{chosen_game}", "chosen_style": "{chosen_style}", "ai_title": "Your generated catchy title here", "reasoning": "Approved for high engagement"}}"""
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        response = requests.post(url, json=payload, timeout=15)
        response.raise_for_status()
        res_data = response.json()
        candidates = res_data.get("candidates", [])
        if candidates and "content" in candidates[0]:
            parts = candidates[0]["content"].get("parts", [])
            if parts:
                text_res = parts[0].get("text", "").replace("```json", "").replace("```", "").strip()
                parsed = json.loads(text_res)
                if parsed.get("ai_title"):
                    generated_ai_title = parsed.get("ai_title")
    except Exception:
        pass

    total_links, uploaded_links, remaining_links, game_stats = get_game_video_stats(target_file, memory, chosen_game)
    
    specific_uploaded_link = "N/A"
    try:
        with open(target_file, 'r', encoding='utf-8', errors='ignore') as f:
            lines = [line.strip() for line in f if line.strip() and line.strip().startswith("http")]
            if lines:
                link_index = uploaded_links % len(lines)
                specific_uploaded_link = lines[link_index]
    except Exception:
        pass

    game_stats[chosen_game]["uploaded_count"] = uploaded_links + 1
    memory["game_stats"] = game_stats
    memory["last_used_style"] = chosen_style
    memory["last_played_game"] = chosen_game
    
    next_game = ""
    next_link = "N/A"
    if game_list:
        if chosen_game in game_list:
            next_idx = (game_list.index(chosen_game) + 1) % len(game_list)
            next_game = game_list[next_idx]
        else:
            next_game = game_list[0]
            
        next_target_file = file_mapping.get(next_game)
        if next_target_file and os.path.exists(next_target_file):
            try:
                with open(next_target_file, 'r', encoding='utf-8', errors='ignore') as f:
                    next_lines = [line.strip() for line in f if line.strip() and line.strip().startswith("http")]
                    next_uploaded_count = memory.get("game_stats", {}).get(next_game, {}).get("uploaded_count", 0)
                    if next_lines:
                        next_link = next_lines[next_uploaded_count % len(next_lines)]
            except Exception:
                pass

    try:
        with open(memory_file, 'w', encoding='utf-8') as f:
            json.dump(memory, f, indent=4)
    except Exception:
        pass

    total_links, uploaded_links, remaining_links, _ = get_game_video_stats(target_file, memory, chosen_game)

    update_unified_dashboard(
        game_name=chosen_game,
        chosen_style=chosen_style,
        ai_title=generated_ai_title,
        specific_uploaded_link=specific_uploaded_link,
        facebook_video_link=current_video_link,
        views_count=current_video_views,
        game_views_summary=game_views_summary,
        game_stats=memory.get("game_stats", {})
    )

    print(f"""
🚀 GAMING AGENT COMMAND & ANALYTICS DASHBOARD
> Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Status: All Systems Active & Synchronized

📊 Current Execution Status:
• Current Upload Game : {chosen_game}
• AI Generated Title   : {generated_ai_title}
• Chosen Style         : {chosen_style}
• Source File Link     : {specific_uploaded_link}
• Facebook Video Link  : {current_video_link}
• Selected Video Views : {current_video_views:,} views

⏭️ Next Rotation Preview:
• Next Game            : {next_game}
• Next Link            : {next_link}

📈 Progress Stats:
• Total Videos         : {total_links}
• Uploaded So Far      : {uploaded_links}
• Remaining Videos     : {remaining_links}
""")

if __name__ == "__main__":
    run_agent_brain()
