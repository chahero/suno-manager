import os
from pathlib import Path
import secrets
from datetime import datetime
from io import BytesIO
import json
import zipfile
from urllib.parse import urlparse

from dotenv import load_dotenv
from flask import Flask, g, jsonify, redirect, render_template, request, send_file, session, url_for
from werkzeug.exceptions import HTTPException

from suno_api import SunoAPI, SunoAPIError, download_filename, is_mp3, validate_song_id
from recording import PlaybackRecorder, RecordingError

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')
app = Flask(__name__)
app.config.update(SECRET_KEY=os.getenv('SECRET_KEY') or secrets.token_hex(32),
                  MAX_CONTENT_LENGTH=32 * 1024, SESSION_COOKIE_HTTPONLY=True,
                  SESSION_COOKIE_SAMESITE='Lax',
                  DOWNLOAD_FOLDER=str(ROOT / os.getenv('DOWNLOAD_FOLDER', 'downloads')))
# Local single-process app: browser cookies contain only a random reference.
# Tokens entered in the UI are discarded on logout or server restart.
app.config['SERVER_TOKENS'] = {}
app.config['PLAYBACK_RECORDER'] = PlaybackRecorder(Path(app.config['DOWNLOAD_FOLDER']) / 'recordings')


def get_suno_client():
    if 'suno_client' not in g:
        token = app.config['SERVER_TOKENS'].get(session.get('auth_id'))
        if token is None and not session.get('logged_out'):
            token = os.getenv('SUNO_BEARER_TOKEN', '')
        g.suno_client = SunoAPI(token or '')
    return g.suno_client


@app.teardown_appcontext
def close_client(_error):
    client = g.pop('suno_client', None)
    if client:
        client.close()


@app.errorhandler(SunoAPIError)
def api_error(error):
    return jsonify(error=str(error), code=error.code), error.status_code


@app.errorhandler(RecordingError)
def recording_error(error):
    return jsonify(error=str(error), code='recording_error'), error.status_code


@app.errorhandler(ValueError)
def invalid_input(error):
    return jsonify(error=str(error), code='invalid_input'), 400


@app.errorhandler(Exception)
def unexpected_error(error):
    if isinstance(error, HTTPException):
        return error
    # Never expose exceptions that may contain tokens or signed URLs.
    app.logger.error('Request failed: %s', type(error).__name__)
    return jsonify(error='요청 처리에 실패했습니다. 서버 설정과 저장 경로를 확인해 주세요.'), 500


def json_body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError('JSON 객체가 필요합니다.')
    if 'unlock' in data and not isinstance(data['unlock'], bool):
        raise ValueError('unlock은 true 또는 false여야 합니다.')
    return data


def song_or_404(client, song_id):
    song = client.get_song(validate_song_id(song_id))
    if not song:
        raise SunoAPIError('곡을 찾을 수 없습니다.', 404, 'not_found')
    return song


def song_view(song):
    song = dict(song)
    song_id = validate_song_id(song['id'])
    cached = Path(app.config['DOWNLOAD_FOLDER']) / f'{song_id}.mp3'
    song['local_audio_url'] = url_for('api_audio', song_id=song_id) if is_mp3(cached) else None
    song['suno_url'] = f'https://suno.com/song/{song_id}'
    return song


def page(template):
    if not get_suno_client().bearer_token:
        return redirect(url_for('login'))
    return render_template(template)


@app.route('/')
def index():
    return page('dashboard.html')


@app.route('/library')
def library():
    return render_template('library.html')


@app.route('/record')
def record():
    song_id = request.args.get('song_id')
    return redirect(url_for('library', record=validate_song_id(song_id)) if song_id else url_for('library'))


def recorder():
    return app.config['PLAYBACK_RECORDER']


@app.before_request
def require_local_recording():
    if request.path.startswith('/api/recordings') or request.endpoint in {'api_local_songs', 'api_audio'}:
        local_hosts = {'localhost', '127.0.0.1', '::1'}
        if urlparse(request.host_url).hostname not in local_hosts or request.remote_addr not in {'127.0.0.1', '::1'}:
            raise RecordingError('녹음 기능은 이 컴퓨터의 localhost 앱에서만 사용할 수 있습니다.', 403)


