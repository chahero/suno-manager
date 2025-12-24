import requests
import os
import uuid
from typing import Optional, List, Dict

class SunoAPI:
    def __init__(self, bearer_token: Optional[str] = None):
        """
        SUNO API Client

        Args:
            bearer_token: SUNO Bearer token (JWT)
        """
        self.bearer_token = bearer_token or os.getenv('SUNO_BEARER_TOKEN')
        self.base_url = 'https://studio-api.prod.suno.com/api'

        # Generate device ID or get from environment variable
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
        Get generated music list

        Args:
            page: Page number (starts from 0)

        Returns:
            Music list and metadata
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
        Get all music list (with pagination)

        Args:
            max_pages: Maximum number of pages

        Returns:
            All music list
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
        Get specific music info

        Args:
            song_id: Music ID

        Returns:
            Music info
        """
        # Find specific song from feed
        songs = self.get_all_songs()
        for song in songs:
            if song.get('id') == song_id:
                return song
        return None

    def generate_music(self, prompt: str, tags: str = "", **kwargs) -> Dict:
        """
        Request music generation (SUNO v2 API)

        Args:
            prompt: Lyrics/prompt
            tags: Music style/genre tags
            **kwargs: Additional parameters

        Returns:
            Generation task info
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
        Delete music

        Args:
            song_id: Music ID to delete

        Returns:
            Success status
        """
        # SUNO API delete endpoint
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
        Download music

        Args:
            song_id: Music ID to download
            output_path: Save path

        Returns:
            Success status
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
        Check authentication status

        Returns:
            Authentication status
        """
        try:
            result = self.get_songs(page=0)
            return 'clips' in result and result.get('num_total_results', 0) >= 0
        except:
            return False

    def get_billing_info(self) -> Dict:
        """
        Get credits and subscription info

        Returns:
            Credits, plan, subscription info
        """
        endpoint = f'{self.base_url}/billing/info/'

        try:
            response = self.session.get(endpoint, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Billing Info Error: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Response: {e.response.text}")
            return {
                'total_credits_left': 0,
                'monthly_limit': 0,
                'monthly_usage': 0,
                'plan': {'name': 'Unknown'}
            }
