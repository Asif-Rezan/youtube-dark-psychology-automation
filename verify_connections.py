"""Read-only verification of account identity, private folder, and refresh tokens."""
import json
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from storage import Store, required
from pipeline import youtube_client


def verify():
    required('EXPECTED_CHANNEL_ID')
    for name in ('YOUTUBE_TOKEN_JSON','DRIVE_TOKEN_JSON'):
        credentials = Credentials.from_authorized_user_info(json.loads(required(name)))
        if name == 'YOUTUBE_TOKEN_JSON' and not credentials.has_scopes(['https://www.googleapis.com/auth/youtube.force-ssl']):
            raise RuntimeError('YouTube scheduling update permission missing')
        if not credentials.refresh_token:
            raise RuntimeError('Offline refresh token missing')
        credentials.refresh(Request())
    client = youtube_client()
    channel = client.channels().list(part='id,snippet',mine=True).execute()['items'][0]
    if channel['id'] != required('EXPECTED_CHANNEL_ID'):
        raise RuntimeError('Destination channel identity mismatch')
    store = Store()
    folder = store.client.files().get(fileId=store.folder,fields='id,name,trashed').execute()
    if folder.get('trashed'):
        raise RuntimeError('Drive folder is trashed')
    print(json.dumps({'channel':channel['snippet']['title'],'handle':channel['snippet'].get('customUrl',''),
        'channel_id':channel['id'],'drive_folder':folder['name'],'private_folder_verified':True,
        'both_refresh_tokens_verified':True,'uploads_performed':False}))


if __name__=='__main__':
    try:
        verify()
    except Exception as error:
        safe_messages = {
            'Missing configuration: EXPECTED_CHANNEL_ID',
            'YouTube scheduling update permission missing',
            'Offline refresh token missing',
            'Destination channel identity mismatch',
            'Drive folder is trashed',
        }
        detail = str(error) if type(error) is RuntimeError and str(error) in safe_messages else type(error).__name__
        print('Connection verification failed: '+detail+'. No credentials printed.')
        raise SystemExit(1)
