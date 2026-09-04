import os
import json
import requests

def fetch_and_update_real_insights():
    memory_file = 'logs/agent_memory.json'
    posted_dir = 'posted_links_editor'
    
    if not os.path.exists(memory_file):
        return

    with open(memory_file, 'r', encoding='utf-8') as f:
        memory = json.load(f)

    page_token = os.environ.get("PAGE_ACCESS_TOKEN")
    if not page_token:
        return

    for filename in os.listdir(posted_dir):
        if filename.endswith('_posted_links_editor.txt'):
            game_name = filename.replace('_posted_links_editor.txt', '')
            filepath = os.path.join(posted_dir, filename)
            
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            blocks = content.split('\n\n')
            for block in blocks:
                if 'Video id :' in block:
                    vid_id = block.split('Video id :')[-1].strip()
                    insights_url = f"https://graph.facebook.com/v24.0/{vid_id}/video_insights?access_token={page_token}"
                    try:
                        res = requests.get(insights_url, timeout=10).json()
                        views = 0
                        for metric in res.get('data', []):
                            if metric.get('name') == 'total_video_views':
                                values = metric.get('values', [{}])
                                views = values[0].get('value', 0)
                        
                        if views > 5000:
                            memory['game_scores'][game_name] = memory['game_scores'].get(game_name, 10) + 10
                        elif views > 1000:
                            memory['game_scores'][game_name] = memory['game_scores'].get(game_name, 10) + 5
                        elif views < 100:
                            memory['game_scores'][game_name] = max(5, memory['game_scores'].get(game_name, 10) - 2)
                    except Exception:
                        pass

    with open(memory_file, 'w', encoding='utf-8') as f:
        json.dump(memory, f, indent=4)
    print("📊 Real Facebook Insights fetched & AI memory updated successfully!")

if __name__ == "__main__":
    fetch_and_update_real_insights()
