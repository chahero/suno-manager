# SUNO Manager (Unofficial)

English | [한국어](README.md)

An **unofficial local Flask app** for viewing your Suno library, saving authorized MP3 files and recording Windows playback as WAV.
It uses Suno's internal web API and embedded player. It is not an official Suno product or API SDK.

> **Unofficial playback recording**
>
> Automatic playback recording is an **unofficial method, not a storage workflow officially supported or recommended by Suno.**
> As checked on 2026-10-05, the “Permitted Commercial Use” section of [Suno's terms](https://suno.com/terms)
> prohibits obtaining copies outside Suno-provided download channels and **explicitly prohibits recording and stream ripping**.
> Technical validation does not imply permission from Suno. Use Suno-provided download channels to save music.

On 2026-10-04, a real account verified listing, direct MP3 download for an already unlocked song,
ZIP download, and playback from the local cache. New authorization is implemented and mock-tested;
no additional song was unlocked during validation.

## Supported features

- Token login; library, song details, lyrics, search, sorting and pagination.
- MP3 download and ZIP downloads of up to 50 selected songs, with a failure manifest.
- A CLI that works without opening a browser or starting the Flask server.
- Playback of downloaded MP3 files; other tracks use Suno's official embedded player.
- Live account credits and remaining download allowance.
- Unofficial per-song automatic Windows playback recording, WAV playback and download in the library.

Suno source WAV/M4A/video export is not implemented.

## Screenshots

Captured from the current code on 2026-10-05. These show the local library fallback after the Suno token expired,
with recordings saved during validation on 2026-10-04. No tokens or authorization headers appear in the images.

**Library — per-song playback recording and saved results**

![Library with per-song playback recording and saved-recording buttons](docs/images/library.jpg)

**Song dialog — playback and download of a WAV automatically saved at the song ending**

![Saved WAV marked with automatic song-ending detection and a download button](docs/images/song-recordings.jpg)

## Setup

Requires Python 3.10+. The validated environment is Windows with Python 3.11.
**Playback recording is Windows-only** and requires Microsoft Edge and an available speaker/headphone output device.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Enter a token on the web login page or set `SUNO_BEARER_TOKEN` in `.env` (with or without the Bearer prefix).
The CLI uses the token from `.env`.
In your logged-in Suno browser, open Developer Tools → Network → reload → `feed/v3` →
Headers → Request Headers → `authorization`.

Use a random `SECRET_KEY`, `DEBUG=False`, and `HOST=127.0.0.1`.
Run `.\.venv\Scripts\python.exe main.py` or `start.bat`, then open
[the local app](http://127.0.0.1:5000). `start.bat` prefers the project virtual environment.
If you change `PORT`, use the same port in the app URL.

Expired tokens return an explicit 401. Refresh the token through the login page, or edit `.env`
and restart the server. UI tokens are stored in server memory, not the browser session cookie,
and are removed on logout or server restart. Logging out prevents that browser from falling back
to the environment token.

## Unofficial automatic playback recording

This feature is for technical verification of Windows output capture. Read the **Unofficial playback recording** notice above first.

Open [the library](http://127.0.0.1:5000/library) and click **재생·녹음** on a song.
Its dialog includes playback, recording controls and WAV recordings belonging to that song.
It captures Windows speaker/headphone output through WASAPI loopback, rather than a microphone.
`PyAudioWPatch` and `playwright` are installed on Windows by `requirements.txt`. Microsoft Edge is required. Run the server locally in one process.

1. Click the song's **재생·녹음** button once in the library.
2. The app prepares capture and automatically plays the song from the beginning.
3. The actual song ending stops playback and recording and automatically saves a WAV.
4. Play or download the result under **이 곡의 녹음**. **녹음 N개 보기** opens existing results without starting a new session.

| Save method | Result | Suno download allowance |
| --- | --- | --- |
| MP3 download | An MP3 file prepared by Suno | Used when a new download is authorized |
| Unofficial playback recording | A WAV captured from Windows output | No download or authorization API call |

Cached MP3s play in the current browser. Other songs use Suno's official player in an isolated temporary Edge session.
**The player is provided by Suno; its automatic controls and recording are this project's unofficial implementation.**
The session has no separate visible window or access to the user's browser profile. Online automatic playback records the Windows default output device. The full song must be playable in Suno's embed. Playback that makes no progress for 30 seconds fails and cleans up its session.

A duration of 0 means stop at the song ending; 1–3600 also sets a capture time limit.
All sessions stop after at most one hour. Closing the dialog or pressing Esc stops and saves recording.
Leaving the library also sends a stop/save request. If abrupt browser closure prevents delivery,
return to the library's active-recording control or wait for automatic stop. Server shutdown also ends recording.
WAVs use the device's native sample rate, 16-bit PCM and up to two channels. WAVs and JSON metadata
persist in `DOWNLOAD_FOLDER/recordings/` and remain available after a server restart.
The `song_id` field associates results with the correct song, even when titles are identical.
When the Suno token expires, the library falls back to songs associated with local MP3s and recordings.
Use **새 토큰으로 로그인** to restore the full online library and download authorization.

Recording does not call Suno's download or authorization APIs, so it does not consume their allowance.
Capture takes real time and includes notifications and other apps playing through the selected device.
Saving as WAV does not improve the source audio quality. Changes to Suno's player may require updating the automatic controls.

## Download without clicking

```powershell
# List UUID, unlocked/locked status and title
.\.venv\Scripts\python.exe download.py --list

# Already unlocked song; ID is the last UUID in its Suno URL
.\.venv\Scripts\python.exe download.py d4865d3e-d7c0-4a05-afee-fa0cfe2cd116

# Back up already unlocked library songs; skip locked songs
.\.venv\Scripts\python.exe download.py --all

# Explicitly authorize a new download, using the account allowance
.\.venv\Scripts\python.exe download.py SONG_UUID --unlock

# Custom output folder
.\.venv\Scripts\python.exe download.py SONG_UUID --output "D:\Music"
```

Multiple UUIDs can be supplied. Files are saved as `UUID.mp3` in `DOWNLOAD_FOLDER` by default.
Using the same folder as Flask makes CLI downloads available in the local player.
Valid existing MP3 files are reused. Failures exit with code 1.
`--all --unlock` authorizes each locked song, so use it only when intended.

## Current download flow

Old direct `audio_url` downloads can now return `/api/forbidden` and HTTP 403.
The client instead checks `GET /api/clip/{id}`, optionally sends a single
`POST /api/download/authorize`, then polls `GET /api/download/clip/{id}?format=mp3`.
The returned HTTPS file URL is fetched without a Suno bearer token.
The file size and MP3 header are checked before an atomic save.

This follows account permissions and [Suno's download allowance](https://help.suno.com/en/articles/13876865).
Re-downloading a previously downloaded song does not use another allowance.
Ambiguous authorization responses are not automatically retried. Check unlock status and usage before retrying.
An approval may have consumed an allowance even if file preparation or transfer later fails.
ZIPs contain `download-results.json` with successful and failed song IDs. Sanitized attachment/ZIP names
avoid Windows filename errors, while cache files use UUID names.

## Local API

- `POST /login` with `{"token":"..."}`; `GET /api/auth/check`.
- `GET /api/billing/info`: credits, plan, remaining downloads.
- `GET /api/songs?cursor=...` (URL-encode cursors); `GET /api/songs/{id}`.
- `GET /api/songs/local`: locally cached/recorded songs without a token, localhost only.
- `GET /api/songs/{id}/download`: already unlocked MP3 only.
- `POST /api/songs/{id}/download` with `{"unlock":false}`: set true to authorize a new download.
- `POST /api/songs/batch-download` with `{"song_ids":["UUID"],"unlock":false}`.
- `GET /api/songs/{id}/audio`: cached MP3 with range support.
- `GET /api/recordings/devices`; `GET /api/recordings/status`.
- `POST /api/recordings/start` with `{"device_id":25,"title":"Recording","duration":0,"song_id":"UUID","auto_playback":true}`; use the default output device for automatic Suno playback. With false, the UI handles cached MP3 playback.
- `POST /api/recordings/{id}/stop` with `{}`.
- `GET /api/recordings?song_id=UUID`: saved sessions for one song; omit the filter to list all.
- `GET /api/recordings/{id}/audio` or `/download`: WAV playback/download with range support.

Recording APIs accept only localhost requests and do not require Suno authentication.

## Validation and limitations

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests mock Suno requests and do not unlock real songs.
They cover authentication, pagination, explicit authorization, uncertain approval handling,
invalid audio, partial ZIP results and server-side token storage/logout.
Recording tests cover loopback filtering, exact PCM/WAV data, duplicate starts, automatic stop,
device failure, local access restrictions and WAV playback/download without a Suno token.
Tests also cover song association/filtering, legacy recording links and cached MP3 playback independent of live Suno authentication.
A real downloaded MP3 was also checked with ffprobe and a full ffmpeg decode.
An actual UI session recorded a test tone into 8.256 seconds of stereo 48kHz WAV;
audio signal, browser playback and a full decode were verified.
The per-song UI was checked with real cached MP3 and Suno official-player sources.
A single click automatically played an entire uncached 128.6-second song and saved a stereo 48kHz WAV when the song ended (130.176 seconds including preparation/output buffering). Browser playback, exact download bytes, range responses and full ffmpeg decoding passed.
Tests cover capture-before-play ordering, song endings and repeat boundaries, manual stop and browser/temporary-file cleanup on failures.
ffmpeg is not required to run the application.

Designed for personal, local, single-process use. Suno's internal web API can change;
automatic token refresh is not implemented. `.env` and `downloads/` are ignored by Git.
The current endpoints were cross-checked against [sunox's public implementation](https://github.com/ctykwz/sunox/blob/main/src/api/download.rs).
