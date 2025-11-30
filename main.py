from flask import Flask, render_template, request, jsonify, send_file, session, redirect, url_for
import os
from dotenv import load_dotenv
from suno_api import SunoAPI

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

def get_suno_client():
    """세션에서 SUNO 토큰을 가져와 클라이언트 생성"""
    token = session.get('suno_token') or os.getenv('SUNO_SESSION_TOKEN')
    return SunoAPI(session_token=token)

@app.route('/')
def index():
    # 인증 확인
    client = get_suno_client()
    if not client.is_authenticated():
        return redirect(url_for('login'))
    return render_template('dashboard.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form
        token = data.get('token')

        if token:
            # 토큰 유효성 검사
            client = SunoAPI(session_token=token)
            if client.is_authenticated():
                session['suno_token'] = token
                if request.is_json:
                    return jsonify({'status': 'success'})
                return redirect(url_for('index'))
            else:
                if request.is_json:
                    return jsonify({'error': 'Invalid token'}), 401
                return render_template('login.html', error='Invalid token')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('suno_token', None)
    return redirect(url_for('login'))

@app.route('/generate')
def generate():
    client = get_suno_client()
    if not client.is_authenticated():
        return redirect(url_for('login'))
    return render_template('generate.html')

@app.route('/library')
def library():
    client = get_suno_client()
    if not client.is_authenticated():
        return redirect(url_for('login'))
    return render_template('library.html')

@app.route('/api/auth/check')
def api_auth_check():
    """인증 상태 확인"""
    client = get_suno_client()
    is_auth = client.is_authenticated()
    return jsonify({'authenticated': is_auth})

@app.route('/api/generate', methods=['POST'])
def api_generate():
    """음악 생성 API 엔드포인트"""
    try:
        client = get_suno_client()
        if not client.is_authenticated():
            return jsonify({'error': 'Not authenticated'}), 401

        data = request.json

        # 필수 파라미터 확인
        if not data.get('prompt'):
            return jsonify({'error': 'Prompt is required'}), 400

        # 태그 생성 (genre + mood)
        tags_parts = []
        if data.get('genre'):
            tags_parts.append(data['genre'])
        if data.get('mood'):
            tags_parts.append(data['mood'])
        tags = ', '.join(tags_parts) if tags_parts else ''

        # SUNO API로 음악 생성 요청
        result = client.generate_music(
            prompt=data['prompt'],
            tags=tags,
            instrumental=data.get('instrumental', False)
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
        client = get_suno_client()
        if not client.is_authenticated():
            return jsonify({'error': 'Not authenticated'}), 401

        page = request.args.get('page', 0, type=int)

        result = client.get_songs(page=page)

        # 응답 구조 그대로 반환
        return jsonify({
            'status': 'success',
            'clips': result.get('clips', []),
            'num_total_results': result.get('num_total_results', 0),
            'current_page': result.get('current_page', 0),
            'has_more': result.get('has_more', False)
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/songs/<song_id>', methods=['GET'])
def api_get_song(song_id):
    """특정 곡 정보 조회 API"""
    try:
        client = get_suno_client()
        if not client.is_authenticated():
            return jsonify({'error': 'Not authenticated'}), 401

        song = client.get_song(song_id)

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
        client = get_suno_client()
        if not client.is_authenticated():
            return jsonify({'error': 'Not authenticated'}), 401

        success = client.delete_song(song_id)

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
        client = get_suno_client()
        if not client.is_authenticated():
            return jsonify({'error': 'Not authenticated'}), 401

        output_dir = os.path.join('static', 'audio')
        os.makedirs(output_dir, exist_ok=True)

        output_path = os.path.join(output_dir, f'{song_id}.mp3')

        success = client.download_song(song_id, output_path)

        if not success:
            return jsonify({'error': 'Failed to download song'}), 500

        return send_file(output_path, as_attachment=True)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
