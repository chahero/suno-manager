from array import array
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch
import wave

from main import app

SONG_ID = 'd4865d3e-d7c0-4a05-afee-fa0cfe2cd116'
from recording import PlaybackRecorder, RecordingError

DEVICE = {'index': 4, 'name': 'Test Speakers [Loopback]', 'maxInputChannels': 2,
          'defaultSampleRate': 48000, 'isLoopbackDevice': True}
PCM = array('h', [1000, -1000] * 1024).tobytes()


class FakeStream:
    def __init__(self, callback, fail=False):
        self.callback = callback
        self.closed = False
        self.fail = fail

    def start_stream(self):
        if self.fail:
            raise OSError('simulated device disconnection')
        self.callback(PCM, 1024, {}, 0)

    def is_active(self):
        return True

    def close(self):
        self.closed = True


class FakeAudio:
    def __init__(self, fail=False):
        self.fail = fail
        self.stream = None
        self.terminated = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.terminate()

    def get_default_wasapi_loopback(self):
        return DEVICE

    def get_loopback_device_info_generator(self):
        # Device discovery must filter out microphones.
        return iter([DEVICE, {**DEVICE, 'index': 5, 'name': 'Microphone', 'isLoopbackDevice': False}])

    def get_device_info_by_index(self, index):
        return DEVICE

    def open(self, **kwargs):
        self.stream = FakeStream(kwargs['stream_callback'], self.fail)
        return self.stream

    def terminate(self):
        self.terminated = True


def backend(fail=False):
    module = MagicMock()
    module.PyAudio.side_effect = lambda: FakeAudio(fail)
    module.paInt16, module.paContinue, module.paComplete, module.paAbort = 8, 0, 1, 2
    return module


class RecorderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.recorder = PlaybackRecorder(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.recorder.shutdown)

    def wait_for(self, states):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            status = self.recorder.status()
            if status['state'] in states:
                return status
            time.sleep(0.01)
        self.fail('Recording did not reach expected state: ' + str(self.recorder.status()))

    def test_devices_only_include_output_loopback(self):
        with patch('recording.audio_backend', return_value=backend()):
            devices = self.recorder.devices()
        self.assertEqual(len(devices), 1)
        self.assertTrue(devices[0]['default'])

    def test_start_stop_creates_replayable_wav_and_persists_metadata(self):
        with patch('recording.audio_backend', return_value=backend()):
            job = self.recorder.start(4, 'A:?*/ test', song_id=SONG_ID)
            self.wait_for({'recording'})
            self.recorder.stop(job['id'])
            status = self.wait_for({'completed', 'error'})
        self.assertEqual(status['state'], 'completed', status)
        self.assertTrue(status['has_signal'])
        path, info = self.recorder.file(job['id'])
        self.assertNotIn('?', info['filename'])
        with wave.open(str(path)) as audio:
            self.assertEqual(audio.getnchannels(), 2)
            self.assertEqual(audio.getframerate(), 48000)
            self.assertEqual(audio.readframes(audio.getnframes()), PCM)
        second = PlaybackRecorder(self.temp.name)
        self.addCleanup(second.shutdown)
        self.assertEqual(second.recordings()[0]['id'], job['id'])
        self.assertEqual(second.recordings()[0]['song_id'], SONG_ID)
        self.assertFalse(list(Path(self.temp.name).glob('*.part')))

    def test_second_start_is_rejected_without_replacing_active_job(self):
        with patch('recording.audio_backend', return_value=backend()):
            first = self.recorder.start(4)
            self.wait_for({'recording'})
            with self.assertRaises(RecordingError) as error:
                self.recorder.start(4)
            self.assertEqual(error.exception.status_code, 409)
            self.assertEqual(self.recorder.status()['id'], first['id'])
            self.recorder.stop(first['id'])
            self.wait_for({'completed', 'error'})

    def test_auto_stop_finishes_file(self):
        with patch('recording.audio_backend', return_value=backend()):
            self.recorder.start(4, duration=1)
            status = self.wait_for({'completed', 'error'})
        self.assertEqual(status['state'], 'completed')
        self.assertTrue(status['auto_stopped'])

    def test_device_failure_closes_resources_and_leaves_no_partial_recording(self):
        with patch('recording.audio_backend', return_value=backend(fail=True)):
            self.recorder.start(4)
            status = self.wait_for({'error'})
        self.assertIn('출력 오디오', status['error'])
        self.assertFalse(list(Path(self.temp.name).glob('*.part')))
        self.assertEqual(self.recorder.recordings(), [])

    def test_invalid_device_and_duration_are_rejected(self):
        with patch('recording.audio_backend', return_value=backend()):
            for arguments in ((True, 0), (4, -1), (4, 3601), (4, 0.5), (5, 0)):
                with self.subTest(arguments=arguments), self.assertRaises(RecordingError):
                    self.recorder.start(arguments[0], duration=arguments[1])

    def test_stopping_another_id_does_not_stop_current_recording(self):
        with patch('recording.audio_backend', return_value=backend()):
            job = self.recorder.start(4)
            self.wait_for({'recording'})
            with self.assertRaises(RecordingError):
                self.recorder.stop('00000000-0000-0000-0000-000000000001')
            self.assertFalse(self.recorder.stop_event.is_set())
            self.recorder.stop(job['id'])
            self.wait_for({'completed', 'error'})

    def test_recording_paths_cannot_escape_folder(self):
        with self.assertRaises(RecordingError):
            self.recorder.file('../../private.wav')

    def test_invalid_song_id_never_starts_capture(self):
        with patch('recording.audio_backend') as audio:
            with self.assertRaises(RecordingError):
                self.recorder.start(4, song_id='../../song')
            audio.assert_not_called()
        self.assertEqual(self.recorder.status()['state'], 'idle')

    def test_automatic_song_playback_starts_after_capture_and_saves_at_actual_end(self):
        player = MagicMock()
        player.state.side_effect = [
            {'current_time': 0.2, 'duration': 0.4, 'ended': False, 'error': None},
            {'current_time': 0.4, 'duration': 0.4, 'ended': True, 'error': None}]
        capture_at_play = []
        player.play.side_effect = lambda: capture_at_play.append(self.recorder.status())
        with patch('recording.audio_backend', return_value=backend()), \
                patch('suno_playback.SunoPlayback', return_value=player):
            self.recorder.start(4, song_id=SONG_ID, auto_playback=True)
            status = self.wait_for({'completed', 'error'})
        self.assertEqual(status['state'], 'completed', status)
        self.assertEqual(capture_at_play[0]['state'], 'recording')
        self.assertGreater(capture_at_play[0]['bytes'], 0)
        self.assertEqual(status['stop_reason'], 'song-ended')
        self.assertTrue(status['auto_stopped'])
        self.assertEqual(status['playback_seconds'], 0.4)
        player.close.assert_called_once()
        path, _ = self.recorder.file(status['id'])
        with wave.open(str(path)) as audio:
            self.assertEqual(audio.readframes(audio.getnframes()), PCM)

    def test_manual_stop_also_closes_automatic_player(self):
        player = MagicMock()
        player.state.return_value = {'current_time': 0.2, 'duration': 120, 'ended': False, 'error': None}
        with patch('recording.audio_backend', return_value=backend()), \
                patch('suno_playback.SunoPlayback', return_value=player):
            job = self.recorder.start(4, song_id=SONG_ID, auto_playback=True)
            self.wait_for({'recording'})
            self.recorder.stop(job['id'])
            status = self.wait_for({'completed', 'error'})
        self.assertEqual(status['state'], 'completed', status)
        player.close.assert_called_once()

    def test_player_repeat_boundary_is_treated_as_song_end(self):
        player = MagicMock()
        player.state.side_effect = [
            {'current_time': 9.9, 'duration': 10, 'ended': False, 'error': None},
            {'current_time': 0.1, 'duration': 10, 'ended': False, 'error': None}]
        with patch('recording.audio_backend', return_value=backend()), \
                patch('suno_playback.SunoPlayback', return_value=player):
            self.recorder.start(4, song_id=SONG_ID, auto_playback=True)
            status = self.wait_for({'completed', 'error'})
        self.assertEqual(status['state'], 'completed', status)
        self.assertEqual(status['stop_reason'], 'song-ended')
        player.close.assert_called_once()

    def test_player_failure_closes_browser_and_leaves_no_recording(self):
        player = MagicMock()
        player.prepare.side_effect = RecordingError('Player connection failed')
        with patch('recording.audio_backend', return_value=backend()), \
                patch('suno_playback.SunoPlayback', return_value=player):
            self.recorder.start(4, song_id=SONG_ID, auto_playback=True)
            status = self.wait_for({'error'})
        self.assertIn('Player connection failed', status['error'])
        player.close.assert_called_once()
        self.assertEqual(self.recorder.recordings(), [])
        self.assertFalse(list(Path(self.temp.name).glob('*.part')))

    def test_automatic_playback_requires_song_and_default_output(self):
        with patch('recording.audio_backend', return_value=backend()):
            for arguments in ({'auto_playback': 'true', 'song_id': SONG_ID},
                              {'auto_playback': True}):
                with self.subTest(arguments=arguments), self.assertRaises(RecordingError):
                    self.recorder.start(4, **arguments)
        with patch.object(self.recorder, 'devices', return_value=[{
                'id': 4, 'name': 'Other output', 'default': False}]):
            with self.assertRaises(RecordingError):
                self.recorder.start(4, song_id=SONG_ID, auto_playback=True)
        self.assertEqual(self.recorder.status()['state'], 'idle')


