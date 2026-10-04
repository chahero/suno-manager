"""Download from Suno without browser clicks: python download.py --help."""
import argparse
import os
from pathlib import Path
import sys

from dotenv import load_dotenv
from suno_api import SunoAPI, SunoAPIError, validate_song_id


def main(argv=None):
    root = Path(__file__).resolve().parent
    load_dotenv(root / '.env')
    parser = argparse.ArgumentParser(description='Suno MP3 다운로드 (브라우저 불필요)')
    parser.add_argument('song_ids', nargs='*', help='곡 URL 끝에 있는 UUID')
    parser.add_argument('--list', action='store_true', help='곡 ID / 잠금 해제 상태 / 제목만 조회')
    parser.add_argument('--all', action='store_true', help='전체 라이브러리 다운로드; 기본은 이미 잠금 해제된 곡만')
    parser.add_argument('--unlock', action='store_true', help='새 곡 다운로드도 승인 (계정 다운로드 한도 사용)')
    parser.add_argument('--output', type=Path, default=root / os.getenv('DOWNLOAD_FOLDER', 'downloads'), help='저장 폴더')
    args = parser.parse_args(argv)
    if not args.song_ids and not args.all and not args.list:
        parser.error('곡 ID, --list 또는 --all을 지정해 주세요.')
    if args.song_ids and (args.all or args.list):
        parser.error('곡 ID와 --all / --list는 함께 사용할 수 없습니다.')
    if args.list and (args.all or args.unlock):
        parser.error('--list는 다른 작업 옵션과 함께 사용할 수 없습니다.')
    client = SunoAPI()
    failed = 0
    try:
        songs = client.get_all_songs() if args.all or args.list else []
        if args.list:
            for song in songs:
                state = 'unlocked' if song.get('is_download_unlocked') is True else 'locked'
                print(f"{song['id']}\t{state}\t{song.get('title') or 'Untitled'}")
            return 0
        if not songs and args.song_ids:
            for song_id in dict.fromkeys(args.song_ids):
                song = client.get_song(validate_song_id(song_id))
                if not song:
                    raise SunoAPIError('곡을 찾을 수 없습니다.', 404, 'not_found')
                songs.append(song)
        skipped = 0
        for song in songs:
            if args.all and not args.unlock and song.get('is_download_unlocked') is not True:
                skipped += 1
                continue
            try:
                # Same UUID cache as the web player; human-readable titles are ZIP/attachment names.
                path = args.output / f"{validate_song_id(song['id'])}.mp3"
                client.download_song(song['id'], str(path), unlock=args.unlock)
                print(f'Saved: {path.resolve()} ({song.get("title") or "Untitled"})')
            except SunoAPIError as error:
                failed += 1
                print(f"Failed {song['id']}: {error}", file=sys.stderr)
                if error.status_code == 401 or error.code == 'authorization_uncertain':
                    return 1
        if skipped:
            print(f'Skipped locked songs: {skipped} (--unlock 사용 시 새 다운로드 한도 사용)')
        return 1 if failed else 0
    except (SunoAPIError, ValueError, OSError) as error:
        print(str(error) if not isinstance(error, OSError) else '저장 폴더에 파일을 쓸 수 없습니다.', file=sys.stderr)
        return 1
    finally:
        client.close()


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    raise SystemExit(main())
