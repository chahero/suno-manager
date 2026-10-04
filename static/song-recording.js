const songRecording = (() => {
    const dialog = document.getElementById('song-recording-dialog');
    const player = document.getElementById('song-recording-player');
    const deviceSelect = document.getElementById('song-recording-device');
    const startButton = document.getElementById('start-song-recording');
    const stopButton = document.getElementById('stop-song-recording');
    const closeButton = document.getElementById('close-song-recording');
    let song = null, current = {state:'idle'}, devices = [], recordings = [];
    let busy = false, polling = false, lastFinished = null, deviceError = null;
    const active = () => ['starting', 'recording', 'stopping'].includes(current.state);
    const forSong = () => song && current.song_id === song.id;
    const seconds = value => {
        const total = Math.floor(value || 0);
        return String(Math.floor(total / 60)).padStart(2,'0') + ':' + String(total % 60).padStart(2,'0');
    };
    const message = (text, error = false) => {
        const element = document.getElementById('song-recording-message');
        element.textContent = text; element.style.color = error ? '#fca5a5' : '';
    };
    const post = (url, data) => apiJSON(url, {
        method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)
    });
    const pausePreviews = () => {
        document.querySelectorAll('#song-recording-results audio').forEach(audio => audio.pause());
        document.getElementById('audio-player').pause();
        document.getElementById('player').hidden = true;
    };
    function stopPlayback() {
        player.pause();
    }
    function renderState() {
        const running = active(), own = forSong();
        const labels = {idle:'대기 중',starting:'자동 재생 준비 중',recording:'● 재생·녹음 중',stopping:'파일 저장 중',completed:'저장 완료',error:'녹음 실패'};
        document.getElementById('song-recording-state').textContent = own ? labels[current.state] : '대기 중';
        document.getElementById('song-recording-clock').textContent = seconds(own ? current.elapsed_seconds : 0);
        const percent = own && running ? Math.min(100,Math.round(Math.sqrt(current.level || 0) * 100)) : 0;
        document.getElementById('song-recording-level').style.width = percent + '%';
        dialog.querySelector('[role=meter]').setAttribute('aria-valuenow',String(percent));
        startButton.disabled = busy || running || !devices.length || !song;
        stopButton.disabled = busy || !own || !['starting','recording'].includes(current.state);
        deviceSelect.disabled = busy || running || !devices.length || !song?.local_audio_url;
        player.controls = !running;
        const playbackTime = song?.local_audio_url ? player.currentTime : current.playback_seconds;
        const playbackDuration = song?.local_audio_url ? player.duration : current.playback_duration;
        document.getElementById('song-playback-progress').textContent = own && running
            ? '곡 재생 ' + seconds(playbackTime) + ' / ' + seconds(playbackDuration) : '';
        document.getElementById('song-recording-duration').disabled = busy || running;
        closeButton.disabled = busy;
        closeButton.textContent = own && running ? '정지하고 닫기' : '닫기';
        document.getElementById('active-song-recording').hidden = !running;
        document.getElementById('active-song-recording-title').textContent = running ? (current.title || '곡') + ' · 녹음 중' : '';
    }
    function renderResults() {
        const container = document.getElementById('song-recording-results'); container.replaceChildren();
        const items = song ? recordings.filter(item => item.song_id === song.id) : [];
        if (!items.length) container.append(node('p','아직 이 곡의 녹음이 없습니다.','small muted'));
        for (const recording of items) {
            const item = document.createElement('div'); item.className = 'song-recording-result';
            const heading = document.createElement('div'); heading.className = 'toolbar';
            const download = node('a','WAV 다운로드','button');
            download.href = '/api/recordings/' + recording.id + '/download';
            heading.append(node('span',new Date(recording.created_at).toLocaleString('ko-KR') + ' · ' + seconds(recording.audio_seconds),'small muted'),
                node('span','','spacer'),download);
            const audio = document.createElement('audio'); audio.controls = true; audio.preload = 'none';
            audio.src = '/api/recordings/' + recording.id + '/audio';
            audio.setAttribute('aria-label',recording.title + ' 녹음 재생');
            audio.addEventListener('play',() => {
                if (active()) { audio.pause(); message('녹음이 끝난 뒤 저장된 파일을 재생하세요.',true); }
            });
            item.append(heading,audio);
            if (recording.stop_reason === 'song-ended') item.append(node('p','곡 종료 감지 · 자동 저장','small muted'));
            if (!recording.has_signal) item.append(node('p','녹음된 소리가 거의 없습니다. 출력 장치를 확인하세요.','small muted'));
            if (recording.overruns) item.append(node('p','오디오 버퍼 지연이 감지됐습니다. 녹음을 재생해 확인하세요.','small muted'));
            container.append(item);
        }
    }
    async function loadRecordings() {
        const data = await apiJSON('/api/recordings'); recordings = data.recordings;
        renderResults(); controller.onChange?.();
    }
    async function finish() {
        stopPlayback(); lastFinished = current.id;
        message(current.state === 'error' ? current.error : current.has_signal
            ? (current.stop_reason === 'song-ended' ? '곡이 끝나 재생과 녹음을 자동으로 정지했습니다. ' : '') + 'WAV를 저장했습니다. 아래에서 재생하거나 다운로드하세요.'
            : '녹음은 저장했지만 소리가 거의 없습니다. 출력 장치를 확인하세요.',
            current.state === 'error' || !current.has_signal);
        await loadRecordings();
    }
    async function poll() {
        if (polling) return;
        polling = true;
        try {
            current = await apiJSON('/api/recordings/status'); renderState();
            if (forSong() && ['completed','error'].includes(current.state) && lastFinished !== current.id) await finish();
        } catch (error) { if (dialog.open) message(error.message,true); }
        finally { polling = false; }
    }
    async function waitForState(states, identifier) {
        const deadline = Date.now() + (states.includes('recording') ? 70000 : 10000);
        do {
            current = await apiJSON('/api/recordings/status'); renderState();
            if (current.id !== identifier) throw new Error('녹음 상태가 변경되었습니다. 현재 녹음을 확인하세요.');
            if (states.includes(current.state)) return;
            if (current.state === 'error') throw new Error(current.error);
            await new Promise(resolve => setTimeout(resolve,100));
        } while (Date.now() < deadline);
        throw new Error('녹음 장치 응답이 늦습니다. 정지하고 저장을 눌러 상태를 확인하세요.');
    }
    async function start() {
        if (busy || active() || !song) return;
        busy = true; renderState(); pausePreviews();
        controller.onChange?.();
        message('녹음을 준비한 뒤 이 곡을 자동으로 재생합니다…');
        player.pause();
        try {
            if (song.local_audio_url) player.currentTime = 0;
            current = await post('/api/recordings/start',{
                device_id:Number(deviceSelect.value),title:song.title || 'Untitled',song_id:song.id,
                duration:Number(document.getElementById('song-recording-duration').value),
                auto_playback:!song.local_audio_url
            });
            await waitForState(['recording'],current.id);
            if (song.local_audio_url) {
                await player.play();
                message('이 곡을 처음부터 재생하며 녹음합니다. 곡이 끝나면 자동으로 저장합니다.');
            } else message('Suno에서 이 곡을 자동 재생하며 녹음합니다. 곡이 끝나면 자동으로 정지하고 저장합니다.');
        } catch (error) {
            if (forSong() && active()) {
                try { current = await post('/api/recordings/' + current.id + '/stop',{}); } catch (_) {}
            }
            stopPlayback(); message(error.message,true);
        } finally { busy = false; renderState(); controller.onChange?.(); }
    }
    async function stop() {
        if (busy || !active() || !forSong()) return;
        busy = true; stopPlayback(); renderState();
        try {
            current = await post('/api/recordings/' + current.id + '/stop',{});
            await waitForState(['completed','error'],current.id);
            await finish();
        } catch (error) { message(error.message,true); }
        finally { busy = false; renderState(); controller.onChange?.(); }
    }
    async function open(selected) {
        if (busy) return false;
        await poll();
        if (active() && current.song_id !== selected.id) {
            showNotice('녹음 중인 곡을 먼저 정지하고 저장해 주세요.',true); return false;
        }
        if (song?.id === selected.id && dialog.open) return true;
        stopPlayback(); pausePreviews(); song = selected;
        document.getElementById('song-recording-title').textContent = selected.title || 'Untitled';
        document.getElementById('song-recording-subtitle').textContent = '이 곡 재생·녹음 · 다운로드 횟수 미사용';
        player.hidden = !selected.local_audio_url;
        document.getElementById('song-remote-playback').hidden = !!selected.local_audio_url;
        if (selected.local_audio_url) player.src = selected.local_audio_url;
        else deviceSelect.value = String((devices.find(item => item.default) || devices[0])?.id || '');
        startButton.textContent = '재생·녹음 시작';
        document.getElementById('song-playback-help').textContent = selected.local_audio_url
            ? '저장된 MP3로 재생합니다. 녹음 시작 시 처음부터 재생하고 곡이 끝나면 자동 저장합니다.'
            : '앱이 Suno 공식 플레이어를 자동으로 재생합니다. 곡 종료를 감지하면 녹음을 자동 저장합니다.';
        message(deviceError || (active() ? '이 곡을 재생하며 녹음하고 있습니다. 곡이 끝나면 자동 저장합니다.' : '재생·녹음 시작을 누르면 이 곡을 처음부터 자동 재생합니다.'),!!deviceError);
        renderResults(); renderState();
        if (!dialog.open) dialog.showModal();
        return true;
    }
    async function playAndRecord(selected) {
        if (await open(selected) && !active()) await start();
    }
    async function close() {
        if (busy) return;
        if (forSong() && active()) await stop();
        if (active()) return;
        stopPlayback(); pausePreviews(); dialog.close();
    }
    async function init() {
        try {
            const data = await apiJSON('/api/recordings/devices'); devices = data.devices;
            deviceSelect.replaceChildren();
            for (const device of devices) {
                const option = node('option',device.name + (device.default ? ' · 기본 장치' : ''));
                option.value = String(device.id); deviceSelect.append(option);
            }
            deviceSelect.value = String((devices.find(item => item.default) || devices[0]).id);
        } catch (error) {
            devices = []; deviceSelect.replaceChildren(node('option','녹음 장치를 사용할 수 없습니다.'));
            deviceError = error.message; message(deviceError,true);
        }
        await poll();
        try { await loadRecordings(); } catch (error) { showNotice(error.message,true); }
        renderState();
    }
    startButton.addEventListener('click',start);
    stopButton.addEventListener('click',stop);
    closeButton.addEventListener('click',close);
    dialog.addEventListener('cancel',event => { event.preventDefault(); close(); });
    player.addEventListener('ended',() => { if (active() && forSong()) stop(); });
    player.addEventListener('error',() => {
        message('이 곡의 오디오를 재생하지 못했습니다.',true);
        if (active() && forSong() && !busy) stop();
    });
    document.getElementById('resume-song-recording').addEventListener('click',() => {
        if (current.song_id) open({id:current.song_id,title:current.title});
        else showNotice('이전 일반 녹음이 진행 중입니다. 녹음이 종료된 후 곡별 녹음을 이용하세요.',true);
    });
    // Leaving the library also ends playback; request a save of its recording.
    window.addEventListener('pagehide',() => {
        if (active() && current.song_id) navigator.sendBeacon('/api/recordings/' + current.id + '/stop',new Blob(['{}'],{type:'application/json'}));
    });
    setInterval(() => { if (!document.hidden && (dialog.open || active())) poll(); },500);
    const controller = {open,playAndRecord,init,isActive:active,isBusy:() => busy,songId:() => current.song_id,
        savedFor:id => recordings.filter(item => item.song_id === id),onChange:null};
    return controller;
})();
window.songRecording = songRecording;
