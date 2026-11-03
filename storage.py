import os, json, hashlib, time
from pathlib import Path

def required(name):
    value = os.getenv(name)
    if not value: raise RuntimeError('Missing configuration: ' + name)
    return value

def drive_transient(error):
    """Retry transport failures and temporary API responses, never permission/quota errors."""
    import socket
    import ssl
    import http.client
    status = getattr(getattr(error, 'resp', None), 'status', None)
    return isinstance(error, (TimeoutError, ConnectionError, socket.timeout,
        ssl.SSLError, http.client.IncompleteRead, http.client.RemoteDisconnected)) or status in (408, 429, 500, 502, 503, 504)


def drive_retry(call):
    for attempt in range(5):
        try:
            return call()
        except Exception as error:
            if not drive_transient(error) or attempt == 4:
                raise
            print(json.dumps({'check': 'Drive request', 'retry': attempt + 1,
                'error_type': type(error).__name__}), flush=True)
            time.sleep(min(2 ** (attempt + 1), 16))


class Store:
    """Private Google Drive storage; never purchases additional quota."""
    def __init__(self):
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        self.client = build('drive', 'v3', credentials=Credentials.from_authorized_user_info(
            json.loads(required('DRIVE_TOKEN_JSON'))), cache_discovery=False)
        user = self.client.about().get(fields='user(emailAddress)').execute()['user']
        root = required('DRIVE_FOLDER_ID')
        self.check_owned_folder(root, user['emailAddress'])
        info = drive_retry(lambda: self.client.files().get(fileId=root, fields='appProperties').execute())
        if info.get('appProperties', {}).get('grow_with_rezan_root') != 'v1':
            raise RuntimeError('DRIVE_FOLDER_ID must identify the dedicated Grow with Rezan folder')
        # Isolate kids checkpoints from the archived pipeline's history and runs.
        query = (f"'{root}' in parents and trashed=false and "
                 "mimeType='application/vnd.google-apps.folder' and "
                 "appProperties has { key='grow_with_rezan_kids_root' and value='v1' }")
        result = drive_retry(lambda: self.client.files().list(
            q=query, fields='nextPageToken,files(id)', pageSize=100).execute())
        folders = result.get('files', [])
        if result.get('nextPageToken') or len(folders) > 1:
            raise RuntimeError('Multiple kids rhyme folders require reconciliation')
        if folders:
            self.folder = folders[0]['id']
        else:
            self.folder = self.client.files().create(body={
                'name': 'Kids Rhymes - Grow with Rezan', 'parents': [root],
                'mimeType': 'application/vnd.google-apps.folder',
                'appProperties': {'grow_with_rezan_kids_root': 'v1'}}, fields='id').execute()['id']
        self.check_owned_folder(self.folder, user['emailAddress'])

    def check_owned_folder(self, folder, email):
        info = drive_retry(lambda: self.client.files().get(fileId=folder,
            fields='mimeType,trashed,owners(emailAddress)').execute())
        if info.get('trashed') or info.get('mimeType') != 'application/vnd.google-apps.folder':
            raise RuntimeError('DRIVE_FOLDER_ID must identify an accessible active folder')
        if {owner.get('emailAddress', '').lower() for owner in info.get('owners', [])} != {email.lower()}:
            raise RuntimeError('Configured Drive folder must belong to the authenticated account')
        self.check_private(folder)

    def check_private(self, file_id):
        permissions = drive_retry(lambda: self.client.permissions().list(fileId=file_id,
            fields='permissions(type,role)', pageSize=100).execute()).get('permissions', [])
        if any(p.get('role') != 'owner' for p in permissions):
            raise RuntimeError('Workflow storage must be private to its owner')

    def find(self, key):
        # Query using only an internal SHA-256 key, never interpolated user input.
        digest = hashlib.sha256(key.encode()).hexdigest()
        q = (f"'{self.folder}' in parents and trashed = false and "
             f"appProperties has {{ key='workflow_key' and value='{digest}' }}")
        result = drive_retry(lambda: self.client.files().list(q=q, fields='nextPageToken,files(id)', pageSize=100).execute())
        items = result['files']
        if result.get('nextPageToken'):
            raise RuntimeError('Duplicate checkpoint files require reconciliation')
        if len(items) > 1:
            raise RuntimeError('Duplicate checkpoint files require reconciliation')
        if items:
            self.check_private(items[0]['id'])
            return items[0]['id']
        return None

    def load(self, key, default):
        file_id = self.find(key)
        if not file_id:
            return default
        return json.loads(drive_retry(lambda: self.client.files().get_media(fileId=file_id).execute()))

    def check_quota(self, size, reserve_bytes=100 * 1024**2):
        quota = drive_retry(lambda: self.client.about().get(fields='storageQuota').execute())['storageQuota']
        if 'limit' not in quota:
            raise RuntimeError('Cannot verify free storage allowance; stop before upload')
        limit = min(int(quota['limit']), 15 * 1024**3)
        if int(quota.get('usage', 0)) + size + reserve_bytes > limit:
            raise RuntimeError('Free storage allowance nearly full; no paid upgrade will be requested')

    def metadata(self, key, file_id):
        metadata = {'id': file_id, 'name': key.replace('/', '__'), 'parents': [self.folder],
                    'appProperties': {'workflow_key': hashlib.sha256(key.encode()).hexdigest()}}
        return metadata

    def verified(self, file_id, key, size, checksum):
        try:
            remote = drive_retry(lambda: self.client.files().get(fileId=file_id,
                fields='id,parents,trashed,appProperties,size,md5Checksum').execute())
        except Exception as error:
            if getattr(getattr(error, 'resp', None), 'status', None) == 404:
                return False
            raise
        if (remote.get('trashed') or self.folder not in remote.get('parents', []) or
                remote.get('appProperties', {}).get('workflow_key') != hashlib.sha256(key.encode()).hexdigest()):
            raise RuntimeError('Drive upload identity mismatch; refusing overwrite')
        self.check_private(file_id)
        return str(remote.get('size')) == str(size) and remote.get('md5Checksum') == checksum

    def put(self, key, media, size):
        """Bounded retries on one file ID and upload session; verify before returning."""
        checksum = hashlib.md5()
        for offset in range(0, size, 8 * 1024 * 1024):
            checksum.update(media.getbytes(offset, min(8 * 1024 * 1024, size - offset)))
        checksum = checksum.hexdigest()
        self.check_private(self.folder)
        file_id = self.find(key)
        creating = file_id is None
        journal = Path(os.getenv('OUTPUT_DIR', 'output')) / '.drive-upload-ids' / (
            hashlib.sha256((self.folder + ':' + key).encode()).hexdigest() + '.json')
        reserved = json.loads(journal.read_text())['id'] if journal.exists() else None
        if file_id and reserved and file_id != reserved:
            raise RuntimeError('Drive file ID differs from reserved upload identity')
        file_id = file_id or reserved
        if file_id and self.verified(file_id, key, size, checksum):
            return {'id': file_id}
        # A tiny durable cleanup journal must be writable inside the normal
        # 100MB reserve, otherwise cleanup itself cannot free a nearly-full Drive.
        if key.endswith('/cleanup.json') and size<=256*1024:
            self.check_quota(size,reserve_bytes=0)
        else:
            self.check_quota(size)
        if creating and not file_id:
            file_id = drive_retry(lambda: self.client.files().generateIds(count=1, space='drive').execute())['ids'][0]
        journal.parent.mkdir(parents=True, exist_ok=True)
        temporary = journal.with_suffix('.tmp')
        temporary.write_text(json.dumps({'id': file_id}))
        temporary.replace(journal)
        metadata = self.metadata(key, file_id)

        def new_request():
            if creating:
                return self.client.files().create(body=metadata, media_body=media, fields='id')
            return self.client.files().update(fileId=file_id, media_body=media, fields='id')

        request, failures = new_request(), 0
        while True:
            try:
                if media.resumable():
                    _, result = request.next_chunk(num_retries=0)
                    if result is None:
                        continue
                else:
                    request.execute(num_retries=0)
                if not self.verified(file_id, key, size, checksum):
                    raise RuntimeError('Drive upload checksum or size verification failed')
                return {'id': file_id}
            except Exception as error:
                status = getattr(getattr(error, 'resp', None), 'status', None)
                if not drive_transient(error) and status not in (404, 410, 409):
                    raise
                # A response can time out after Drive has committed the complete file.
                # Read errors are not evidence that the file is absent.
                if self.verified(file_id, key, size, checksum):
                    return {'id': file_id}
                if status == 409:
                    raise RuntimeError('Drive creation conflict; refusing overwrite') from error
                failures += 1
                if failures >= 5:
                    raise
                print(json.dumps({'check': 'Drive upload', 'retry': failures,
                    'error_type': type(error).__name__}), flush=True)
                time.sleep(min(2 ** failures, 16))
                if status in (404, 410):
                    # Expired resumable session: reuse the reserved ID, never a new file.
                    request = new_request()

    def save(self, key, value):
        import io
        from googleapiclient.http import MediaIoBaseUpload
        payload = json.dumps(value).encode()
        return self.put(key, MediaIoBaseUpload(io.BytesIO(payload),
            mimetype='application/json', resumable=False), len(payload))

    def upload(self, path, key):
        from googleapiclient.http import MediaFileUpload
        media = MediaFileUpload(str(path), chunksize=8 * 1024 * 1024, resumable=True)
        try:
            return self.put(key, media, path.stat().st_size)
        finally:
            media.stream().close()

    def download(self, file_id, path):
        from googleapiclient.http import MediaIoBaseDownload
        self.check_private(file_id)
        info = drive_retry(lambda: self.client.files().get(fileId=file_id,
            fields='size,md5Checksum').execute())
        temporary = path.with_name(path.name + '.download-part')
        try:
            with temporary.open('wb') as output:
                request = MediaIoBaseDownload(output, self.client.files().get_media(fileId=file_id),
                    chunksize=8 * 1024 * 1024)
                done = False
                while not done:
                    _, done = drive_retry(lambda: request.next_chunk(num_retries=0))
            digest = hashlib.md5()
            with temporary.open('rb') as downloaded:
                for chunk in iter(lambda: downloaded.read(8 * 1024 * 1024), b''):
                    digest.update(chunk)
            if (str(temporary.stat().st_size) != str(info.get('size')) or
                    digest.hexdigest() != info.get('md5Checksum')):
                raise RuntimeError('Drive download checksum or size verification failed')
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
