import requests
import os
from typing import Optional, List, Dict

class SunoAPI:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('SUNO_API_KEY')
        self.base_url = os.getenv('SUNO_API_URL', 'https://api.suno.ai/v1')
        self.headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }

    def generate_music(self, prompt: str, duration: int = 30, **kwargs) -> Dict:
        """
        음악 생성 요청

        Args:
            prompt: 음악 생성 프롬프트
            duration: 음악 길이 (초)
            **kwargs: 추가 파라미터 (genre, mood, instruments 등)

        Returns:
            생성된 음악 정보
        """
        endpoint = f'{self.base_url}/generate'
        payload = {
            'prompt': prompt,
            'duration': duration,
            **kwargs
        }

        try:
            response = requests.post(endpoint, json=payload, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {'error': str(e)}

    def get_songs(self, limit: int = 50, offset: int = 0) -> List[Dict]:
        """
        생성된 음악 목록 조회

        Args:
            limit: 가져올 곡 수
            offset: 오프셋

        Returns:
            음악 목록
        """
        endpoint = f'{self.base_url}/songs'
        params = {'limit': limit, 'offset': offset}

        try:
            response = requests.get(endpoint, params=params, headers=self.headers)
            response.raise_for_status()
            return response.json().get('songs', [])
        except requests.exceptions.RequestException as e:
            return []

    def get_song(self, song_id: str) -> Optional[Dict]:
        """
        특정 음악 정보 조회

        Args:
            song_id: 음악 ID

        Returns:
            음악 정보
        """
        endpoint = f'{self.base_url}/songs/{song_id}'

        try:
            response = requests.get(endpoint, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return None

    def delete_song(self, song_id: str) -> bool:
        """
        음악 삭제

        Args:
            song_id: 삭제할 음악 ID

        Returns:
            성공 여부
        """
        endpoint = f'{self.base_url}/songs/{song_id}'

        try:
            response = requests.delete(endpoint, headers=self.headers)
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
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
        if not song_info or 'audio_url' not in song_info:
            return False

        try:
            response = requests.get(song_info['audio_url'], stream=True)
            response.raise_for_status()

            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True
        except requests.exceptions.RequestException as e:
            return False