class RecordingWebTests(unittest.TestCase):
    def setUp(self):
        self.previous = app.config['PLAYBACK_RECORDER']
        self.fake = MagicMock()
        app.config.update(TESTING=True, PLAYBACK_RECORDER=self.fake)
        self.addCleanup(lambda: app.config.update(PLAYBACK_RECORDER=self.previous))
        self.web = app.test_client()

    def test_recording_ui_and_api_work_without_a_suno_client(self):
        self.fake.devices.return_value = [{'id': 4, 'name': 'Test Speakers'}]
        self.fake.status.return_value = {'state': 'idle'}
        self.fake.recordings.return_value = []
        self.fake.start.return_value = {'state': 'starting', 'id': 'test'}
        self.fake.stop.return_value = {'state': 'stopping'}
        with patch('main.get_suno_client') as suno:
            self.assertEqual(self.web.get('/record').status_code, 302)
            self.assertEqual(self.web.get('/api/recordings/devices').status_code, 200)
            self.assertEqual(self.web.get('/api/recordings/status').status_code, 200)
            self.assertEqual(self.web.get('/api/recordings').status_code, 200)
            self.assertEqual(self.web.post('/api/recordings/start', json={'device_id': 4}).status_code, 202)
            self.assertEqual(self.web.post('/api/recordings/test/stop', json={}).status_code, 202)
            suno.assert_not_called()

    def test_old_recording_link_opens_the_song_in_library(self):
        result = self.web.get('/record?song_id=' + SONG_ID)
        self.assertEqual(result.status_code, 302)
        self.assertEqual(result.headers['Location'], '/library?record=' + SONG_ID)

    def test_library_renders_song_recording_dialog(self):
        with patch('main.get_suno_client') as suno:
            suno.return_value.bearer_token = 'test-token'
            result = self.web.get('/library')
        self.assertEqual(result.status_code,200)
        self.assertIn(b'id="song-recording-dialog"',result.data)
        self.assertIn(b'song-recording.js',result.data)

    def test_start_keeps_the_selected_song_id_without_calling_suno(self):
        self.fake.start.return_value = {'state':'starting','song_id':SONG_ID}
        with patch('main.get_suno_client') as suno:
            result = self.web.post('/api/recordings/start',json={
                'device_id':4,'title':'My song','duration':0,'song_id':SONG_ID})
        self.assertEqual(result.status_code, 202)
        self.fake.start.assert_called_once_with(4,'My song',0,song_id=SONG_ID)
        suno.assert_not_called()

    def test_automatic_playback_start_does_not_call_download_or_authorization_client(self):
        self.fake.start.return_value = {'state': 'starting', 'song_id': SONG_ID}
        with patch('main.get_suno_client') as suno:
            result = self.web.post('/api/recordings/start', json={
                'device_id': 4, 'song_id': SONG_ID, 'auto_playback': True})
        self.assertEqual(result.status_code, 202)
        self.fake.start.assert_called_once_with(4, 'Recording', 0, song_id=SONG_ID, auto_playback=True)
        suno.assert_not_called()

    def test_recording_list_can_be_filtered_by_song(self):
        self.fake.recordings.return_value = [
            {'id':'first','song_id':SONG_ID}, {'id':'second','song_id':None},
            {'id':'third','song_id':'00000000-0000-0000-0000-000000000001'}]
        result = self.web.get('/api/recordings?song_id=' + SONG_ID)
        self.assertEqual(result.json['recordings'], [{'id':'first','song_id':SONG_ID}])

    def test_local_song_audio_does_not_require_a_live_suno_token(self):
        previous = app.config['DOWNLOAD_FOLDER']
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / (SONG_ID + '.mp3')
            path.write_bytes(b'ID3' + b'\x00' * 200)
            app.config['DOWNLOAD_FOLDER'] = folder
            try:
                with patch('main.get_suno_client') as suno:
                    result = self.web.get('/api/songs/' + SONG_ID + '/audio',headers={'Range':'bytes=0-2'})
                    self.assertEqual(result.status_code, 206)
                    self.assertEqual(result.data,b'ID3')
                    result.close(); suno.assert_not_called()
            finally:
                app.config['DOWNLOAD_FOLDER'] = previous

    def test_local_song_list_combines_recordings_and_cached_mp3_without_suno(self):
        previous = app.config['DOWNLOAD_FOLDER']
        self.fake.recordings.return_value = [
            {'song_id':SONG_ID,'title':'Recorded song','created_at':'2026-10-04'},
            {'song_id':None,'title':'Generic recording'},
            {'song_id':'../invalid','title':'Invalid'}]
        with tempfile.TemporaryDirectory() as folder:
            Path(folder,SONG_ID + '.mp3').write_bytes(b'ID3' + b'\x00' * 200)
            app.config['DOWNLOAD_FOLDER'] = folder
            try:
                with patch('main.get_suno_client') as suno:
                    result = self.web.get('/api/songs/local')
                self.assertEqual(result.status_code,200)
                self.assertEqual(len(result.json['clips']),1)
                song = result.json['clips'][0]
                self.assertEqual(song['id'],SONG_ID)
                self.assertEqual(song['title'],'Recorded song')
                self.assertTrue(song['offline'])
                self.assertEqual(song['local_audio_url'],'/api/songs/' + SONG_ID + '/audio')
                suno.assert_not_called()
            finally:
                app.config['DOWNLOAD_FOLDER'] = previous

    def test_local_song_list_rejects_remote_clients(self):
        result = self.web.get('/api/songs/local',environ_overrides={'REMOTE_ADDR':'192.168.1.20'})
        self.assertEqual(result.status_code,403)

    def test_cross_origin_start_does_not_capture(self):
        result = self.web.post('/api/recordings/start', json={'device_id': 4},
                               headers={'Origin': 'https://other.example'})
        self.assertEqual(result.status_code, 403)
        self.fake.start.assert_not_called()

    def test_remote_clients_cannot_start_recording(self):
        result = self.web.post('/api/recordings/start', json={'device_id': 4},
                               environ_overrides={'REMOTE_ADDR': '192.168.1.20'})
        self.assertEqual(result.status_code, 403)
        self.fake.start.assert_not_called()

    def test_nonlocal_host_is_rejected(self):
        result = self.web.post('/api/recordings/start', json={'device_id': 4},
                               base_url='http://other.example')
        self.assertEqual(result.status_code, 403)
        self.fake.start.assert_not_called()

    def test_wav_download_and_audio_range_work_without_suno(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'test.wav'
            with wave.open(str(path), 'wb') as audio:
                audio.setnchannels(2); audio.setsampwidth(2); audio.setframerate(48000)
                audio.writeframes(PCM)
            self.fake.file.return_value = (path, {'filename': 'test.wav'})
            with patch('main.get_suno_client') as suno:
                result = self.web.get('/api/recordings/test/download')
                self.assertEqual(result.status_code, 200)
                self.assertTrue(result.data.startswith(b'RIFF'))
                self.assertIn('attachment', result.headers['Content-Disposition'])
                result.close()
                result = self.web.get('/api/recordings/test/audio', headers={'Range': 'bytes=0-43'})
                self.assertEqual(result.status_code, 206)
                self.assertEqual(len(result.data), 44)
                result.close()
                suno.assert_not_called()


if __name__ == '__main__':
    unittest.main()
