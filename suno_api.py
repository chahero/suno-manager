import requests
import os
import uuid
from typing import Optional, List, Dict

class SunoAPI:
    def __init__(self, bearer_token: Optional[str] = None):
        """
        SUNO API 클라이언트

        Args:
            bearer_token: SUNO Bearer 토큰 (JWT)
        """
        self.bearer_token = bearer_token or os.getenv('SUNO_BEARER_TOKEN')
        self.base_url = 'https://studio-api.prod.suno.com/api'

        # 디바이스 ID 생성 또는 환경 변수에서 가져오기
        self.device_id = os.getenv('SUNO_DEVICE_ID', str(uuid.uuid4()))

        self.session = requests.Session()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9,ko;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Authorization': f'Bearer {self.bearer_token}' if self.bearer_token else '',
            'device-id': self.device_id,
        }

    def get_songs(self, page: int = 0) -> Dict:
        """
        생성된 음악 목록 조회

        Args:
            page: 페이지 번호 (0부터 시작)

        Returns:
            음악 목록 및 메타데이터
        """
        endpoint = f'{self.base_url}/feed/v2'
        params = {
            'hide_disliked': 'true',
            'hide_gen_stems': 'true',
            'hide_studio_clips': 'true',
            'page': page
        }

        try:
            response = self.session.get(endpoint, params=params, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"API Error: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Response: {e.response.text}")
            return {
                'clips': [],
                'num_total_results': 0,
                'current_page': 0,
                'has_more': False
            }

    def get_all_songs(self, max_pages: int = 10) -> List[Dict]:
        """
        모든 음악 목록 조회 (페이지네이션)

        Args:
            max_pages: 최대 페이지 수

        Returns:
            모든 음악 목록
        """
        all_clips = []
        page = 0

        while page < max_pages:
            result = self.get_songs(page=page)
            clips = result.get('clips', [])

            if not clips:
                break

            all_clips.extend(clips)

            if not result.get('has_more', False):
                break

            page += 1

        return all_clips

    def get_song(self, song_id: str) -> Optional[Dict]:
        """
        특정 음악 정보 조회

        Args:
            song_id: 음악 ID

        Returns:
            음악 정보
        """
        # feed에서 특정 곡 찾기
        songs = self.get_all_songs()
        for song in songs:
            if song.get('id') == song_id:
                return song
        return None

    def generate_music(self, prompt: str, tags: str = "", **kwargs) -> Dict:
        """
        음악 생성 요청 (SUNO v2 API)

        Args:
            prompt: 가사/프롬프트
            tags: 음악 스타일/장르 태그
            **kwargs: 추가 파라미터

        Returns:
            생성 작업 정보
        """
        endpoint = f'{self.base_url}/generate/v2/'
        payload = {
            'prompt': prompt,
            'tags': tags,
            'make_instrumental': kwargs.get('instrumental', False),
            'wait_audio': False
        }

        try:
            response = self.session.post(endpoint, json=payload, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Generate Error: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Response: {e.response.text}")
            return {'error': str(e)}

    def delete_song(self, song_id: str) -> bool:
        """
        음악 삭제

        Args:
            song_id: 삭제할 음악 ID

        Returns:
            성공 여부
        """
        # SUNO API의 삭제 엔드포인트
        endpoint = f'{self.base_url}/clip/{song_id}'

        try:
            response = self.session.delete(endpoint, headers=self.headers)
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            print(f"Delete Error: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Response: {e.response.text}")
            return False

    def download_song(self, song_id: str, output_path: str) -> bool:
        """
        음악 다운로드

        Args:
            song_id: 다운로드할 음악 ID
            output_path: 저장 경로

        Returns:
            성공 여부
        """
        song_info = self.get_song(song_id)
        if not song_info:
            return False

        audio_url = song_info.get('audio_url')
        if not audio_url:
            return False

        try:
            response = requests.get(audio_url, stream=True)
            response.raise_for_status()

            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True
        except requests.exceptions.RequestException as e:
            print(f"Download Error: {e}")
            return False

    def is_authenticated(self) -> bool:
        """
        인증 상태 확인

        Returns:
            인증 여부
        """
        try:
            result = self.get_songs(page=0)
            return 'clips' in result and result.get('num_total_results', 0) >= 0
        except:
            return False
