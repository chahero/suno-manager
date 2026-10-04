"""Small client for Suno's current web API (not a public, stable API)."""

import base64
import json
import os
from pathlib import Path
import re
import tempfile
import time
from typing import Dict, List, Optional
from urllib.parse import urlparse
import uuid

import requests

DEVICE_ID = os.getenv('SUNO_DEVICE_ID') or str(uuid.uuid4())


class SunoAPIError(Exception):
    def __init__(self, message, status_code=502, code='upstream_error'):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


def validate_song_id(song_id: str) -> str:
    try:
        return str(uuid.UUID(song_id))
    except (ValueError, TypeError, AttributeError):
        raise ValueError('올바른 곡 ID(UUID)가 필요합니다.') from None


def download_filename(song: Dict) -> str:
    title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '-', str(song.get('title') or 'Untitled'))
    title = title.strip(' .')[:80] or 'Untitled'
    return f"{title}_{validate_song_id(song['id'])}.mp3"


def is_mp3(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size < 128:
        return False
    with path.open('rb') as file:
        head = file.read(3)
    return head.startswith(b'ID3') or (len(head) >= 2 and head[0] == 0xff and head[1] & 0xe0 == 0xe0)


class SunoAPI:
    def __init__(self, bearer_token: Optional[str] = None):
        token = bearer_token if bearer_token is not None else os.getenv('SUNO_BEARER_TOKEN', '')
        self.bearer_token = re.sub(r'^Bearer\s+', '', token.strip(), flags=re.I)
        self.base_url = 'https://studio-api.prod.suno.com/api'
        self.session = requests.Session()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            # Only advertise codecs actually installed in requests.
            'Accept-Encoding': requests.utils.default_headers()['Accept-Encoding'],
            'Authorization': f'Bearer {self.bearer_token}',
            'device-id': os.getenv('SUNO_DEVICE_ID') or DEVICE_ID,
            'Origin': 'https://suno.com',
            'Referer': 'https://suno.com/',
        }

    def close(self):
        self.session.close()

    def _get_browser_token(self) -> str:
        raw = json.dumps({'timestamp': int(time.time() * 1000)}, separators=(',', ':'))
        encoded = base64.b64encode(raw.encode()).decode().rstrip('=')
        return json.dumps({'token': encoded}, separators=(',', ':'))

    def _request(self, method: str, endpoint: str, *, mutation=False, **kwargs) -> Dict:
        if not self.bearer_token:
            raise SunoAPIError('Suno 토큰을 설정하거나 로그인해 주세요.', 401, 'unauthorized')
        headers = {**self.headers, 'browser-token': self._get_browser_token()}
        # No automatic retries or redirects: authorization can consume a download.
        try:
            response = self.session.request(method, self.base_url + endpoint,
                                            headers=headers, timeout=(10, 30),
                                            allow_redirects=False, **kwargs)
        except requests.RequestException:
            if mutation:
                raise self._uncertain_authorization() from None
            raise SunoAPIError('Suno 연결에 실패했습니다. 잠시 후 다시 시도해 주세요.', 502, 'connection_failed') from None
        try:
            if response.status_code == 401:
                raise SunoAPIError('Suno 토큰이 만료되었거나 유효하지 않습니다. 새 토큰으로 로그인해 주세요.', 401, 'unauthorized')
            if response.status_code == 404:
                raise SunoAPIError('곡을 찾을 수 없습니다.', 404, 'not_found')
            if mutation and (300 <= response.status_code < 400 or response.status_code >= 500):
                raise self._uncertain_authorization()
            if not 200 <= response.status_code < 300:
                status = response.status_code if response.status_code in (403, 409, 429) else 502
                raise SunoAPIError(f'Suno 요청이 거절되었습니다 (HTTP {response.status_code}).', status, 'request_denied')
            try:
                data = response.json()
            except ValueError:
                if mutation:
                    raise self._uncertain_authorization() from None
                raise SunoAPIError('Suno 응답을 읽을 수 없습니다.', 502, 'invalid_response') from None
            if not isinstance(data, dict):
                if mutation:
                    raise self._uncertain_authorization()
                raise SunoAPIError('Suno 응답 형식이 변경되었습니다.', 502, 'invalid_response')
            return data
        finally:
            response.close()

    @staticmethod
    def _uncertain_authorization():
        return SunoAPIError('다운로드 승인 결과를 확인하지 못했습니다. 자동 재시도하지 않았습니다. 곡의 잠금 해제 상태와 사용량을 새로 조회한 뒤 다시 시도해 주세요.',
                            502, 'authorization_uncertain')

    def get_songs(self, cursor: Optional[str] = None) -> Dict:
        data = self._request('POST', '/feed/v3', json={'cursor': cursor} if cursor else {})
        if not isinstance(data.get('clips'), list):
            raise SunoAPIError('Suno 곡 목록 응답 형식이 변경되었습니다.', 502, 'invalid_response')
        if data.get('has_more') and not data.get('next_cursor'):
            raise SunoAPIError('Suno가 다음 페이지 커서를 반환하지 않았습니다.', 502, 'invalid_pagination')
        return data

    def get_all_songs(self) -> List[Dict]:
        songs, seen_ids, seen_cursors = [], set(), set()
        cursor = None
        while True:
            data = self.get_songs(cursor)
            for song in data['clips']:
                if song.get('id') and song['id'] not in seen_ids:
                    seen_ids.add(song['id'])
                    songs.append(song)
            if not data.get('has_more'):
                return songs
            cursor = data['next_cursor']
            if cursor in seen_cursors:
                raise SunoAPIError('Suno가 동일한 페이지를 반복해서 반환했습니다.', 502, 'invalid_pagination')
            seen_cursors.add(cursor)

    def get_song(self, song_id: str) -> Optional[Dict]:
        song_id = validate_song_id(song_id)
        try:
            song = self._request('GET', f'/clip/{song_id}')
        except SunoAPIError as error:
            if error.status_code == 404:
                return None
            raise
        if song.get('id') != song_id:
            raise SunoAPIError('Suno 곡 정보 응답 형식이 변경되었습니다.', 502, 'invalid_response')
        return song

    def is_authenticated(self) -> bool:
        if not self.bearer_token:
            return False
        try:
            self.get_songs()
            return True
        except SunoAPIError as error:
            if error.status_code == 401:
                return False
            raise

    def get_billing_info(self) -> Dict:
        return self._request('GET', '/billing/info/')

    def authorize_download(self, song_id: str):
        data = self._request('POST', '/download/authorize', mutation=True,
                             json={'item_id': validate_song_id(song_id), 'item_type': 'clip'})
        if data.get('ok') is True:
            return
        if data.get('ok') is not False:
            raise self._uncertain_authorization()
        reason = str(data.get('reason') or '')
        raise SunoAPIError('다운로드 승인이 거절되었습니다. 계정의 다운로드 한도와 곡 권한을 확인해 주세요.',
                           403, reason if reason in ('rate_limited', 'insufficient_credits') else 'authorization_denied')

    def _prepared_download_url(self, song_id: str, wait_seconds=60) -> str:
        deadline = time.monotonic() + wait_seconds
        while True:
            data = self._request('GET', f'/download/clip/{song_id}', params={'format': 'mp3'})
            if data.get('ok') is not True or data.get('status') == 'error':
                raise SunoAPIError('Suno가 MP3 파일을 준비하지 못했습니다. 잠금 해제 상태와 다운로드 한도를 확인해 주세요.', 409, 'download_not_ready')
            if data.get('status') == 'ready':
                url = data.get('download_url')
                if isinstance(url, str) and urlparse(url).scheme == 'https' and urlparse(url).hostname:
                    return url
                raise SunoAPIError('Suno 다운로드 주소가 올바르지 않습니다.', 502, 'invalid_response')
            if data.get('status') != 'processing':
                raise SunoAPIError('Suno 다운로드 응답 형식이 변경되었습니다.', 502, 'invalid_response')
            if time.monotonic() >= deadline:
                raise SunoAPIError('MP3 준비가 지연되고 있습니다. 잠시 후 다시 다운로드해 주세요.', 504, 'download_timeout')
            time.sleep(2)

    def download_song(self, song_id: str, output_path: str, song_info: Optional[Dict] = None,
                      *, unlock=False) -> bool:
        """Download an authorized MP3. New unlocks require explicit opt-in.

        Errors are raised rather than returned as a misleading empty result.
        Existing valid files are reused; partial files never replace them.
        """
        song_id = validate_song_id(song_id)
        # Re-read authoritative state before a potentially quota-consuming action.
        song = self.get_song(song_id)
        if not song:
            raise SunoAPIError('곡을 찾을 수 없습니다.', 404, 'not_found')
        if song.get('is_download_unlocked') is not True:
            if not unlock:
                raise SunoAPIError('아직 다운로드 잠금이 해제되지 않은 곡입니다. 새 승인 시 다운로드 한도가 사용됩니다.', 409, 'download_locked')
            self.authorize_download(song_id)
        destination = Path(output_path)
        if is_mp3(destination):
            return True
        url = self._prepared_download_url(song_id)
        destination.parent.mkdir(parents=True, exist_ok=True)
        part = None
        try:
            # Signed file URL is fetched without the Suno bearer token.
            with requests.get(url, stream=True, timeout=(10, 60)) as response:
                if response.status_code != 200:
                    raise SunoAPIError('MP3 파일 서버에서 다운로드가 실패했습니다.', 502, 'file_download_failed')
                content_type = response.headers.get('Content-Type', '').lower()
                if any(kind in content_type for kind in ('text/', 'json', 'xml')):
                    raise SunoAPIError('파일 서버가 오디오 대신 오류 응답을 반환했습니다.', 502, 'invalid_audio')
                with tempfile.NamedTemporaryFile(dir=destination.parent, suffix='.part', delete=False) as file:
                    part = Path(file.name)
                    size = 0
                    for chunk in response.iter_content(64 * 1024):
                        size += len(chunk)
                        if size > 250 * 1024 * 1024:
                            raise SunoAPIError('MP3 파일이 최대 허용 크기(250MB)를 초과했습니다.', 502, 'invalid_audio')
                        file.write(chunk)
                length = response.headers.get('Content-Length')
                if length and not response.headers.get('Content-Encoding') and size != int(length):
                    raise SunoAPIError('MP3 파일이 완전히 다운로드되지 않았습니다.', 502, 'incomplete_audio')
            if not is_mp3(part):
                raise SunoAPIError('다운로드 결과가 MP3 파일이 아닙니다.', 502, 'invalid_audio')
            os.replace(part, destination)
            return True
        except requests.RequestException:
            raise SunoAPIError('MP3 파일 연결에 실패했습니다. 다시 다운로드해 주세요.', 502, 'file_download_failed') from None
        finally:
            if part and part.exists():
                part.unlink()
