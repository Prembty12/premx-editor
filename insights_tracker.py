import os
import json
import time
import requests
from datetime import datetime

def fetch_and_update_real_insights():
    memory_file = 'logs/agent_memory.json'
    posted_dir = 'posted_links_editor'
    dashboard_file = 'GAMING_DASHBOARD.md'
    
    if not os.path.exists(memory_file):
        print("❌ Memory file not found!")
        return

    with open(memory_file, 'r', encoding='utf-8') as f:
        memory = json.load(f)
    
    memory.setdefault('game_scores', {})
    page_token = os.environ.get("PAGE_ACCESS_TOKEN")
    
    if not page_token:
        print("❌ PAGE_ACCESS_TOKEN missing!")
        return

    dashboard_data = []

    # Har file ko process karo
    for filename in os.listdir(posted_dir):
        if filename.endswith('_posted_links_editor.txt'):
            game_name = filename.replace('_posted_links_editor.txt', '')
            filepath = os.path.join(posted_dir, filename)
            
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # Line by line process karo (taaki multiple videos handle ho)
            lines = content.split('\n')
            posts = []
            current_video = {}
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # Agar line mein "Link:" hai to naya video shuru
                if '| Link:' in line:
                    # Agar pehle se koi video pending hai to save karo
                    if current_video.get('vid_id'):
                        posts.append(current_video)
                    
                    # Naya video object banao
                    title_part = line.split('| Link:')[0].strip()
                    current_video = {
                        'title': title_part,
                        'vid_id': None
                    }
                
                # Video ID line
                elif 'Video id :' in line:
                    vid_id = line.split('Video id :')[-1].strip()
                    current_video['vid_id'] = vid_id
                
                # Agar Title line mil jaye to use karo
                elif 'Title :' in line:
                    current_video['title'] = line.split('Title :')[-1].strip()
            
            # Last video ko bhi add karo
            if current_video.get('vid_id'):
                posts.append(current_video)
            
            # Ab har video ka insights fetch karo
            for post in posts:
                vid_id = post['vid_id']
                title = post.get('title', 'Untitled')
                
                insights_url = f"https://graph.facebook.com/v24.0/{vid_id}/video_insights?access_token={page_token}"
                
                views = 0
                for attempt in range(3):
                    try:
                        res = requests.get(insights_url, timeout=10).json()
                        for metric in res.get('data', []):
                            if metric.get('name') == 'total_video_views':
                                views = metric.get('values', [{}])[0].get('value', 0)
                        if views > 0:
                            break
                    except Exception as e:
                        print(f"⚠️ Error fetching {vid_id}: {e}")
                    time.sleep(5)
                
                # AI Memory update karo
                if views > 5000:
                    memory['game_scores'][game_name] = memory['game_scores'].get(game_name, 10) + 10
                elif views > 1000:
                    memory['game_scores'][game_name] = memory['game_scores'].get(game_name, 10) + 5
                elif 0 < views < 100:
                    memory['game_scores'][game_name] = max(5, memory['game_scores'].get(game_name, 10) - 2)
                
                status = "✅ Live" if views > 0 else "⏳ Pending"
                post['views'] = views
                post['status'] = status
                post['title'] = title
            
            if posts:
                dashboard_data.append({'game': game_name, 'posts': posts})

    # Save memory
    os.makedirs('logs', exist_ok=True)
    with open(memory_file, 'w', encoding='utf-8') as f:
        json.dump(memory, f, indent=4)

    # Dashboard generate karo
    lines = ["# 🎮 GAMING AGENT COMMAND & ANALYTICS DASHBOARD\n"]
    lines.append(f"**Last Updated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Status: All Systems Active\n")
    lines.append("---\n")
    
    for data in dashboard_data:
        game = data['game']
        posts = data['posts']
        total_views = sum(p.get('views', 0) for p in posts)
        avg_views = total_views // len(posts) if posts else 0
        tier = "🔥 Hot" if avg_views > 5000 else "✅ Stable"
        
        lines.append(f"\n## 🎮 {game} — Upload History ({len(posts)} posts)\n")
        lines.append(f"**📊 Total Views:** {total_views} | **Avg:** {avg_views} | **Tier:** {tier}\n")
        lines.append("| # | Timestamp | Live Title | Views | Status |")
        lines.append("|---|-----------|------------|-------|--------|")
        
        for i, p in enumerate(posts, 1):
            ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            lines.append(f"| {i} | {ts} | {p.get('title', 'Untitled')} | {p.get('views', 0)} | {p.get('status', 'Pending')} |")
    
    with open(dashboard_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    
    print(f"📊 Insights fetched & Dashboard updated! Total games: {len(dashboard_data)}")

if __name__ == "__main__":
    fetch_and_update_real_insights()
