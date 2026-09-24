import os
import glob
import json
import random
import requests
import sys
import subprocess
from datetime import datetime, timedelta

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

def git_commit_and_push(file_paths_to_add, commit_message="Auto-Agent: Fix file target warning & update A-Z dashboard [skip ci]"):
    try:
        subprocess.run(["git", "config", "--global", "user.name", "github-actions[bot]"], check=False)
        subprocess.run(["git", "config", "--global", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"], check=False)
        
        for path in file_paths_to_add:
            if os.path.exists(path):
                subprocess.run(["git", "add", path], check=False)
            
        subprocess.run(["git", "commit", "-m", commit_message], check=False)
        push_res = subprocess.run(["git", "push"], capture_output=True, text=True, check=False)
        log(f"Git Push Result: {push_res.stdout} {push_res.stderr}")
    except Exception as e:
        log(f"Git auto-push error: {e}")

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
            log(f"Chart error: {e}")

    if REPORTLAB_AVAILABLE:
        try:
            doc = SimpleDocTemplate(pdf_path, pagesize=letter)
            elements = []
            styles = getSampleStyleSheet()
            title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=18, textColor=colors.HexColor('#1A237E'), spaceAfter=15, alignment=1)
            heading_style = ParagraphStyle('HeadingStyle', parent=styles['Heading2'], fontSize=13, textColor=colors.HexColor('#3F51B5'), spaceBefore=10, spaceAfter=5)
            normal_style = styles['Normal']
            
            elements.append(Paragraph("Multi-Platform Gaming Agent - Clean Analytics Report", title_style))
            elements.append(Paragraph(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", normal_style))
            elements.append(Spacer(1, 15))
            
            elements.append(Paragraph("Performance & Efficiency Leaderboard", heading_style))
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
            log(f"PDF error: {e}")
            
    return sorted_analytics

def update_unified_dashboard(game_name, chosen_style, ai_title, specific_uploaded_link, post_link, platform_name, views_count, game_views_summary, game_stats):
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
        "post_link": post_link,
        "platform": platform_name
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
        log(f"Leaderboard error: {e}")

    md_content = []
    md_content.append("# GAMING AGENT COMMAND & ANALYTICS DASHBOARD\n\n")
    md_content.append(f"> Last Updated: {timestamp} | Status: All Systems Active & Synchronized\n\n")
    
    md_content.append("--- \n\n## Global Leaderboard & Performance Summary\n\n")
    md_content.append("| Rank | Game Name | Total Videos | Total Views | Avg Views / Video | Performance Tier |\n")
    md_content.append("| :---: | :--- | :---: | :---: | :---: | :---: |\n")
    
    medals = ["1", "2", "3", "4", "5"]
    for idx, item in enumerate(sorted_analytics):
        rank_icon = medals[idx] if idx < len(medals) else f"{idx+1}"
        tier = "Viral / Hype" if item['avg_views'] > 7000 else "Trending" if item['avg_views'] > 4000 else "Stable"
        md_content.append(f"| {rank_icon} | **{item['game']}** | {item['uploaded_count']} | {item['total_views']:,} | {item['avg_views']:,} | {tier} |\n")
        
    md_content.append("\n--- \n\n## Complete A to Z Upload & Execution History\n\n")
    md_content.append("| # | Game Name | Timestamp | AI Generated Title | Views | Source File Link | Live Post Link | Platform | Status |\n")
    md_content.append("|---|---|---|---|---|---|---|---|---|\n")

    global_counter = 1
    for g_name in sorted(all_history.keys()):
        for entry in all_history[g_name]:
            v_str = f"{entry['views']:,} views" if entry['views'] > 0 else "Pending"
            p_name = entry.get('platform', 'Facebook / Auto')
            p_link = entry.get('post_link', '#')
            
            if p_link != "N/A" and p_link != "#":
                link_markdown = f"[View Post]({p_link})"
            else:
                link_markdown = "Pending / Local"
            
            md_content.append(f"| {global_counter} | **{g_name}** | {entry['timestamp']} | {entry['ai_title']} | {v_str} | [Source]({entry['source_link']}) | {link_markdown} | {p_name} | Active |\n")
            global_counter += 1

    with open(dashboard_path, 'w', encoding='utf-8') as f:
        f.writelines(md_content)
        
    git_commit_and_push([dashboard_path, leaderboard_json, history_json, "logs/agent_memory.json", "current_game.txt"])


def get_game_video_stats(target_file, memory, game_name):
    total_links = 0
    if target_file and os.path.exists(target_file):
        try:
            with open(target_file, 'r', encoding='utf-8', errors='ignore') as f:
                lines = []
                for line in f:
                    line_str = line.strip()
                    if line_str and "http" in line_str:
                        lines.append(line_str)
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
        return None, "", "", "", "", 0, {}, memory
    
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
        
        if res_fb.status_code == 200:
            for video in res_fb.json().get("data", []):
                vid_id = video.get("id", "")
                title = video.get("title", "") or video.get("description", "")
                permalink = video.get("permalink_url", f"https://facebook.com/{vid_id}")
                views = video.get("views", 0)
                text = title.lower()

                for game in game_list:
                    if game.lower() in text:
                        temp_game_views[game] += views
                        temp_game_counts[game] += 1
                        if views >= 5000:
                            temp_viral_counts[game] += 1
                        if views > best_views and vid_id not in processed_viral_ids:
                            best_views = views
                            winning_game = game
                            winning_title = title
                            winning_link = permalink
                            platform_type = "Facebook"
                            winning_views = views

        for ig in ig_data_list:
            ig_id = ig.get("id", "")
            caption = ig.get("caption", "")
            permalink = ig.get("permalink", f"https://instagram.com")
            approx_views = (ig.get("like_count", 0) * 10) + (ig.get("comments_count", 0) * 20)
            text = caption.lower()

            for game in game_list:
                if game.lower() in text:
                    temp_game_views[game] += approx_views
                    temp_game_counts[game] += 1
                    if approx_views > best_views and ig_id not in processed_viral_ids:
                        best_views = approx_views
                        winning_game = game
                        winning_title = caption[:50]
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

        return winning_game, winning_title, winning_link, platform_type, winning_views, temp_game_views, memory
        
    except Exception as e:
        log(f"Multi-platform Fetch Error: {e}")
        
    return None, "", "", "Facebook", 0, {}, memory

def run_agent_brain():
    links_dir = "game_links_editor"
    archive_dir = "archived_links"
    memory_file = "logs/agent_memory.json"
    
    os.makedirs("logs", exist_ok=True)
    os.makedirs(archive_dir, exist_ok=True)
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

    all_files = glob.glob(os.path.join(links_dir, "*.txt"))
    if not all_files:
        log("Warning: game_links_editor folder mein koi .txt file nahi mili.")

    valid_game_files = []
    for f in all_files:
        try:
            with open(f, 'r', encoding='utf-8', errors='ignore') as file_obj:
                content = file_obj.read().strip()
            if not content:
                archive_path = os.path.join(archive_dir, os.path.basename(f))
                os.rename(f, archive_path)
            else:
                valid_game_files.append(f)
        except IOError:
            continue

    if not valid_game_files:
        log("Error: game_links_editor mein koi bhi valid non-empty file nahi mili.")
        sys.exit(1)

    game_list = []
    file_mapping = {}
    for f in valid_game_files:
        g_name = os.path.basename(f).replace("_uploaded_links.txt", "").replace(".txt", "").strip()
        if g_name:
            game_list.append(g_name)
            file_mapping[g_name] = f

    game_list.sort()

    winning_game, winning_title, winning_link, platform_type, winning_views, game_views_summary, memory = fetch_and_calculate_scores_multiplatform(game_list, memory)
    
    last_game = memory.get("last_played_game", "")
    if last_game in game_list:
        next_index = (game_list.index(last_game) + 1) % len(game_list)
        chosen_game = game_list[next_index]
    else:
        chosen_game = game_list[0] if game_list else "DefaultGame"

    # Game name ko simple text file mein save karna (bina env variable ke)
    with open("current_game.txt", "w", encoding="utf-8") as f:
        f.write(chosen_game)

    target_file = file_mapping.get(chosen_game, "")
    if not target_file or not os.path.exists(target_file):
        log(f"Critical Error: Target file for chosen game '{chosen_game}' not found. Halting pipeline execution.")
        sys.exit(1)

    styles = memory.get("title_styles", {})
    chosen_style = random.choices(list(styles.keys()), weights=list(styles.values()), k=1)[0]
    
    game_hashtag = f"#{chosen_game.replace(' ', '')}"
    generated_ai_title = f"Epic {chosen_game} Gameplay Moments! {game_hashtag}"

    try:
        api_key = get_active_key()
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        prompt = f"""You are an advanced AI Social Media Manager.
Target Game: {chosen_game}
Selected Style: {chosen_style}
Hashtag to include: {game_hashtag}
Generate a catchy, viral social media video title for this game, and make sure to include the exact game name '{chosen_game}' and its hashtag '{game_hashtag}' in the title.
Respond ONLY in strict JSON format:
{{"chosen_game": "{chosen_game}", "chosen_style": "{chosen_style}", "ai_title": "Your generated catchy title here with {game_hashtag}", "reasoning": "Approved"}}"""
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
                    if game_hashtag.lower() not in generated_ai_title.lower():
                        generated_ai_title = f"{generated_ai_title} {game_hashtag}"
    except Exception as e:
        log(f"AI Title generation warning: {e}")
        generated_ai_title = f"{chosen_game} Best Moments! {game_hashtag}"

    total_links, uploaded_links, remaining_links, game_stats = get_game_video_stats(target_file, memory, chosen_game)
    
    specific_uploaded_link = "N/A"
    try:
        with open(target_file, 'r', encoding='utf-8', errors='ignore') as f:
            valid_links = []
            for line in f:
                line_str = line.strip()
                if line_str and "http" in line_str:
                    parts = line_str.split("http")
                    url = "http" + parts[1].split()[0]
                    valid_links.append(url)
            if valid_links:
                link_index = uploaded_links % len(valid_links)
                specific_uploaded_link = valid_links[link_index]
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
        game_stats=memory.get("game_stats", {})
    )

    print(f"""
GAMING AGENT COMMAND & ANALYTICS DASHBOARD (MULTI-PLATFORM)
> Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Status: Smart Sync Active

Current Execution Status:
• Current Upload Game : {chosen_game}
• AI Generated Title   : {generated_ai_title}
• Detected Platform    : {platform_type if winning_link else "Pending"}
• Live Post Link       : {winning_link if winning_link else "N/A"}
• Source File Link     : {specific_uploaded_link}
• Engagement Views     : {winning_views:,} views

Progress Stats:
• Total Videos         : {total_links}
• Uploaded So Far      : {uploaded_links + 1}
• Remaining Videos     : {remaining_links}
""")

if __name__ == "__main__":
    run_agent_brain()
