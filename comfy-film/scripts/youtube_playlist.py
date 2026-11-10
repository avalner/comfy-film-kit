"""Add a video to the requested playlist, checking ownership and duplicates."""
import argparse
import json
import sys

def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('token','dependencies','video','playlist','expected-channel'):
        p.add_argument('--'+name, required=True)
    a=p.parse_args()
    sys.path.insert(0,a.dependencies)
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    c=Credentials.from_authorized_user_file(a.token)
    if not c.valid and c.refresh_token: c.refresh(Request())
    y=build('youtube','v3',credentials=c,cache_discovery=False)
    playlist=y.playlists().list(part='snippet',id=a.playlist).execute(num_retries=0).get('items',[])
    video=y.videos().list(part='snippet',id=a.video).execute(num_retries=0).get('items',[])
    if not playlist or not video or any(x['snippet']['channelId']!=a.expected_channel for x in playlist+video):
        raise ValueError('Video/playlist missing or channel mismatch')
    existing=[]
    page=None
    while True:
        response=y.playlistItems().list(part='snippet,contentDetails',playlistId=a.playlist,maxResults=50,pageToken=page).execute(num_retries=0)
        existing += [x for x in response.get('items',[]) if x.get('contentDetails',{}).get('videoId')==a.video]
        page=response.get('nextPageToken')
        if not page:break
    item=existing[0] if existing else y.playlistItems().insert(part='snippet',body={
        'snippet':{'playlistId':a.playlist,'resourceId':{'kind':'youtube#video','videoId':a.video}}
    }).execute(num_retries=0)
    check=y.playlistItems().list(part='snippet,contentDetails',id=item['id']).execute(num_retries=0).get('items',[])
    verified=any(x.get('contentDetails',{}).get('videoId')==a.video and x.get('snippet',{}).get('playlistId')==a.playlist for x in check)
    print(json.dumps({'added':verified,'already_present':bool(existing),'playlist':playlist[0]['snippet']['title'],
                      'playlist_item_id':item['id'],'video_id':a.video}))
    return 0 if verified else 2

if __name__=='__main__':
    sys.exit(main())
