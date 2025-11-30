from flask import Flask, render_template, request, jsonify, send_file
import os
from dotenv import load_dotenv
from suno_api import SunoAPI

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

# SUNO API 클라이언트 초기화
suno_client = SunoAPI()

@app.route('/')
def index():
    return render_template('dashboard.html')

@app.route('/generate')
def generate():
    return render_template('generate.html')

@app.route('/library')
def library():
    return render_template('library.html')

@app.route('/api/generate', methods=['POST'])
def api_generate():
    """음악 생성 API 엔드포인트"""
    try:
        data = request.json

        # 필수 파라미터 확인
        if not data.get('prompt'):
            return jsonify({'error': 'Prompt is required'}), 400

        # SUNO API로 음악 생성 요청
        result = suno_client.generate_music(
            prompt=data['prompt'],
            duration=data.get('duration', 30),
            genre=data.get('genre'),
            mood=data.get('mood'),
            tempo=data.get('tempo')
        )

        if 'error' in result:
            return jsonify({'error': result['error']}), 500

        return jsonify({
            'status': 'success',
            'message': 'Music generation started',
            'data': result
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/songs', methods=['GET'])
def api_songs():
    """생성된 곡 목록 조회 API"""
    try:
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)

        songs = suno_client.get_songs(limit=limit, offset=offset)

        return jsonify({
            'status': 'success',
            'songs': songs,
            'total': len(songs)
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/songs/<song_id>', methods=['GET'])
def api_get_song(song_id):
    """특정 곡 정보 조회 API"""
    try:
        song = suno_client.get_song(song_id)

        if not song:
            return jsonify({'error': 'Song not found'}), 404

        return jsonify({
            'status': 'success',
            'song': song
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/songs/<song_id>', methods=['DELETE'])
def api_delete_song(song_id):
    """곡 삭제 API"""
    try:
        success = suno_client.delete_song(song_id)

        if not success:
            return jsonify({'error': 'Failed to delete song'}), 500

        return jsonify({
            'status': 'success',
            'message': 'Song deleted successfully'
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/songs/<song_id>/download', methods=['GET'])
def api_download_song(song_id):
    """곡 다운로드 API"""
    try:
        output_dir = os.path.join('static', 'audio')
        os.makedirs(output_dir, exist_ok=True)

        output_path = os.path.join(output_dir, f'{song_id}.mp3')

        success = suno_client.download_song(song_id, output_path)

        if not success:
            return jsonify({'error': 'Failed to download song'}), 500

        return send_file(output_path, as_attachment=True)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
