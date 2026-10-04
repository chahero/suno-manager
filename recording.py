"""Local Windows playback capture. No Suno API calls are made here."""
import atexit
from array import array
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import threading
import time
import uuid
import wave

MAX_SECONDS = 3600


class RecordingError(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


def audio_backend():
    if os.name != 'nt':
        raise RecordingError('출력 오디오 녹음은 Windows에서 지원합니다.', 503)
    try:
        import pyaudiowpatch
        return pyaudiowpatch
    except ImportError:
        raise RecordingError('녹음 라이브러리가 필요합니다. requirements.txt를 설치하고 서버를 다시 시작해 주세요.', 503) from None


def recording_id(value):
    try:
        return str(uuid.UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise RecordingError('녹음 ID가 올바르지 않습니다.') from None


def safe_title(value):
    if not isinstance(value, str):
        raise RecordingError('녹음 이름은 문자열이어야 합니다.')
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', '-', value).strip(' .')[:80] or 'Recording'


class PlaybackRecorder:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.lock = threading.RLock()
        self.job = None
        self.worker = None
        self.stop_event = threading.Event()
        atexit.register(self.shutdown)

    def devices(self):
        backend = audio_backend()
        try:
            with backend.PyAudio() as audio:
                try:
                    default = int(audio.get_default_wasapi_loopback()['index'])
                except (OSError, LookupError):
                    default = None
                devices = [
                    {'id': int(device['index']), 'name': device['name'],
                     'channels': int(device['maxInputChannels']),
                     'sample_rate': int(device['defaultSampleRate']),
                     'default': int(device['index']) == default}
                    for device in audio.get_loopback_device_info_generator()
                    if device.get('isLoopbackDevice') and device['maxInputChannels'] > 0
                ]
        except OSError:
            raise RecordingError('Windows 출력 장치를 읽지 못했습니다. 연결된 스피커·헤드폰을 확인해 주세요.', 503) from None
        if not devices:
            raise RecordingError('녹음할 출력 장치가 없습니다. 스피커·헤드폰을 연결해 주세요.', 503)
        return devices

    def status(self):
        with self.lock:
            if not self.job:
                return {'state': 'idle'}
            result = {key: value for key, value in self.job.items() if not key.startswith('_')}
            if result['state'] in ('starting', 'recording', 'stopping'):
                result['elapsed_seconds'] = round(time.monotonic() - self.job['_started'], 2)
                if time.monotonic() - self.job.get('_last_audio', 0) > 1:
                    result['level'] = 0
            return result

    def start(self, device_id, title='Recording', duration=0, song_id=None, auto_playback=False):
        if not isinstance(auto_playback, bool):
            raise RecordingError('auto_playback은 true 또는 false여야 합니다.')
        if isinstance(device_id, bool) or not isinstance(device_id, int):
            raise RecordingError('출력 장치를 선택해 주세요.')
        if isinstance(duration, bool) or not isinstance(duration, int) or not 0 <= duration <= MAX_SECONDS:
            raise RecordingError('자동 정지 시간은 0~3600초의 정수로 입력해 주세요.')
        title = safe_title(title)
        if song_id is not None:
            try:
                song_id = str(uuid.UUID(song_id))
            except (ValueError, TypeError, AttributeError):
                raise RecordingError('곡 ID가 올바르지 않습니다.') from None
        devices = self.devices()
        device = next((item for item in devices if item['id'] == device_id), None)
        if not device:
            raise RecordingError('선택한 출력 장치를 찾을 수 없습니다. 장치 목록을 새로고침해 주세요.')
        if auto_playback and (not song_id or not device['default']):
            raise RecordingError('Suno 자동 재생은 곡 ID와 Windows 기본 출력 장치를 선택해야 합니다.')
        with self.lock:
            if self.job and self.job['state'] in ('starting', 'recording', 'stopping'):
                raise RecordingError('이미 녹음 중입니다. 현재 녹음을 정지해 주세요.', 409)
            try:
                self.folder.mkdir(parents=True, exist_ok=True)
            except OSError:
                raise RecordingError('녹음 저장 폴더를 만들 수 없습니다.', 500) from None
            self.stop_event = threading.Event()
            self.job = {
                'id': str(uuid.uuid4()), 'title': title, 'song_id': song_id, 'state': 'starting',
                'device_name': device['name'], 'device_id': device['id'],
                'sample_rate': device['sample_rate'], 'channels': min(device['channels'], 2),
                'created_at': datetime.now(timezone.utc).isoformat(),
                'duration_limit': duration or MAX_SECONDS, 'elapsed_seconds': 0,
                'audio_seconds': 0, 'bytes': 0, 'level': 0, 'has_signal': False,
                'auto_playback': auto_playback,
                '_started': time.monotonic(), '_frames': 0,
            }
            self.worker = threading.Thread(target=self._capture, args=(self.job, self.stop_event),
                                           name='playback-recorder', daemon=True)
            self.worker.start()
            return self.status()

    def stop(self, job_id):
        job_id = recording_id(job_id)
        with self.lock:
            if not self.job or self.job['id'] != job_id:
                raise RecordingError('현재 녹음과 ID가 다릅니다.', 409)
            if self.job['state'] in ('starting', 'recording'):
                self.job['state'] = 'stopping'
                self.stop_event.set()
            return self.status()

    def _capture(self, job, stop_event):
        backend = audio = stream = wav = playback = None
        part = self.folder / (job['id'] + '.wav.part')
        destination = self.folder / (job['id'] + '.wav')
        failure = None
        try:
            if job['auto_playback']:
                from suno_playback import SunoPlayback
                playback = SunoPlayback(job['song_id'])
                playback.prepare()
                if stop_event.is_set():
                    return
            backend = audio_backend()
            audio = backend.PyAudio()
            # Recheck the source at opening time; microphone indices cannot be used.
            device = audio.get_device_info_by_index(job['device_id'])
            if not device.get('isLoopbackDevice'):
                raise RecordingError('출력 오디오 장치만 녹음할 수 있습니다.')
            wav = wave.open(str(part), 'wb')
            wav.setnchannels(job['channels'])
            wav.setsampwidth(2)
            wav.setframerate(job['sample_rate'])

            def callback(data, frames, _timing, flags):
                try:
                    if stop_event.is_set():
                        return (None, backend.paComplete)
                    wav.writeframesraw(data)
                    samples = array('h', data)
                    peak = max((abs(sample) for sample in samples), default=0)
                    with self.lock:
                        job['_frames'] += len(data) // (2 * job['channels'])
                        job['bytes'] += len(data)
                        job['audio_seconds'] = round(job['_frames'] / job['sample_rate'], 3)
                        job['level'] = round(min(1, peak / 32768), 4)
                        job['has_signal'] = job['has_signal'] or peak > 32
                        job['_last_audio'] = time.monotonic()
                        if flags:
                            job['overruns'] = job.get('overruns', 0) + 1
                    return (None, backend.paContinue)
                except Exception:
                    with self.lock:
                        job['_callback_error'] = True
                    stop_event.set()
                    return (None, backend.paAbort)

            stream = audio.open(format=backend.paInt16, channels=job['channels'],
                                rate=job['sample_rate'], input=True,
                                input_device_index=job['device_id'], frames_per_buffer=1024,
                                stream_callback=callback, start=False)
            with self.lock:
                if not stop_event.is_set():
                    job['state'] = 'recording'
            stream.start_stream()
            capture_started = time.monotonic()
            deadline = capture_started + job['duration_limit']
            if playback:
                playback.play()
            last_progress, last_time, began_playing = capture_started, 0, False
            while not stop_event.wait(0.1):
                if playback:
                    state = playback.state()
                    with self.lock:
                        job['playback_seconds'] = round(state['current_time'], 2)
                        job['playback_duration'] = state['duration']
                    if state['current_time'] > last_time:
                        began_playing = True
                        last_progress, last_time = time.monotonic(), state['current_time']
                    wrapped_at_end = (began_playing and state['duration'] and
                                      last_time >= state['duration'] - 0.5 and
                                      state['current_time'] < last_time - 1)
                    if (state['ended'] or wrapped_at_end) and began_playing:
                        # Let the output buffer drain before closing the loopback stream.
                        stop_event.wait(0.4)
                        with self.lock:
                            job['auto_stopped'] = True
                            job['stop_reason'] = 'song-ended'
                        break
                    if time.monotonic() - last_progress > 30:
                        raise RecordingError('Suno 재생이 시작되지 않거나 30초 이상 멈췄습니다. 인터넷 연결을 확인한 뒤 다시 녹음하세요.', 503)
                    if state['error'] and began_playing:
                        raise RecordingError('Suno 곡 재생 중 오류가 발생했습니다. 다시 녹음해 주세요.', 503)
                if time.monotonic() >= deadline:
                    with self.lock:
                        job['auto_stopped'] = True
                        job['stop_reason'] = 'time-limit'
                    break
                if not stream.is_active():
                    raise RecordingError('오디오 장치 연결이 종료되었습니다. 다시 연결한 뒤 녹음해 주세요.', 503)
        except RecordingError as error:
            failure = str(error)
        except (OSError, ValueError):
            failure = '출력 오디오를 열거나 저장하지 못했습니다. 장치 연결·저장 공간을 확인해 주세요.'
        except Exception:
            failure = '녹음 처리에 실패했습니다. 출력 장치를 다시 선택해 주세요.'
        finally:
            if playback:
                playback.close()
            # Close the callback stream before closing the WAV writer.
            for resource, method in ((stream, 'close'), (wav, 'close'), (audio, 'terminate')):
                if resource:
                    try:
                        getattr(resource, method)()
                    except Exception:
                        failure = failure or '녹음 파일을 마무리하지 못했습니다.'
            with self.lock:
                job['elapsed_seconds'] = round(time.monotonic() - job['_started'], 2)
                job['level'] = 0
                if job.get('_callback_error'):
                    failure = failure or '오디오 데이터를 저장하지 못했습니다.'
                if not job['bytes']:
                    failure = failure or '오디오 데이터가 없습니다. 선택한 장치에서 소리를 재생한 뒤 다시 녹음해 주세요.'
                if failure:
                    job['state'], job['error'] = 'error', failure
                    if part.exists():
                        try:
                            part.unlink(missing_ok=True)
                        except OSError:
                            pass
                else:
                    try:
                        os.replace(part, destination)
                        job['state'] = 'completed'
                        job['filename'] = f"{job['title']}_{job['id'][:8]}.wav"
                        metadata = self.status()
                        metadata.pop('level', None)
                        sidecar = self.folder / (job['id'] + '.json')
                        sidecar.write_text(json.dumps(metadata, ensure_ascii=False), encoding='utf-8')
                    except OSError:
                        job['state'], job['error'] = 'error', '녹음 파일을 저장하지 못했습니다. 저장 경로를 확인해 주세요.'

    def recordings(self):
        result = []
        for path in self.folder.glob('*.json'):
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
                job_id = recording_id(data['id'])
                if path.stem == job_id and (self.folder / (job_id + '.wav')).is_file():
                    result.append(data)
            except (OSError, ValueError, KeyError, TypeError, RecordingError):
                continue
        return sorted(result, key=lambda item: item.get('created_at', ''), reverse=True)

    def file(self, job_id):
        job_id = recording_id(job_id)
        path = self.folder / (job_id + '.wav')
        info = next((item for item in self.recordings() if item['id'] == job_id), None)
        if not info or not path.is_file():
            raise RecordingError('저장된 녹음을 찾을 수 없습니다.', 404)
        return path, info

    def shutdown(self):
        with self.lock:
            self.stop_event.set()
            worker = self.worker
        if worker and worker.is_alive() and worker is not threading.current_thread():
            worker.join(timeout=3)