@app.route('/api/recordings/devices')
def api_recording_devices():
    return jsonify(devices=recorder().devices())


@app.route('/api/recordings/status')
def api_recording_status():
    return jsonify(recorder().status())


@app.route('/api/recordings')
def api_recordings():
    items = recorder().recordings()
    song_id = request.args.get('song_id')
    if song_id:
        song_id = validate_song_id(song_id)
        items = [item for item in items if item.get('song_id') == song_id]
    return jsonify(recordings=items)


@app.route('/api/recordings/start', methods=['POST'])
def api_recording_start():
    data = json_body()
    # Stop cross-origin pages from triggering local audio capture.
    origin = request.headers.get('Origin')
    if origin and origin != request.host_url.rstrip('/'):
        raise RecordingError('현재 앱 화면에서 녹음을 시작해 주세요.', 403)
    options = {'song_id': data.get('song_id')}
    if 'auto_playback' in data:
        options['auto_playback'] = data['auto_playback']
    return jsonify(recorder().start(data.get('device_id'), data.get('title', 'Recording'),
                                   data.get('duration', 0), **options)), 202


@app.route('/api/recordings/<job_id>/stop', methods=['POST'])
def api_recording_stop(job_id):
    json_body()
    origin = request.headers.get('Origin')
    if origin and origin != request.host_url.rstrip('/'):
        raise RecordingError('현재 앱 화면에서 녹음을 정지해 주세요.', 403)
    return jsonify(recorder().stop(job_id)), 202


@app.route('/api/recordings/<job_id>/audio')
@app.route('/api/recordings/<job_id>/download')
def api_recording_file(job_id):
    path, info = recorder().file(job_id)
    return send_file(path, mimetype='audio/wav', conditional=True,
                     as_attachment=request.path.endswith('/download'), download_name=info['filename'])


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = json_body() if request.is_json else request.form
        token = data.get('token', '')
        if not isinstance(token, str) or not token.strip():
            raise ValueError('Suno 토큰을 입력해 주세요.')
        client = SunoAPI(token)
        try:
            if not client.is_authenticated():
                raise SunoAPIError('토큰이 만료되었거나 유효하지 않습니다.', 401, 'unauthorized')
            app.config['SERVER_TOKENS'].pop(session.get('auth_id'), None)
            session.clear()
            auth_id = secrets.token_urlsafe(32)
            app.config['SERVER_TOKENS'][auth_id] = client.bearer_token
            session['auth_id'] = auth_id
        finally:
            client.close()
        return jsonify(status='success') if request.is_json else redirect(url_for('index'))
    return render_template('login.html')


@app.route('/logout')
def logout():
    app.config['SERVER_TOKENS'].pop(session.get('auth_id'), None)
    session.clear()
    session['logged_out'] = True
    return redirect(url_for('login'))


@app.route('/api/auth/check')
def api_auth_check():
    authenticated = get_suno_client().is_authenticated()
    return jsonify(authenticated=authenticated), 200 if authenticated else 401


@app.route('/api/billing/info')
def api_billing_info():
    data = get_suno_client().get_billing_info()
    usage = data.get('download_usage') or {}
    limit = usage.get('current_period_downloads_limit')
    used = usage.get('current_period_downloads_used')
    extra = usage.get('additional_download_remaining')
    remaining = max(0, limit - used) + extra if all(isinstance(x, int) for x in (limit, used, extra)) else None
    return jsonify(credits=data.get('total_credits_left'), monthly_limit=data.get('monthly_limit'),
                   plan_name=(data.get('plan') or {}).get('name', 'Unknown'),
                   downloads_remaining=remaining, download_usage=usage)


@app.route('/api/songs')
def api_songs():
    data = get_suno_client().get_songs(request.args.get('cursor'))
    return jsonify(status='success', clips=[song_view(song) for song in data['clips']],
                   has_more=bool(data.get('has_more')), next_cursor=data.get('next_cursor'))


