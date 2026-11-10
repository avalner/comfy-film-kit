"""Authorize local YouTube uploads and verify channel; never uploads a video."""
import argparse
import json
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--client-secrets', required=True)
    parser.add_argument('--token', required=True)
    parser.add_argument('--dependencies', required=True)
    parser.add_argument('--expected-channel', required=True)
    parser.add_argument('--manage-playlists', action='store_true')
    args = parser.parse_args()
    sys.path.insert(0, args.dependencies)
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request, AuthorizedSession
    from google.auth.exceptions import RefreshError

    scopes = ['https://www.googleapis.com/auth/youtube.upload',
              'https://www.googleapis.com/auth/youtube.readonly']
    if args.manage_playlists:
        scopes.append('https://www.googleapis.com/auth/youtube.force-ssl')
    token = Path(args.token)
    credentials = None
    if token.exists():
        credentials = Credentials.from_authorized_user_file(str(token), scopes)
        saved_scopes = json.loads(token.read_text(encoding='utf-8')).get('scopes', [])
        if not set(scopes).issubset(saved_scopes):
            credentials = None
        if credentials and credentials.expired and credentials.refresh_token:
            try:
                credentials.refresh(Request())
            except RefreshError:
                credentials = None
    if not credentials or not credentials.valid:
        flow = InstalledAppFlow.from_client_secrets_file(args.client_secrets, scopes=scopes,
                                                        autogenerate_code_verifier=True)
        print('Opening Google authorization in the default browser. Select Little Wonder Worlds (@avalner).', flush=True)
        credentials = flow.run_local_server(host='localhost', bind_addr='127.0.0.1', port=0,
            open_browser=True, authorization_prompt_message='',
            success_message='Authorization received. You may close this tab and return to your chat.',
            timeout_seconds=600, prompt='consent', access_type='offline')
    token.parent.mkdir(parents=True, exist_ok=True)
    temp = token.with_suffix('.tmp')
    temp.write_text(credentials.to_json(), encoding='utf-8')
    os.replace(temp, token)
    # Read-only identity check; do not infer channel from the Google email.
    response = AuthorizedSession(credentials).get(
        'https://www.googleapis.com/youtube/v3/channels',
        params={'part': 'snippet', 'mine': 'true'}, timeout=30)
    if response.status_code != 200:
        body = response.json().get('error', {})
        reasons = [e.get('reason') for e in body.get('errors', [])]
        print(json.dumps({'authorized': True, 'channel_verified': False,
                          'http_status': response.status_code, 'reasons': reasons,
                          'message': body.get('message', '')}), flush=True)
        return 2
    channels = [{'id': c['id'], 'title': c['snippet']['title']}
                for c in response.json().get('items', [])]
    verified = any(c['id'] == args.expected_channel for c in channels)
    print(json.dumps({'authorized': True, 'channel_verified': verified,
                      'channels': channels, 'token_saved': True,
                      'refresh_token_available': bool(credentials.refresh_token),
                      'video_uploaded': False}, ensure_ascii=True), flush=True)
    return 0 if verified else 3


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as error:
        # Avoid logging authorization response URLs, codes, or token contents.
        print(json.dumps({'error_type': type(error).__name__,
                          'message': 'Authorization did not complete. Check the browser; no video was uploaded.'}), flush=True)
        sys.exit(1)
