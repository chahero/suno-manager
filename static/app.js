function node(tag, text, className = '') {
    const element = document.createElement(tag);
    element.textContent = text;
    element.className = className;
    return element;
}

function action(text, callback) {
    const button = node('button', text);
    button.type = 'button';
    button.addEventListener('click', callback);
    return button;
}

function showNotice(message, error = false) {
    const notice = document.getElementById('notice');
    notice.textContent = message;
    notice.classList.toggle('error', error);
    notice.hidden = false;
}

async function apiJSON(url, options) {
    const response = await fetch(url, options);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || '요청에 실패했습니다.');
    return data;
}

async function downloadFile(url, payload, fallbackName) {
    const response = await fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)});
    if (!response.ok) {
        const data = await response.json();
        const failures = (data.failed || []).map(item => item.id + ': ' + item.error).join('\n');
        throw new Error((data.error || '다운로드 실패') + (failures ? '\n' + failures : ''));
    }
    const blob = await response.blob(), objectURL = URL.createObjectURL(blob);
    const link = document.createElement('a');
    const disposition = response.headers.get('Content-Disposition') || '';
    const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i);
    const plain = disposition.match(/filename="([^"]+)"|filename=([^;]+)/i);
    let filename = fallbackName;
    try { filename = encoded ? decodeURIComponent(encoded[1]) : plain ? (plain[1] || plain[2]).trim() : filename; } catch (_) {}
    link.href = objectURL; link.download = filename; document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(objectURL), 1000);
    return {downloaded: Number(response.headers.get('X-Downloaded-Count') || 1), failed: Number(response.headers.get('X-Failed-Count') || 0)};
}

async function loadBilling() {
    const status = document.getElementById('connection-status');
    try {
        const data = await apiJSON('/api/billing/info');
        document.getElementById('plan-name').textContent = data.plan_name;
        document.getElementById('credits-count').textContent = (data.credits ?? '—').toLocaleString() + ' 크레딧';
        document.getElementById('downloads-count').textContent = data.downloads_remaining ?? '확인 불가';
        status.textContent = 'Suno 연결됨';
        document.getElementById('refresh-token-link').hidden = true;
    } catch (error) {
        status.textContent = '연결 확인 실패';
        document.getElementById('refresh-token-link').hidden = false;
        document.getElementById('plan-name').textContent = '계정 확인 실패';
        document.getElementById('credits-count').textContent = '— 크레딧';
        document.getElementById('downloads-count').textContent = '—';
        showNotice(error.message, true);
    }
}

function showLyrics(song) {
    document.getElementById('lyrics-title').textContent = song.title || '가사';
    document.getElementById('lyrics-text').textContent = song.metadata?.prompt || '저장된 가사가 없습니다.';
    document.getElementById('lyrics-dialog').showModal();
}

async function playLocal(song) {
    if (window.songRecording?.isActive()) {
        showNotice('녹음 중인 곡을 먼저 정지하고 저장해 주세요.', true); return;
    }
    const audio = document.getElementById('audio-player');
    audio.src = song.local_audio_url;
    document.getElementById('player-title').textContent = song.title || 'Untitled';
    document.getElementById('player').hidden = false;
    try { await audio.play(); } catch (_) { showNotice('오디오를 재생하지 못했습니다. 연결 상태를 확인해 주세요.', true); }
}

document.getElementById('close-player').addEventListener('click', () => {
    const audio = document.getElementById('audio-player'); audio.pause(); audio.removeAttribute('src'); audio.load();
    document.getElementById('player').hidden = true;
});
document.getElementById('close-lyrics').addEventListener('click', () => document.getElementById('lyrics-dialog').close());
document.getElementById('audio-player').addEventListener('error', () => showNotice('로컬 MP3를 불러오지 못했습니다. 다시 로그인하거나 다운로드해 주세요.', true));
if (document.getElementById('credits-count')) loadBilling();
