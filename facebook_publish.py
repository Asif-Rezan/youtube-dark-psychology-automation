"""Publish existing episode media to the configured Facebook Page, with durable IDs.

No model generation or YouTube writes. API failures never expose tokens or response bodies.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urlsplit
import requests

PAGE_ID = '301624356367343'
VERSION = 'v26.0'


class FacebookError(RuntimeError):
    pass


def schedule_timestamp(value, now=None):
    when = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    current = now or dt.datetime.now(dt.timezone.utc)
    if when.tzinfo is None or not 600 < (when-current).total_seconds() < 29*86400:
        raise FacebookError('Facebook schedule must be 10 minutes to 29 days in the future')
    return int(when.timestamp())


def finish_fields(kind, video_id, session_id, metadata, timestamp):
    fields = dict(upload_phase='finish', title=metadata['title'], description=metadata['description'])
    # Reel API supports an explicit AI disclosure. Also disclose in Page video text.
    if kind == 'short':
        fields.update(video_id=video_id, video_state='SCHEDULED',
                      scheduled_publish_time=timestamp, is_ai_generated='true')
    else:
        fields.update(upload_session_id=session_id, published='false',
                      scheduled_publish_time=timestamp, unpublished_content_type='SCHEDULED')
    return fields


class Facebook:
    def __init__(self, token, session=None):
        if not token:
            raise FacebookError('FACEBOOK_PAGE_ACCESS_TOKEN is required')
        self.token = token
        self.session = session or requests.Session()

    def request(self, method, path, *, host='graph.facebook.com', data=None, params=None, files=None, headers=None):
        if host not in ('graph.facebook.com', 'graph-video.facebook.com', 'rupload.facebook.com'):
            raise FacebookError('Invalid Facebook API host')
        if not path.startswith('/') or path.startswith('//') or '?' in path or '#' in path:
            raise FacebookError('Invalid Facebook API path')
        try:
            response = self.session.request(method, 'https://'+host+path,
                headers={'Authorization': 'OAuth '+self.token, **(headers or {})},
                data=data, params=params, files=files, timeout=(30, 600), allow_redirects=False)
            result = response.json()
        except (requests.RequestException, ValueError):
            raise FacebookError('Facebook transport failed; retry the same identity to reconcile its saved video') from None
        if not 200 <= response.status_code < 300 or not isinstance(result, dict) or 'error' in result:
            code = result.get('error', {}).get('code') if isinstance(result, dict) else None
            safe_code = code if isinstance(code, int) else 'unknown'
            raise FacebookError(f'Facebook API rejected request (HTTP {response.status_code}, code {safe_code})')
        return result

    def verify_page(self):
        page = self.request('GET', f'/{VERSION}/me', params={'fields': 'id,name'})
        if page.get('id') != PAGE_ID:
            raise FacebookError('Facebook token does not belong to Grow with Rezan')

    def status(self, video_id):
        return self.request('GET', f'/{VERSION}/{video_id}', params={'fields': 'id,status,scheduled_publish_time,from,published,title,description,length'})


def verify_remote(remote, state):
    if remote.get('id') != state['video_id'] or remote.get('from', {}).get('id') != PAGE_ID:
        raise FacebookError('Facebook video identity or Page mismatch')
    status = remote.get('status', {})
    if any(status.get(key, {}).get('status') == 'error' for key in ('uploading_phase','processing_phase','publishing_phase')) or status.get('video_status') in ('error', 'failed'):
        raise FacebookError('Facebook video processing failed; saved video retained')
    actual = remote.get('scheduled_publish_time')
    if actual is not None:
        try:
            stamp = int(actual)
        except (ValueError, TypeError):
            stamp = int(dt.datetime.fromisoformat(str(actual).replace('Z','+00:00')).timestamp())
        if stamp != state['publish_at']:
            raise FacebookError('Facebook publication schedule mismatch')
    released = remote.get('published') is True and time.time() >= state['publish_at']
    return (actual is not None or released) and status.get('video_status') == 'ready'


def publish(api, path, kind, metadata, publish_at, state, save, *, attempts=60, sleep=time.sleep):
    path = Path(path)
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    identity = dict(page_id=PAGE_ID, kind=kind, sha256=digest, title=metadata['title'],
                    description=metadata['description'], publish_at=publish_at)
    if state and state.get('identity') != identity:
        raise FacebookError('Facebook source or schedule changed; refusing to overwrite checkpoint')
    if not state:
        state.update(identity=identity, publish_at=publish_at)
        save()
    api.verify_page()
    edge = 'video_reels' if kind == 'short' else 'videos'
    host = 'graph.facebook.com' if kind == 'short' else 'graph-video.facebook.com'
    endpoint = f'/{VERSION}/{PAGE_ID}/{edge}'
    if not state.get('video_id'):
        if state.get('initialization_started'):
            raise FacebookError('Facebook initialization response was lost; reconcile Page before creating another video')
        state['initialization_started'] = True
        save()
        initial = api.request('POST', endpoint, host=host,
                              data={'upload_phase':'start', 'file_size':str(path.stat().st_size)})
        video_id = str(initial.get('video_id', ''))
        if not video_id.isdigit():
            raise FacebookError('Facebook did not return a video ID')
        state.update(video_id=video_id, session_id=str(initial.get('upload_session_id','')),
                     start=int(initial.get('start_offset',0)), end=int(initial.get('end_offset',0)))
        if kind == 'short':
            url = urlsplit(initial.get('upload_url',''))
            if url.scheme != 'https' or url.netloc != 'rupload.facebook.com' or url.query or url.fragment or not url.path.startswith('/video-upload/') or url.path.rsplit('/',1)[-1] != video_id:
                raise FacebookError('Facebook returned an invalid upload URL')
            state['upload_path'] = url.path
        elif not state['session_id'].isdigit():
            raise FacebookError('Facebook did not return an upload session')
        save()
    if not state.get('transferred') and not state.get('finish_started'):
        if kind == 'short':
            remote = api.status(state['video_id'])['status'].get('uploading_phase',{})
            offset = int(remote.get('bytes_transfered',0))
            if not 0 <= offset <= path.stat().st_size:
                raise FacebookError('Invalid Facebook transfer offset')
            if remote.get('status') != 'complete':
                with path.open('rb') as stream:
                    stream.seek(offset)
                    result = api.request('POST',state['upload_path'],host='rupload.facebook.com',data=stream,
                        headers={'offset':str(offset),'file_size':str(path.stat().st_size), 'Content-Type':'application/octet-stream'})
                if result.get('success') is not True:
                    raise FacebookError('Facebook transfer was not confirmed')
        else:
            while state['start'] != state['end']:
                start,end = state['start'],state['end']
                if not 0 <= start < end <= path.stat().st_size:
                    raise FacebookError('Invalid Facebook chunk offsets')
                with path.open('rb') as stream:
                    stream.seek(start)
                    chunk = stream.read(end-start)
                result = api.request('POST',endpoint,host=host,
                    data={'upload_phase':'transfer','upload_session_id':state['session_id'],'start_offset':str(start)},
                    files={'video_file_chunk':('chunk.mp4',chunk,'application/octet-stream')})
                next_start,next_end = int(result['start_offset']),int(result['end_offset'])
                if next_start <= start:
                    raise FacebookError('Facebook upload did not advance')
                state.update(start=next_start,end=next_end)
                save()
        state['transferred'] = True
        save()
    if not state.get('finish_started'):
        # Commit the intent before the write. A lost response is reconciled by GET,
        # never by initializing another video or blindly publishing twice.
        state['finish_started'] = True
        save()
        result = api.request('POST',endpoint,host=host,
            data=finish_fields(kind,state['video_id'],state['session_id'],metadata,publish_at))
        if result.get('success') is not True:
            raise FacebookError('Facebook publication was not acknowledged; reconcile saved video')
        state['finish_accepted'] = True
        save()
    for attempt in range(attempts):
        if verify_remote(api.status(state['video_id']),state):
            state['phase'] = 'scheduled'
            save()
            print(json.dumps({'phase':'Facebook scheduled','video_id':state['video_id'],'page_id':PAGE_ID,
                              'publish_at':state['publish_at']}),flush=True)
            return
        if attempt+1 < attempts:
            sleep(15)
    raise FacebookError('Facebook processing or schedule readback pending; resume the same identity')


def run(run_id, source=None, adopt_video_id=None):
    if not re.fullmatch(r'daily-\d+', run_id):
        raise FacebookError('Invalid daily run ID')
    from workflow import Store
    store = Store()
    youtube = store.load(f'runs/{run_id}/state.json', {})
    publication = youtube.get('publication', {})
    if not publication.get('confirmed') or youtube.get('phase') != 'verified_private':
        raise FacebookError('Confirmed YouTube publication is required before Facebook upload')
    target = publication.get('publish_at')
    if publication.get('mode') != 'scheduled' or not target:
        raise FacebookError('A saved YouTube schedule is required')
    key = f'runs/{run_id}/facebook.json'
    state = store.load(key, {})
    expiry = int(os.getenv('FACEBOOK_DATA_ACCESS_EXPIRES_AT', '0'))
    if expiry and expiry - time.time() < 14*86400:
        print('::warning::Facebook data access expires within 14 days; renew Page authorization in Meta.')
    api = Facebook(os.getenv('FACEBOOK_PAGE_ACCESS_TOKEN'))
    if state.get('phase') == 'scheduled':
        api.verify_page()
        if not verify_remote(api.status(state['video_id']), state):
            raise FacebookError('Previously scheduled video needs reconciliation')
        return
    stamp = schedule_timestamp(target) if not state.get('video_id') else int(state['publish_at'])
    story = youtube['story']
    metadata = {'title': story['title'], 'description': youtube.get('upload_description', story['description'])
                + '\n\nVisual scenes and narration were created with AI assistance.'}
    if adopt_video_id:
        if not adopt_video_id.isdigit() or state.get('video_id') not in (None, adopt_video_id):
            raise FacebookError('Cannot adopt a different existing Facebook identity')
        remote = api.status(adopt_video_id)
        candidate = {'video_id': adopt_video_id, 'publish_at': stamp}
        expected_duration = youtube.get('validation', {}).get('duration_seconds')
        if expected_duration is not None and abs(float(remote.get('length', -999)) - float(expected_duration)) > 2:
            raise FacebookError('Existing Facebook video duration does not match this run')
        if (remote.get('title') != metadata['title'] or remote.get('description') != metadata['description']
                or not verify_remote(remote, candidate)):
            raise FacebookError('Existing Facebook metadata or publication does not match this run')
        state.update(candidate, phase='scheduled', adopted=True)
        store.save(key, state)
        print(json.dumps({'phase': 'Facebook scheduled', 'video_id': adopt_video_id,
                          'page_id': PAGE_ID, 'publish_at': stamp, 'reconciled': True}))
        return
    root = Path('output/facebook')/run_id
    root.mkdir(parents=True, exist_ok=True)
    path = Path(source) if source else root/'video.mp4'
    if not source:
        file_id = store.find(f'runs/{run_id}/video.mp4')
        if not file_id:
            raise FacebookError('Source video missing; restore original MP4 before retrying Facebook')
        store.download(file_id, path)
    def save():
        store.save(key, state)
    publish(api, path, 'video', metadata, stamp, state, save)
    # Facebook owns a separate checkpoint; YouTube state is never modified.
    from daily_publish import cleanup
    cleanup(store, run_id, youtube)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--source', help='Original local MP4 for recovery only')
    parser.add_argument('--adopt-video-id', help='Reconcile an existing matching Facebook video without uploading')
    args = parser.parse_args()
    try:
        run(args.run_id, args.source, args.adopt_video_id)
    except Exception as error:
        print(str(error) if isinstance(error, FacebookError) else 'Facebook publication failed: '+type(error).__name__)
        raise SystemExit(1)
