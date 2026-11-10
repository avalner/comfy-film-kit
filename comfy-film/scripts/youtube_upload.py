"""Upload one approved video directly to YouTube with a durable duplicate guard."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys


def write(path, value):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, indent=2), encoding='utf-8')
    os.replace(tmp, path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('token', 'dependencies', 'file', 'metadata', 'state', 'expected-channel'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    sys.path.insert(0, args.dependencies)
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from googleapiclient.errors import HttpError

    source, journal = Path(args.file), Path(args.state)
    meta = json.loads(Path(args.metadata).read_text(encoding='utf-8-sig'))
    if not source.is_file() or not meta.get('title') or len(meta['title']) > 100:
        raise ValueError('Missing video or invalid title')
    if journal.exists():
        old = json.loads(journal.read_text(encoding='utf-8'))
        print(json.dumps({'existing_attempt': True, 'status': old.get('status'),
                          'video_id': old.get('video_id'),
                          'message': 'No duplicate upload attempted. Inspect or recover existing attempt.'}), flush=True)
        return 2
    if not isinstance(meta.get('madeForKids'), bool) or not isinstance(meta.get('containsSyntheticMedia'), bool):
        raise ValueError('Explicit madeForKids and containsSyntheticMedia booleans required')
    if meta.get('privacyStatus') not in ('public', 'unlisted', 'private'):
        raise ValueError('Explicit privacyStatus required')
    if not isinstance(meta.get('description'), str) or len(meta['description']) > 5000:
        raise ValueError('Invalid description')
    if '<' in meta['title'] or '>' in meta['title']:
        raise ValueError('Invalid title characters')
    digest = hashlib.sha256()
    with source.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            digest.update(chunk)
    fingerprint = digest.hexdigest()
    credentials = Credentials.from_authorized_user_file(args.token)
    if not credentials.valid and credentials.refresh_token:
        credentials.refresh(Request())
        Path(args.token).write_text(credentials.to_json(), encoding='utf-8')
    youtube = build('youtube', 'v3', credentials=credentials, cache_discovery=False)
    channels = youtube.channels().list(part='snippet', mine=True).execute(num_retries=0)
    if args.expected_channel not in [c['id'] for c in channels.get('items', [])]:
        raise ValueError('Authorized channel does not match requested channel; upload refused')
    record = {'status': 'submitting', 'source_sha256': fingerprint,
              'channel_id': args.expected_channel, 'title': meta['title']}
    # Persist uncertainty before any upload call, so re-running cannot duplicate it.
    journal.parent.mkdir(parents=True, exist_ok=True)
    with journal.open('x', encoding='utf-8') as stream:
        json.dump(record, stream, indent=2)
    body = {'snippet': {'title': meta['title'], 'description': meta['description'],
                        'tags': meta.get('tags', []), 'categoryId': str(meta.get('categoryId', '1')),
                        'defaultLanguage': meta.get('language', 'en')},
            'status': {'privacyStatus': meta['privacyStatus'], 'selfDeclaredMadeForKids': meta['madeForKids'],
                       'containsSyntheticMedia': meta['containsSyntheticMedia']}}
    request = youtube.videos().insert(part='snippet,status', body=body,
        media_body=MediaFileUpload(str(source), mimetype='video/mp4', chunksize=8*1024*1024,
                                   resumable=True), notifySubscribers=meta.get('notifySubscribers', True))
    try:
        result = None
        while result is None:
            progress, result = request.next_chunk(num_retries=0)
            if request.resumable_uri:
                record['resumable_uri'] = request.resumable_uri
                write(journal, record)
            if progress:
                print(json.dumps({'upload_percent': round(progress.progress()*100)}), flush=True)
    except Exception as error:
        record['status'] = 'uncertain'
        record['error_type'] = type(error).__name__
        if isinstance(error, HttpError):
            record['http_status'] = error.resp.status
            try:
                detail = json.loads(error.content).get('error', {})
                record['reasons'] = [e.get('reason') for e in detail.get('errors', [])]
                record['message'] = detail.get('message')
            except ValueError:
                pass
        write(journal, record)
        print(json.dumps({k:v for k,v in record.items() if k not in ('resumable_uri',)}, ensure_ascii=True), flush=True)
        return 1
    record.update(status='uploaded', video_id=result['id'],
                  url='https://www.youtube.com/watch?v=' + result['id'],
                  youtube_status=result.get('status', {}))
    record.pop('resumable_uri', None)
    write(journal, record)
    print(json.dumps(record, ensure_ascii=True), flush=True)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as error:
        print(json.dumps({'error_type': type(error).__name__,
                          'message': 'Operation stopped; inspect the publication journal before retrying.'}), flush=True)
        sys.exit(1)
