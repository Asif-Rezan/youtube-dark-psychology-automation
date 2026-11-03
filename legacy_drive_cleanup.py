"""Explicit one-time removal of old documentary files, outside the kids folder."""
import argparse
import json
from pathlib import Path
import re
from storage import drive_retry, required

FIELDS = 'id,name,mimeType,parents,trashed,size,md5Checksum,modifiedTime'


def private(client, file_id):
    permissions = drive_retry(lambda: client.permissions().list(
        fileId=file_id, fields='permissions(type,role),nextPageToken', pageSize=100).execute())
    if permissions.get('nextPageToken') or any(p.get('role') != 'owner' for p in permissions.get('permissions', [])):
        raise RuntimeError('Legacy cleanup requires an owner-only folder/file')


def verify_root(client, root):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', root):
        raise ValueError('Invalid project folder ID')
    email = drive_retry(lambda: client.about().get(fields='user(emailAddress)').execute())['user']['emailAddress']
    info = drive_retry(lambda: client.files().get(fileId=root,
        fields='id,mimeType,trashed,appProperties,owners(emailAddress)').execute())
    if (info.get('id') != root or info.get('mimeType') != 'application/vnd.google-apps.folder'
            or info.get('trashed') or info.get('appProperties', {}).get('grow_with_rezan_root') != 'v1'
            or {o.get('emailAddress','').lower() for o in info.get('owners',[])} != {email.lower()}):
        raise RuntimeError('Legacy project folder identity/owner mismatch')
    private(client, root)


def inventory(client, root):
    verify_root(client, root)
    files, folders, token = [], [], None
    while True:
        page = drive_retry(lambda: client.files().list(q=f"'{root}' in parents",
            fields=f'nextPageToken,files({FIELDS})', pageSize=1000, pageToken=token).execute())
        for item in page.get('files', []):
            if item.get('mimeType') == 'application/vnd.google-apps.folder':
                folders.append(item['id'])  # Never traverse/delete the new kids folder.
            else:
                files.append(item)
        token = page.get('nextPageToken')
        if not token:
            return files, folders


def clean(client, root, report_path, apply=False):
    files, folders = inventory(client, root)
    report = dict(mode='delete' if apply else 'audit', candidates=files,
                  preserved_folders=folders, deleted=[], deleted_bytes=0, failed=[], remaining=[])
    def save():
        report_path.parent.mkdir(parents=True, exist_ok=True)
        temp = report_path.with_suffix('.tmp')
        temp.write_text(json.dumps(report, indent=2))
        temp.replace(report_path)
    save()  # Exact inventory before deleting anything.
    if apply:
        for original in files:
            file_id = original['id']
            try:
                live = drive_retry(lambda: client.files().get(fileId=file_id, fields=FIELDS).execute())
                if (live.get('id') != file_id or root not in live.get('parents', [])
                        or live.get('mimeType') == 'application/vnd.google-apps.folder'
                        or any(live.get(k) != original.get(k) for k in ('name','size','md5Checksum','modifiedTime'))):
                    raise RuntimeError('Legacy file changed after inventory; preserved')
                private(client, file_id)
                drive_retry(lambda: client.files().delete(fileId=file_id).execute())
                report['deleted'].append(file_id)
                report['deleted_bytes'] += int(original.get('size', 0))
            except Exception as error:
                if getattr(getattr(error, 'resp', None), 'status', None) != 404:
                    report['failed'].append(dict(id=file_id, error_type=type(error).__name__))
            save()
        remaining, _ = inventory(client, root)
        report['remaining'] = [item['id'] for item in remaining]
    report['quota_after'] = drive_retry(lambda: client.about().get(fields='storageQuota').execute()).get('storageQuota',{})
    save()
    if report['failed'] or report['remaining']:
        raise RuntimeError('Legacy cleanup incomplete; exact report retained for retry')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--delete', action='store_true')
    args = parser.parse_args()
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    client = build('drive','v3',credentials=Credentials.from_authorized_user_info(
        json.loads(required('DRIVE_TOKEN_JSON'))),cache_discovery=False)
    result = clean(client, required('DRIVE_FOLDER_ID'), Path('output/legacy-cleanup-report.json'), args.delete)
    print(json.dumps(dict(mode=result['mode'], candidates=len(result['candidates']),
        deleted=len(result['deleted']), deleted_bytes=result['deleted_bytes'],
        preserved_folders=len(result['preserved_folders']), remaining=len(result['remaining']))), flush=True)
