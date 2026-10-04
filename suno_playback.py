"""Control Suno's official player in an isolated local Edge session."""
from recording import RecordingError


class SunoPlayback:
    def __init__(self, song_id):
        self.song_id = song_id
        self.runtime = self.browser = self.page = None

    def prepare(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RecordingError('자동 재생 라이브러리가 필요합니다. requirements.txt를 설치해 주세요.', 503) from None
        try:
            self.runtime = sync_playwright().start()
            # Use the installed Edge, with its own temporary profile. Keep audio on.
            self.browser = self.runtime.chromium.launch(
                channel='msedge', headless=True, ignore_default_args=['--mute-audio'])
            self.page = self.browser.new_page(viewport={'width': 760, 'height': 240})
            self.page.goto('https://suno.com/embed/' + self.song_id,
                           wait_until='load', timeout=30000)
            self.page.locator('audio').wait_for(state='attached', timeout=30000)
            self.page.locator('button').first.wait_for(state='visible', timeout=10000)
            self.page.evaluate('''() => {
                // Observe the first ending before Suno's repeat/queue handlers run.
                const marker = document.documentElement.dataset;
                window.addEventListener('playing', event => {
                    if (event.target instanceof HTMLAudioElement) event.target.loop = false;
                }, true);
                window.addEventListener('ended', event => {
                    if (!(event.target instanceof HTMLAudioElement)) return;
                    marker.sunoManagerEnded = '1';
                    marker.sunoManagerEndTime = String(event.target.currentTime);
                    event.stopImmediatePropagation();
                    event.target.pause();
                }, true);
            }''')
        except Exception:
            raise RecordingError('Suno 자동 플레이어를 준비하지 못했습니다. Microsoft Edge 설치와 인터넷 연결을 확인하세요.', 503) from None

    def play(self):
        try:
            # A normal click lets Suno load and decode its own playback stream.
            self.page.locator('button').first.click(timeout=10000)
            try:
                self.page.wait_for_function('''() => {
                    const audio = document.querySelector('audio');
                    return audio && (audio.currentTime > 0 || audio.src.startsWith('blob:'));
                }''', timeout=15000)
            except Exception:
                state = self.state()
                if not state['playing'] and state['current_time'] == 0:
                    # The static HTML can appear before Suno attaches its click handler.
                    self.page.locator('button').first.click(timeout=10000)
        except Exception:
            raise RecordingError('Suno 재생을 시작하지 못했습니다. 잠시 후 다시 시도하세요.', 503) from None

    def state(self):
        try:
            return self.page.locator('audio').evaluate('''audio => ({
                playing: !audio.paused,
                ended: audio.ended || document.documentElement.dataset.sunoManagerEnded === '1',
                current_time: document.documentElement.dataset.sunoManagerEnded === '1'
                    ? Number(document.documentElement.dataset.sunoManagerEndTime) : audio.currentTime,
                ready_state: audio.readyState,
                duration: Number.isFinite(audio.duration) ? audio.duration : null,
                error: audio.error ? audio.error.code : null
            })''', timeout=3000)
        except Exception:
            raise RecordingError('Suno 플레이어 연결이 종료되었습니다. 다시 녹음해 주세요.', 503) from None

    def close(self):
        # Closing this session also stops its sound. Never touch the user's browser.
        for resource in (self.browser, self.runtime):
            if resource:
                try:
                    resource.close() if resource is self.browser else resource.stop()
                except Exception:
                    pass
