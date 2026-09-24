import os
import json
import time
import requests
from datetime import datetime

def fetch_fb_caption(vid_id, page_token):
    """Facebook API se caption fetch karo"""
    url = f"https://graph.facebook.com/v24.0/{vid_id}?fields=description&access_token={page_token}"
    try:
        res = requests.get(url, timeout=10).json()
        caption = res.get('description', '').strip()
        if caption:
            return caption.split('\n')[0].strip()
    except Exception as e:
        print(f"⚠️ Caption error {vid_id}: {e}")
    return None

def fetch_fb_views(vid_id, page_token):
    """Facebook API se views fetch karo (Instagram ignore)"""
    url = f"https://graph.facebook.com/v24.0/{vid_id}/video_insights?access_token={page_token}"
    views = 0
    for attempt in range(3):
        try:
            res = requests.get(url, timeout=10).json()
            for metric in res.get('data', []):
                if metric.get('name') == 'total_video_views':
                    values = metric.get('values', [{}])
                    views = values[0].get('value', 0)
            if views > 0:
                break
        except Exception as e:
            print(f"⚠️ Insights error {vid_id}: {e}")
        time.sleep(5)
    return views

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

    for filename in os.listdir(posted_dir):
        if filename.endswith('_posted_links_editor.txt'):
            game_name = filename.replace('_posted_links_editor.txt', '')
            filepath = os.path.join(posted_dir, filename)
            
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
                        'vid_id': None,
                        'title': None,
                        'link': link_part,
                        'video_name': video_name,
                        'platform': 'FB + IG'
                    }
                
                elif 'Video id :' in line:
                    vid_id = line.split('Video id :')[-1].strip()
                    current_video['vid_id'] = vid_id
                
                elif 'Title :' in line:
                    current_video['title'] = line.split('Title :')[-1].strip()
            
            if current_video.get('vid_id'):
                posts.append(current_video)
            
            for post in posts:
                vid_id = post['vid_id']
                
                fb_caption = fetch_fb_caption(vid_id, page_token)
                fb_views = fetch_fb_views(vid_id, page_token)
                
                if fb_caption:
                    title = fb_caption
                elif post.get('title'):
                    title = post['title']
                else:
                    title = post.get('video_name', '').replace('_', ' ').strip()
                    if not title:
                        title = f"Video {vid_id[:8]}"
                
                if fb_views > 5000:
                    memory['game_scores'][game_name] = memory['game_scores'].get(game_name, 10) + 10
                elif fb_views > 1000:
                    memory['game_scores'][game_name] = memory['game_scores'].get(game_name, 10) + 5
                elif 0 < fb_views < 100:
                    memory['game_scores'][game_name] = max(5, memory['game_scores'].get(game_name, 10) - 2)
                
                status = "✅ Live" if fb_views > 0 else "⏳ Pending"
                
                post['views'] = fb_views
                post['status'] = status
                post['title'] = title
                
                time.sleep(2)
            
            if posts:
                dashboard_data.append({'game': game_name, 'posts': posts})

    os.makedirs('logs', exist_ok=True)
    with open(memory_file, 'w', encoding='utf-8') as f:
        json.dump(memory, f, indent=4)

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
        lines.append(f"**📊 Total FB Views:** {total_views} | **Avg:** {avg_views} | **Tier:** {tier}\n")
        lines.append("| # | Timestamp | Live Title | Link | Platform | FB Views | Status |")
        lines.append("|---|-----------|------------|------|----------|----------|--------|")
        
        for i, p in enumerate(posts, 1):
            ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            link = p.get('link', 'N/A')
            platform = p.get('platform', 'FB + IG')
            lines.append(f"| {i} | {ts} | {p.get('title', 'Untitled')} | [Link]({link}) | {platform} | {p.get('views', 0)} | {p.get('status', 'Pending')} |")
    
    with open(dashboard_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    
    print(f"📊 FB data fetched & Dashboard updated! Games: {len(dashboard_data)}")

if __name__ == "__main__":
    fetch_and_update_real_insights()
