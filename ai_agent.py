import os
import glob
import json
import random
import requests
import sys
import shutil
import csv
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
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
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

# 📊 ADVANCED ANALYTICS: VISUAL CHART & PROFESSIONAL PDF REPORT
def generate_visual_reports(game_views_summary, game_stats, game_name):
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
            
            plt.suptitle("Advanced Gaming Performance & Efficiency Analytics", fontsize=14, fontweight='bold')
            plt.tight_layout()
            plt.savefig(chart_path, dpi=300)
            plt.close()
        except Exception as e:
            log(f"⚠️ Advanced Chart generate karne mein error: {e}")

    if REPORTLAB_AVAILABLE:
        try:
            doc = SimpleDocTemplate(pdf_path, pagesize=letter)
            elements = []
            styles = getSampleStyleSheet()
            
            title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=18, textColor=colors.HexColor('#1A237E'), spaceAfter=15, alignment=1)
            heading_style = ParagraphStyle('HeadingStyle', parent=styles['Heading2'], fontSize=13, textColor=colors.HexColor('#3F51B5'), spaceBefore=10, spaceAfter=5)
            normal_style = styles['Normal']
            
            elements.append(Paragraph("🎮 Facebook Gaming Agent - Advanced Analytics Report", title_style))
            elements.append(Paragraph(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", normal_style))
            elements.append(Spacer(1, 15))
            
            elements.append(Paragraph("🏆 Advanced Performance & Efficiency Leaderboard", heading_style))
            table_data = [["Rank", "Game Name", "Total Views", "Videos", "Avg/Video", "View Share"]]
            for idx, item in enumerate(sorted_analytics, 1):
                table_data.append([str(idx), item["game"], f"{item['total_views']:,}", str(item["uploaded_count"]), f"{item['avg_views']:,}", f"{item['share_pct']}%"])
                
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
            elements.append(Spacer(1, 15))
            
            if os.path.exists(chart_path):
                elements.append(Paragraph("📈 Advanced Performance & Efficiency Visuals", heading_style))
                elements.append(RLImage(chart_path, width=480, height=240))
                
            doc.build(elements)
        except Exception as e:
            log(f"⚠️ Advanced PDF Report generate karne mein error: {e}")
            
    return sorted_analytics


# 📊 PROFESSIONAL & ADVANCED ANALYTICS RECORDING FUNCTION (WITH ALL GAMES VIEWS SUMMARY)
def save_professional_history(game_name, target_file, chosen_style, streak_count, total_views, specific_uploaded_link, facebook_video_link, total_links, uploaded_links_count, remaining_links_count, next_game, next_link, game_views_summary, game_stats, reasoning=""):
    master_history_dir = "logs/professional_records"
    game_history_dir = "logs/game_specific_history"
    leaderboard_dir = "logs/leaderboard"
    os.makedirs(master_history_dir, exist_ok=True)
    os.makedirs(game_history_dir, exist_ok=True)
    os.makedirs(leaderboard_dir, exist_ok=True)
    
    master_csv = os.path.join(master_history_dir, "all_games_execution_history.csv")
    game_specific_csv = os.path.join(game_history_dir, f"{game_name}_video_history.csv")
    leaderboard_json = os.path.join(leaderboard_dir, "games_performance_leaderboard.json")
    leaderboard_csv = os.path.join(leaderboard_dir, "games_performance_leaderboard.csv")
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    saved_screenshot_path = "N/A"
    potential_ss = ["scrennshoot.jpg", "screenshot.jpg", "screnn_shoot.jpg"]
    found_ss = None
    for ss_name in potential_ss:
        if os.path.exists(ss_name):
            found_ss = ss_name
            break
            
    if found_ss:
        ss_folder = "logs/history_screenshots"
        os.makedirs(ss_folder, exist_ok=True)
        file_name = f"{game_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        saved_screenshot_path = os.path.join(ss_folder, file_name)
        try:
            shutil.copy(found_ss, saved_screenshot_path)
            # Game specific stats ma pan screenshot path save rakhva mate
            if game_name in game_stats:
                game_stats[game_name]["last_screenshot"] = saved_screenshot_path
        except Exception:
            pass

    # Convert all games views summary to formatted string for CSV logging
    all_games_views_str = json.dumps(game_views_summary)
    current_game_total_views = game_views_summary.get(game_name, 0)

    row_data = [
        timestamp, game_name, target_file, chosen_style, streak_count, 
        total_links, uploaded_links_count, remaining_links_count, facebook_video_link, 
        specific_uploaded_link, next_game, next_link, total_views, current_game_total_views, all_games_views_str, reasoning, saved_screenshot_path
    ]
    
    headers = [
        "Timestamp", "Game Name", "Target File", "Chosen Style", "Streak", 
        "Total Videos", "Uploaded Videos", "Remaining Videos", "Facebook Video Link", 
        "Uploaded Game Link", "Next Rotation Game", "Next Rotation Link", "Video Views", "Game Total Views", "All Games Total Views Summary", "AI Reasoning / Approve Reason", "Screenshot Path"
    ]

    for path in [master_csv, game_specific_csv]:
        file_exists = os.path.exists(path)
        try:
            with open(path, mode='a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(headers)
                writer.writerow(row_data)
        except Exception as e:
            log(f"⚠️ History save error on {path}: {e}")

    sorted_analytics = generate_visual_reports(game_views_summary, game_stats, game_name)
    
    try:
        with open(leaderboard_json, 'w', encoding='utf-8') as f:
            json.dump([
                {
                    "rank": i+1, 
                    "game_name": item["game"], 
                    "total_views": item["total_views"], 
                    "uploaded_videos": item["uploaded_count"],
                    "avg_views_per_video": item["avg_views"],
                    "view_share_percentage": item["share_pct"],
                    "last_screenshot": game_stats.get(item["game"], {}).get("last_screenshot", "N/A")
                } for i, item in enumerate(sorted_analytics)
            ], f, indent=4)
        
        with open(leaderboard_csv, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["Rank", "Game Name", "Total Accumulated Views", "Uploaded Videos", "Avg Views / Video", "View Share (%)", "Last Screenshot"])
            for i, item in enumerate(sorted_analytics):
                l_shot = game_stats.get(item["game"], {}).get("last_screenshot", "N/A")
                writer.writerow([i+1, item["game"], item["total_views"], item["uploaded_count"], item["avg_views"], f"{item['share_pct']}%", l_shot])
    except Exception as e:
        log(f"⚠️ Leaderboard save error: {e}")


def get_game_video_stats(target_file, memory, game_name):
    total_links = 0
    uploaded_links = 0
    
    if os.path.exists(target_file):
        try:
            with open(target_file, 'r', encoding='utf-8', errors='ignore') as f:
                lines = [line.strip() for line in f if line.strip()]
                total_links = len(lines)
        except Exception:
            pass
            
    game_stats = memory.get("game_stats", {})
    if game_name not in game_stats:
        game_stats[game_name] = {"uploaded_count": 0, "last_screenshot": "N/A"}
    
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
        style_history = memory.get("style_history", {})
        
        best_views = 7000
        winning_game = None
        winning_title = ""
        winning_video_id = ""
        winning_video_link = ""
        winning_video_views = 0
        highest_found = 0

        temp_game_views = {g: 0 for g in game_list}
        temp_game_counts = {g: 0 for g in game_list}
        temp_viral_counts = {g: 0 for g in game_list}

        style_total_views = {s: 0 for s in title_styles}
        style_counts = {s: 0 for s in title_styles}
        style_viral_hits = {s: 0 for s in title_styles}
        
        for video in data:
            video_id = video.get("id", "")
            title = video.get("title", "")
            description = video.get("description", "")
            permalink = video.get("permalink_url", f"https://www.facebook.com/{video_id}")
            text = (title + " " + description).lower()
            views = video.get("views", 0)
            
            if views > highest_found:
                highest_found = views
            
            used_style = style_history.get(video_id)
            if used_style in title_styles:
                style_total_views[used_style] += views
                style_counts[used_style] += 1
                if views >= 7000:
                    style_viral_hits[used_style] += 1

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
    archive_dir = "archived_links"
    memory_file = "logs/agent_memory.json"
    
    os.makedirs("logs", exist_ok=True)
    os.makedirs(archive_dir, exist_ok=True)
    
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
        "streak_game": "",
        "streak_count": 0,
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

    all_files = glob.glob(os.path.join(links_dir, "*.txt"))
    if not all_files:
        print(json.dumps({"error": "No files found"}))
        return

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
        print(json.dumps({"error": "No valid links left"}))
        return

    game_list = []
    file_mapping = {}
    for f in valid_game_files:
        g_name = os.path.basename(f).replace("_uploaded_links.txt", "").replace(".txt", "")
        file_mapping[g_name] = f
        
        _, _, rem_links, _ = get_game_video_stats(f, memory, g_name)
        if rem_links > 0:
            game_list.append(g_name)

    if not game_list:
        for f in valid_game_files:
            g_name = os.path.basename(f).replace("_uploaded_links.txt", "").replace(".txt", "")
            game_list.append(g_name)

    game_list.sort()

    high_perf_game, winning_title, current_video_id, current_video_link, current_video_views, game_views_summary, memory = fetch_and_calculate_scores(game_list, memory)
    
    processed_viral_ids = memory.get("processed_viral_ids", [])
    
    if current_video_id and current_video_id in processed_viral_ids:
        high_perf_game = None
        winning_title = ""
        current_video_id = ""
        current_video_link = ""
        current_video_views = 0

    stored_video_id = memory.get("winning_video_id", "")
    current_streak_count = memory.get("streak_count", 0)
    chosen_game = ""

    if high_perf_game and current_video_id and high_perf_game in game_list:
        if current_video_id != stored_video_id:
            current_streak_count = 1
            memory["winning_video_id"] = current_video_id
            memory["winning_video_link"] = current_video_link
            memory["winning_title_context"] = winning_title
            memory["winning_video_views"] = current_video_views
            memory["streak_game"] = high_perf_game
            memory["streak_count"] = current_streak_count
            chosen_game = high_perf_game
        elif current_streak_count < 2:
            current_streak_count += 1
            memory["streak_count"] = current_streak_count
            chosen_game = high_perf_game
            if current_streak_count >= 2:
                if current_video_id not in processed_viral_ids:
                    processed_viral_ids.append(current_video_id)
                memory["processed_viral_ids"] = processed_viral_ids
        else:
            memory["streak_game"] = ""
            memory["streak_count"] = 0
            memory["winning_title_context"] = ""
            memory["winning_video_id"] = ""
            memory["winning_video_link"] = ""
            memory["winning_video_views"] = 0
            
            last_game = memory.get("last_played_game", "")
            if last_game in game_list:
                next_index = (game_list.index(last_game) + 1) % len(game_list)
                chosen_game = game_list[next_index]
            else:
                chosen_game = game_list[0]
    else:
        memory["streak_game"] = ""
        memory["streak_count"] = 0
        last_game = memory.get("last_played_game", "")
        if last_game in game_list:
            next_index = (game_list.index(last_game) + 1) % len(game_list)
            chosen_game = game_list[next_index]
        else:
            chosen_game = game_list[0]

    winning_context = memory.get("winning_title_context", "None")
    recorded_views = memory.get("winning_video_views", 0)
    tracked_vid_link = memory.get("winning_video_link", "N/A")
    styles = memory.get("title_styles", {})
    
    style_names = list(styles.keys())
    style_weights = list(styles.values())
    chosen_style = random.choices(style_names, weights=style_weights, k=1)[0]
    ai_reasoning = "Default style selection approved."

    try:
        api_key = get_active_key()
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        
        prompt = f"""You are an advanced AI Social Media Manager.
Target Game: {chosen_game}
Selected Style: {chosen_style}
Reference Winning Title: "{winning_context}"

Respond ONLY in strict JSON format:
{{"chosen_game": "{chosen_game}", "chosen_style": "{chosen_style}", "reasoning": "Approved for high engagement"}}"""

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
                if parsed.get("chosen_style") in styles:
                    chosen_style = parsed.get("chosen_style")
                ai_reasoning = parsed.get("reasoning", "AI approved successfully")
    except Exception:
        pass

    target_file = file_mapping[chosen_game]
    total_links, uploaded_links, remaining_links, game_stats = get_game_video_stats(target_file, memory, chosen_game)
    
    specific_uploaded_link = "N/A"
    if os.path.exists(target_file):
        try:
            with open(target_file, 'r', encoding='utf-8', errors='ignore') as f:
                lines = [line.strip() for line in f if line.strip()]
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
                    next_lines = [line.strip() for line in f if line.strip()]
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

    # Save history including all games total views summary and screenshot path
    save_professional_history(
        game_name=chosen_game,
        target_file=target_file,
        chosen_style=chosen_style,
        streak_count=memory.get("streak_count", 0),
        total_views=recorded_views,
        specific_uploaded_link=specific_uploaded_link,
        facebook_video_link=tracked_vid_link,
        total_links=total_links,
        uploaded_links_count=uploaded_links,
        remaining_links_count=remaining_links,
        next_game=next_game,
        next_link=next_link,
        game_views_summary=game_views_summary,
        game_stats=memory.get("game_stats", {}),
        reasoning=ai_reasoning
    )

    current_game_total_views = game_views_summary.get(chosen_game, 0)
    saved_screenshot_logged = game_stats.get(chosen_game, {}).get("last_screenshot", "N/A")

    print(json.dumps({
        "target_file": target_file,
        "current_uploaded_game": chosen_game,
        "current_uploaded_link": specific_uploaded_link,
        "next_rotation_game": next_game,
        "next_rotation_link": next_link,
        "chosen_style": chosen_style,
        "facebook_video_link": tracked_vid_link,
        "total_videos": total_links,
        "uploaded_videos": uploaded_links,
        "remaining_videos": remaining_links,
        "selected_video_views": recorded_views,
        "current_game_total_views": current_game_total_views,
        "all_games_total_views_summary": game_views_summary,
        "saved_screenshot_path": saved_screenshot_logged,
        "approve_reason": ai_reasoning
    }, indent=4))

if __name__ == "__main__":
    run_agent_brain()