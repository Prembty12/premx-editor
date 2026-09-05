from flask import Flask, request, jsonify
import subprocess
import json

app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({"status": "Running", "usage": "Use /download?url=YOUR_YOUTUBE_LINK"})

@app.route('/download', methods=['GET'])
def download():
    yt_url = request.args.get('url')
    if not yt_url:
        return jsonify({"error": "Missing URL parameter"}), 400

    try:
        # yt-dlp command to extract direct stream URLs in JSON format
        command = ['yt-dlp', '-j', yt_url]
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)

        # Extracting useful info
        formats = []
        for f in data.get('formats', []):
            if f.get('url') and f.get('ext') == 'mp4':
                formats.append({
                    'format_id': f.get('format_id'),
                    'resolution': f.get('format_note') or f.get('resolution'),
                    'url': f.get('url')
                })

        return jsonify({
            "title": data.get('title'),
            "thumbnail": data.get('thumbnail'),
            "duration": data.get('duration'),
            "formats": formats
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
