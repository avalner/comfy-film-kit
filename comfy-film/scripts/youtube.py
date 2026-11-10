"""YouTube publishing entrypoint for comfy-film. Uses local OAuth, no intermediary."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def service(config):
    sys.path.insert(0, config['dependencies'])
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    c = Credentials.from_authorized_user_file(config['token'])
    if not c.valid and c.refresh_token:
        c.refresh(Request())
        Path(config['token']).write_text(c.to_json(), encoding='utf-8')
    api = build('youtube', 'v3', credentials=c, cache_discovery=False)
    channels = api.channels().list(part='snippet', mine=True).execute(num_retries=0).get('items', [])
    if config['channel_id'] not in [x['id'] for x in channels]:
        raise ValueError('Channel mismatch; operation refused')
    return api, [{'id': x['id'], 'title': x['snippet']['title']} for x in channels]


def helper(name, config, extra):
    command = [sys.executable, str(HERE / name), '--token', config['token'],
               '--dependencies', config['dependencies'], '--expected-channel', config['channel_id'], *extra]
    return subprocess.call(command)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', default=str(HERE.parent / 'assets' / 'youtube.json'))
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('account')
    sub.add_parser('playlists')
    auth = sub.add_parser('auth')
    auth.add_argument('--manage-playlists', action='store_true')
    upload = sub.add_parser('upload')
    upload.add_argument('--project', required=True)
    upload.add_argument('--file', required=True)
    upload.add_argument('--metadata', required=True)
    upload.add_argument('--approved', action='store_true', help='Use only after actual user authorization')
    status = sub.add_parser('status')
    status.add_argument('--project')
    status.add_argument('--video')
    status.add_argument('--wait', type=float, default=0, help='Seconds to wait for processing; never uploads')
    add = sub.add_parser('add-playlist')
    add.add_argument('--video', required=True)
    add.add_argument('--playlist', required=True)
    args = p.parse_args(argv)
    config = read(args.config)
    if args.command == 'auth':
        return helper('youtube_auth.py', config, ['--client-secrets', config['client_secrets']] +
                      (['--manage-playlists'] if args.manage_playlists else []))
    if args.command == 'upload':
        if not args.approved:
            raise ValueError('Explicit approval required; upload not started')
        root = Path(args.project).resolve()
        if not (root / 'film.json').is_file():
            raise ValueError('Expected a comfy-film project')
        folder = root / '.pipeline'
        folder.mkdir(exist_ok=True)
        return helper('youtube_upload.py', config, ['--file', args.file, '--metadata', args.metadata,
                      '--state', str(folder / 'youtube-upload.json')])
    if args.command == 'add-playlist':
        playlist = config.get('known_playlists', {}).get(args.playlist, args.playlist)
        return helper('youtube_playlist.py', config, ['--video=' + args.video, '--playlist', playlist])
    api, channels = service(config)
    if args.command == 'account':
        print(json.dumps({'authorized': True, 'channels': channels, 'expected_channel_verified': True}))
    elif args.command == 'playlists':
        page = None
        items = []
        while True:
            result = api.playlists().list(part='snippet,status', mine=True, maxResults=50, pageToken=page).execute(num_retries=0)
            items += [{'id': x['id'], 'title': x['snippet']['title']} for x in result.get('items', [])]
            page = result.get('nextPageToken')
            if not page:
                break
        print(json.dumps({'playlists': items}))
    elif args.command == 'status':
        video = args.video
        if not video and args.project:
            journal = read(Path(args.project) / '.pipeline' / 'youtube-upload.json')
            video = journal.get('video_id')
        if not video:
            raise ValueError('No video ID; inspect existing journal, do not re-upload')
        deadline = time.monotonic() + max(0, args.wait)
        while True:
            result = api.videos().list(part='snippet,status,processingDetails', id=video).execute(num_retries=0).get('items', [])
            if not result:
                raise ValueError('Video not found')
            v = result[0]
            if v['snippet']['channelId'] != config['channel_id']:
                raise ValueError('Video belongs to another channel')
            processing = v.get('processingDetails', {}).get('processingStatus')
            if processing != 'processing' or time.monotonic() >= deadline:
                print(json.dumps({'video_id': video, 'url': 'https://www.youtube.com/watch?v=' + video,
                                  'title': v['snippet']['title'], 'status': v['status'], 'processing': processing}))
                break
            time.sleep(min(5, max(.1, deadline - time.monotonic())))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as error:
        # No tokens, OAuth callback URLs or resumable session URLs in console output.
        print(json.dumps({'error_type': type(error).__name__,
                          'message': 'YouTube operation stopped. Check auth/config and existing publication journal before retrying.'}))
        sys.exit(1)