@app.route('/api/songs/local')
def api_local_songs():
    # Keep recorded/cached songs usable when the short-lived Suno token expires.
    items = {}
    for recording in recorder().recordings():
        try:
            song_id = validate_song_id(recording.get('song_id'))
        except ValueError:
            continue
        if song_id not in items:
            items[song_id] = {'id': song_id, 'title': recording.get('title') or '보관한 곡',
                              'created_at': recording.get('created_at', ''),
                              'metadata': {'tags': '로컬 녹음 보관곡'}, 'offline': True}
    for path in Path(app.config['DOWNLOAD_FOLDER']).glob('*.mp3'):
        try:
            song_id = validate_song_id(path.stem)
        except ValueError:
            continue
        if is_mp3(path) and song_id not in items:
            items[song_id] = {'id': song_id, 'title': '보관한 곡 ' + song_id[:8],
                              'created_at': '', 'metadata': {'tags': '로컬 MP3 보관곡'}, 'offline': True}
    return jsonify(clips=[song_view(song) for song in items.values()], has_more=False)


@app.route('/api/songs/<song_id>')
def api_get_song(song_id):
    return jsonify(status='success', song=song_view(song_or_404(get_suno_client(), song_id)))


@app.route('/api/songs/<song_id>/download', methods=['GET', 'POST'])
def api_download_song(song_id):
    data = json_body() if request.method == 'POST' else {}
    client = get_suno_client()
    song = song_or_404(client, song_id)
    path = Path(app.config['DOWNLOAD_FOLDER']) / f"{song['id']}.mp3"
    client.download_song(song['id'], str(path), unlock=data.get('unlock', False))
    return send_file(path, as_attachment=True, download_name=download_filename(song), mimetype='audio/mpeg')


@app.route('/api/songs/<song_id>/audio')
def api_audio(song_id):
    path = Path(app.config['DOWNLOAD_FOLDER']) / f'{validate_song_id(song_id)}.mp3'
    if not is_mp3(path):
        raise SunoAPIError('먼저 MP3를 다운로드해 주세요. 다운로드 승인 없이 재생하려면 Suno에서 열어 주세요.', 404, 'audio_not_cached')
    return send_file(path, mimetype='audio/mpeg', conditional=True)


@app.route('/api/songs/batch-download', methods=['POST'])
def api_batch_download():
    data = json_body()
    song_ids = data.get('song_ids')
    if not isinstance(song_ids, list) or not 1 <= len(song_ids) <= 50:
        raise ValueError('한 번에 1~50곡을 선택해 주세요.')
    song_ids = list(dict.fromkeys(validate_song_id(song_id) for song_id in song_ids))
    client, downloaded, failed = get_suno_client(), [], []
    memory_zip = BytesIO()
    with zipfile.ZipFile(memory_zip, 'w', zipfile.ZIP_STORED) as archive:
        for song_id in song_ids:
            try:
                song = song_or_404(client, song_id)
                path = Path(app.config['DOWNLOAD_FOLDER']) / f'{song_id}.mp3'
                client.download_song(song_id, str(path), unlock=data.get('unlock', False))
                filename = download_filename(song)
                archive.write(path, filename)
                downloaded.append({'id': song_id, 'file': filename})
            except SunoAPIError as error:
                if error.status_code == 401:
                    raise
                failed.append({'id': song_id, 'code': error.code, 'error': str(error)})
                if error.code == 'authorization_uncertain':
                    # Stop further quota-consuming operations after an ambiguous approval.
                    for skipped in song_ids[song_ids.index(song_id) + 1:]:
                        failed.append({'id': skipped, 'code': 'not_attempted', 'error': '이전 승인 결과가 불명확하여 중단했습니다.'})
                    break
        if not downloaded:
            return jsonify(error='다운로드된 곡이 없습니다.', failed=failed), 409
        archive.writestr('download-results.json', json.dumps({'downloaded': downloaded, 'failed': failed}, ensure_ascii=False, indent=2))
    memory_zip.seek(0)
    response = send_file(memory_zip, mimetype='application/zip', as_attachment=True,
                         download_name=f'suno-songs-{datetime.now():%Y-%m-%d}.zip')
    response.headers['X-Downloaded-Count'] = str(len(downloaded))
    response.headers['X-Failed-Count'] = str(len(failed))
    return response


if __name__ == '__main__':
    # This app holds a personal token; keep it local by default.
    app.run(host=os.getenv('HOST', '127.0.0.1'), port=int(os.getenv('PORT', '5000')),
            debug=os.getenv('DEBUG', 'false').lower() in ('true', '1', 'yes'))
