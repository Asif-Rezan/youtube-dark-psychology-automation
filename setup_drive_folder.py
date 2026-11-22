"""Create the dedicated, owner-only Drive folder using this project's Drive OAuth token."""
import json
import os
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


def main():
    token = os.environ.get('DRIVE_TOKEN_JSON')
    if not token:
        raise RuntimeError('DRIVE_TOKEN_JSON is required')
    drive = build('drive', 'v3', credentials=Credentials.from_authorized_user_info(
        json.loads(token)), cache_discovery=False)
    folder = drive.files().create(body={
        'name': 'Grow with Rezan Automation',
        'mimeType': 'application/vnd.google-apps.folder',
        'appProperties': {'grow_with_rezan_root': 'v1'},
    }, fields='id').execute()['id']
    permissions = drive.permissions().list(fileId=folder,
        fields='permissions(type,role)', pageSize=100).execute().get('permissions', [])
    if any(item.get('role') != 'owner' for item in permissions):
        raise RuntimeError('New Drive folder is not owner-only')
    print('Set DRIVE_FOLDER_ID to the new dedicated folder ID: ' + folder)


if __name__ == '__main__':
    main()
