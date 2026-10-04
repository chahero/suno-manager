import json
from contextlib import redirect_stdout
from io import BytesIO, StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import zipfile

import requests

from main import app
from suno_api import SunoAPI, SunoAPIError, download_filename, validate_song_id
from download import main as download_main

ID = 'd4865d3e-d7c0-4a05-afee-fa0cfe2cd116'
OTHER = '5fcfbb2b-c985-41b0-b910-a0662367f3ba'
MP3 = b'ID3' + b'\0' * 200


def response(status=200, data=None):
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(data or {}).encode()
    result._content_consumed = True
    return result


def file_response(body=MP3, content_type='audio/mpeg'):
    result = MagicMock()
    result.__enter__.return_value = result
    result.status_code = 200
    result.headers = {'Content-Type': content_type, 'Content-Length': str(len(body))}
    result.iter_content.return_value = [body]
    return result


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.client = SunoAPI('Bearer test-token')
        self.addCleanup(self.client.close)

    def test_headers_only_advertise_supported_encodings(self):
        self.assertEqual(self.client.headers['Accept-Encoding'], requests.utils.default_headers()['Accept-Encoding'])
        self.assertEqual(self.client.headers['Authorization'], 'Bearer test-token')

    def test_expired_token_is_not_an_empty_success(self):
        with patch.object(self.client.session, 'request', return_value=response(401)):
            self.assertFalse(self.client.is_authenticated())
            with self.assertRaises(SunoAPIError) as caught:
                self.client.get_songs()
            self.assertEqual(caught.exception.status_code, 401)

    def test_connection_error_is_not_an_empty_library(self):
        with patch.object(self.client.session, 'request', side_effect=requests.Timeout):
            with self.assertRaises(SunoAPIError) as caught:
                self.client.is_authenticated()
            self.assertEqual(caught.exception.code, 'connection_failed')

    def test_repeated_cursor_stops_instead_of_looping(self):
        page = {'clips': [{'id': ID}], 'has_more': True, 'next_cursor': 'repeat'}
        with patch.object(self.client, 'get_songs', return_value=page) as request:
            with self.assertRaises(SunoAPIError) as caught:
                self.client.get_all_songs()
            self.assertEqual(caught.exception.code, 'invalid_pagination')
            self.assertEqual(request.call_count, 2)

    def test_missing_cursor_is_an_error(self):
        with patch.object(self.client, '_request', return_value={'clips': [], 'has_more': True}):
            with self.assertRaises(SunoAPIError):
                self.client.get_songs()

    def test_single_song_does_not_scan_feed(self):
        with patch.object(self.client, '_request', return_value={'id': ID}) as request:
            self.assertEqual(self.client.get_song(ID)['id'], ID)
            request.assert_called_once_with('GET', '/clip/' + ID)

    def test_locked_song_never_authorizes_by_default(self):
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(self.client, 'get_song', return_value={'id': ID, 'is_download_unlocked': False}), \
                patch.object(self.client, 'authorize_download') as authorize:
            with self.assertRaises(SunoAPIError) as caught:
                self.client.download_song(ID, str(Path(folder) / 'song.mp3'))
            self.assertEqual(caught.exception.code, 'download_locked')
            authorize.assert_not_called()

    def test_explicit_unlock_uses_current_contract(self):
        with patch.object(self.client.session, 'request', return_value=response(data={'ok': True})) as request:
            self.client.authorize_download(ID)
            self.assertEqual(request.call_args.args[:2], ('POST', self.client.base_url + '/download/authorize'))
            self.assertEqual(request.call_args.kwargs['json'], {'item_id': ID, 'item_type': 'clip'})
            self.assertFalse(request.call_args.kwargs['allow_redirects'])

    def test_uncertain_authorization_is_sent_only_once(self):
        for failure in (requests.Timeout(), response(503), response(data={'message': 'unknown'})):
            with self.subTest(failure=type(failure).__name__):
                options = {'side_effect': failure} if isinstance(failure, Exception) else {'return_value': failure}
                with patch.object(self.client.session, 'request', **options) as request:
                    with self.assertRaises(SunoAPIError) as caught:
                        self.client.authorize_download(ID)
                    self.assertEqual(caught.exception.code, 'authorization_uncertain')
                    self.assertEqual(request.call_count, 1)

    def test_processing_is_polled_without_reauthorization(self):
        with patch.object(self.client, '_request', side_effect=[
            {'ok': True, 'status': 'processing'},
            {'ok': True, 'status': 'ready', 'download_url': 'https://files.example/song.mp3'}
        ]) as request, patch('suno_api.time.sleep'):
            self.assertEqual(self.client._prepared_download_url(ID), 'https://files.example/song.mp3')
            self.assertTrue(all(call.args[0] == 'GET' for call in request.call_args_list))

    def test_invalid_file_does_not_replace_existing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'song.mp3'
            path.write_bytes(b'old file')
            with patch.object(self.client, 'get_song', return_value={'id': ID, 'is_download_unlocked': True}), \
                    patch.object(self.client, '_prepared_download_url', return_value='https://files.example/song.mp3'), \
                    patch('suno_api.requests.get', return_value=file_response(b'<html>not audio</html>', 'application/octet-stream')):
                with self.assertRaises(SunoAPIError) as caught:
                    self.client.download_song(ID, str(path))
                self.assertEqual(caught.exception.code, 'invalid_audio')
            self.assertEqual(path.read_bytes(), b'old file')
            self.assertEqual(list(Path(folder).glob('*.part')), [])

    def test_signed_file_fetch_receives_no_bearer(self):
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(self.client, 'get_song', return_value={'id': ID, 'is_download_unlocked': True}), \
                patch.object(self.client, '_prepared_download_url', return_value='https://files.example/song.mp3'), \
                patch('suno_api.requests.get', return_value=file_response()) as get:
            path = Path(folder) / 'song.mp3'
            self.client.download_song(ID, str(path))
            self.assertEqual(path.read_bytes(), MP3)
            self.assertNotIn('headers', get.call_args.kwargs)

    def test_explicit_unlock_authorizes_once_before_download(self):
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(self.client, 'get_song', return_value={'id': ID, 'is_download_unlocked': False}), \
                patch.object(self.client, 'authorize_download') as authorize, \
                patch.object(self.client, '_prepared_download_url', return_value='https://files.example/song.mp3'), \
                patch('suno_api.requests.get', return_value=file_response()):
            self.client.download_song(ID, str(Path(folder) / 'song.mp3'), unlock=True)
            authorize.assert_called_once_with(ID)

    def test_windows_filename_and_invalid_path_id(self):
        name = download_filename({'id': ID, 'title': 'CON:"a\\b/?*<>|. '})
        self.assertTrue(name.endswith(ID + '.mp3'))
        self.assertFalse(any(character in name for character in '<>:"/\\|?*'))
        with self.assertRaises(ValueError):
            validate_song_id('../../private')


class WebTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.previous = app.config['DOWNLOAD_FOLDER']
        app.config.update(TESTING=True, DOWNLOAD_FOLDER=self.folder.name)
        self.addCleanup(lambda: app.config.update(DOWNLOAD_FOLDER=self.previous))
        self.web = app.test_client()

    def test_single_download_rejects_nonboolean_unlock(self):
        with patch('main.get_suno_client') as client:
            result = self.web.post('/api/songs/' + ID + '/download', json={'unlock': 'false'})
            self.assertEqual(result.status_code, 400)
            client.assert_not_called()

    def test_batch_reports_partial_failures_and_deduplicates(self):
        fake = MagicMock()
        fake.get_song.side_effect = lambda song_id: {'id': song_id, 'title': 'A:?*'}
        def save(song_id, output_path, **kwargs):
            if song_id == OTHER:
                raise SunoAPIError('잠금 해제 필요', 409, 'download_locked')
            Path(output_path).write_bytes(MP3)
        fake.download_song.side_effect = save
        with patch('main.get_suno_client', return_value=fake):
            result = self.web.post('/api/songs/batch-download', json={'song_ids': [ID, OTHER, ID]})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.headers['X-Downloaded-Count'], '1')
        self.assertEqual(result.headers['X-Failed-Count'], '1')
        with zipfile.ZipFile(BytesIO(result.data)) as archive:
            report = json.loads(archive.read('download-results.json'))
            self.assertEqual(report['failed'][0]['code'], 'download_locked')
            self.assertEqual(len(report['downloaded']), 1)
            self.assertIsNone(archive.testzip())
        self.assertEqual(fake.download_song.call_count, 2)

    def test_batch_stops_after_uncertain_approval(self):
        fake = MagicMock()
        fake.get_song.side_effect = lambda song_id: {'id': song_id}
        fake.download_song.side_effect = SunoAPIError('불명확', 502, 'authorization_uncertain')
        with patch('main.get_suno_client', return_value=fake):
            result = self.web.post('/api/songs/batch-download', json={'song_ids': [ID, OTHER], 'unlock': True})
        self.assertEqual(result.status_code, 409)
        self.assertEqual(fake.download_song.call_count, 1)
        self.assertEqual(result.json['failed'][1]['code'], 'not_attempted')

    def test_api_failure_preserves_error_status(self):
        fake = MagicMock()
        fake.get_songs.side_effect = SunoAPIError('만료된 토큰', 401, 'unauthorized')
        with patch('main.get_suno_client', return_value=fake):
            result = self.web.get('/api/songs')
        self.assertEqual(result.status_code, 401)
        self.assertNotIn('clips', result.json)

    def test_login_cookie_does_not_contain_token_and_logout_blocks_env_fallback(self):
        with patch('main.SunoAPI.is_authenticated', return_value=True):
            result = self.web.post('/login', json={'token': 'Bearer private-test-token'})
        self.assertEqual(result.status_code, 200)
        with self.web.session_transaction() as stored:
            self.assertNotIn('suno_token', stored)
            auth_id = stored['auth_id']
        self.assertEqual(app.config['SERVER_TOKENS'][auth_id], 'private-test-token')
        self.web.get('/logout')
        self.assertNotIn(auth_id, app.config['SERVER_TOKENS'])
        self.assertEqual(self.web.get('/').status_code, 302)
        self.assertEqual(self.web.get('/api/auth/check').status_code, 401)


class CLITests(unittest.TestCase):
    def test_all_skips_locked_tracks_by_default(self):
        fake = MagicMock()
        fake.get_all_songs.return_value = [
            {'id': ID, 'is_download_unlocked': True},
            {'id': OTHER, 'is_download_unlocked': False},
        ]
        with patch('download.SunoAPI', return_value=fake), redirect_stdout(StringIO()):
            self.assertEqual(download_main(['--all']), 0)
        self.assertEqual(fake.download_song.call_count, 1)
        self.assertEqual(fake.download_song.call_args.args[0], ID)
        self.assertFalse(fake.download_song.call_args.kwargs['unlock'])

    def test_all_unlock_is_an_explicit_opt_in(self):
        fake = MagicMock()
        fake.get_all_songs.return_value = [{'id': OTHER, 'is_download_unlocked': False}]
        with patch('download.SunoAPI', return_value=fake), redirect_stdout(StringIO()):
            self.assertEqual(download_main(['--all', '--unlock']), 0)
        self.assertTrue(fake.download_song.call_args.kwargs['unlock'])


if __name__ == '__main__':
    unittest.main()
