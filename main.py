from flask import Flask, render_template, request, jsonify, send_file, session, redirect, url_for
import os
import zipfile
import tempfile
from datetime import datetime
from io import BytesIO
from dotenv import load_dotenv
from suno_api import SunoAPI

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

def get_suno_client():
    """Get SUNO Bearer token from session and create client"""
    token = session.get('suno_token') or os.getenv('SUNO_BEARER_TOKEN')
    return SunoAPI(bearer_token=token)

@app.route('/')
def index():
    # Check authentication
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
            # Validate token
            client = SunoAPI(bearer_token=token)
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
    """Check authentication status"""
    client = get_suno_client()
    is_auth = client.is_authenticated()
    return jsonify({'authenticated': is_auth})

@app.route('/api/billing/info')
def api_billing_info():
    """Get credits and subscription info"""
    try:
        client = get_suno_client()
        if not client.is_authenticated():
            return jsonify({'error': 'Not authenticated'}), 401

        billing_info = client.get_billing_info()

        # Extract required information only
        return jsonify({
            'credits': billing_info.get('total_credits_left', 0),
            'monthly_limit': billing_info.get('monthly_limit', 0),
            'monthly_usage': billing_info.get('monthly_usage', 0),
            'plan_name': billing_info.get('plan', {}).get('name', 'Unknown'),
            'renews_on': billing_info.get('renews_on', '')
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/generate', methods=['POST'])
def api_generate():
    """Music generation API endpoint"""
    try:
        client = get_suno_client()
        if not client.is_authenticated():
            return jsonify({'error': 'Not authenticated'}), 401

        data = request.json

        # Check required parameters
        if not data.get('prompt'):
            return jsonify({'error': 'Prompt is required'}), 400

        # Generate tags (genre + mood)
        tags_parts = []
        if data.get('genre'):
            tags_parts.append(data['genre'])
        if data.get('mood'):
            tags_parts.append(data['mood'])
        tags = ', '.join(tags_parts) if tags_parts else ''

        # Request music generation via SUNO API
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
    """Get generated songs list API"""
    try:
        client = get_suno_client()
        if not client.is_authenticated():
            return jsonify({'error': 'Not authenticated'}), 401

        page = request.args.get('page', 0, type=int)

        result = client.get_songs(page=page)

        # Return response structure as is
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
    """Get specific song info API"""
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
    """Delete song API"""
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
    """Download song API"""
    try:
        client = get_suno_client()
        if not client.is_authenticated():
            return jsonify({'error': 'Not authenticated'}), 401

        # Get download folder path from environment variable (default: downloads)
        output_dir = os.getenv('DOWNLOAD_FOLDER', 'downloads')
        os.makedirs(output_dir, exist_ok=True)

        output_path = os.path.join(output_dir, f'{song_id}.mp3')

        success = client.download_song(song_id, output_path)

        if not success:
            return jsonify({'error': 'Failed to download song'}), 500

        return send_file(output_path, as_attachment=True)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/songs/batch-download', methods=['POST'])
def api_batch_download():
    """Batch download multiple songs as ZIP file API"""
    try:
        client = get_suno_client()
        if not client.is_authenticated():
            return jsonify({'error': 'Not authenticated'}), 401

        data = request.json
        song_ids = data.get('song_ids', [])

        if not song_ids:
            return jsonify({'error': 'No songs selected'}), 400

        # Create ZIP file in memory
        memory_zip = BytesIO()

        # Create temporary directory
        with tempfile.TemporaryDirectory() as temp_dir:
            # Download each song
            downloaded_files = []
            for song_id in song_ids:
                song = client.get_song(song_id)
                if not song:
                    continue

                # Generate filename (title + ID)
                title = song.get('title', 'Untitled').replace('/', '-').replace('\\', '-')
                filename = f"{title}_{song_id}.mp3"
                filepath = os.path.join(temp_dir, filename)

                # Download
                if client.download_song(song_id, filepath):
                    downloaded_files.append((filepath, filename))

            if not downloaded_files:
                return jsonify({'error': 'Failed to download any songs'}), 500

            # Create ZIP file (in memory)
            with zipfile.ZipFile(memory_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for filepath, filename in downloaded_files:
                    zipf.write(filepath, filename)

        # Prepare ZIP file for sending
        memory_zip.seek(0)
        date_str = datetime.now().strftime('%Y-%m-%d')
        zip_filename = f'suno-songs-{date_str}.zip'

        return send_file(
            memory_zip,
            mimetype='application/zip',
            as_attachment=True,
            download_name=zip_filename
        )

    except Exception as e:
        print(f"Batch download error: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('DEBUG', 'True').lower() in ('true', '1', 'yes')
    app.run(debug=debug, host='0.0.0.0', port=port)
