from flask import Flask, request, jsonify
import yt_dlp

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
        ydl_opts = {
            'format': 'best',
            'noplaylist': True,
            'extractor_args': {'youtube': {'player_client': ['web']}}
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(yt_url, download=False)
            
            formats = []
            for f in info.get('formats', []):
                if f.get('url'):
                    formats.append({
                        'format_id': f.get('format_id'),
                        'resolution': f.get('format_note') or f.get('resolution'),
                        'url': f.get('url')
                    })

            return jsonify({
                "title": info.get('title'),
                "thumbnail": info.get('thumbnail'),
                "duration": info.get('duration'),
                "formats": formats
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
