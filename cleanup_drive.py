"""Clean only verified public HD episodes; revisit scheduled episodes later."""
import argparse
import datetime as dt
from pathlib import Path
import hashlib
import json
import re

from storage import Store, drive_retry, required

MEDIA = ('storyboard.tar.gz', 'song.wav', 'video.mp4', 'thumbnail.jpg', 'background-source.png',
         'thumbnail-source.png', 'cover.png')


class PublicationPending(RuntimeError):
    """The verified episode is still private/scheduled; keep recovery media."""


class CleanupNotEligible(RuntimeError):
    """Expected verification exclusion, not an operational cleanup failure."""
    def __init__(self,reason,fields=()):
        self.reason=reason
        self.fields=list(fields)
        super().__init__(reason)


def verify_public(client, state):
    from pipeline import metadata_tags, upload_description
    from upload_settings import normalized_tags
    if state.get('phase') not in ('published','scheduled') or not state.get('video_id') or state.get('thumbnail_uploaded') is not True:
        raise CleanupNotEligible('publication_receipt_incomplete')
    items = client.videos().list(part='snippet,status,processingDetails,contentDetails',
                                id=state['video_id']).execute(num_retries=3).get('items', [])
    if len(items) != 1:
        raise CleanupNotEligible('video_unavailable')
    video = items[0]
    snippet, status = video.get('snippet', {}), video.get('status', {})
    song = state['song']
    # Uploads use owner-supplied fixed metadata; verify the durable upload body,
    # not the generated story title/tags. Older checkpoints retain the fallback.
    expected=state.get('upload_body',{}).get('snippet',{})
    title=expected.get('title',song['title'])
    description=expected.get('description',state.get('upload_description',upload_description(song)))
    tags=expected.get('tags',metadata_tags(song))
    checks={'video_id':video.get('id')==state['video_id'],
            'channel_id':snippet.get('channelId')==required('EXPECTED_CHANNEL_ID'),
            'title':snippet.get('title')==title,
            'description':snippet.get('description')==description,
            'tags':normalized_tags(snippet.get('tags',[]))==normalized_tags(tags),
            'upload_status':status.get('uploadStatus') in ('uploaded','processed')}
    mismatches=[name for name,matched in checks.items() if not matched]
    if mismatches:
        raise CleanupNotEligible('video_verification_mismatch',mismatches)
    if state.get('phase') == 'scheduled' and status.get('privacyStatus') == 'private':
        raise PublicationPending('Scheduled episode is not public yet')
    if (status.get('privacyStatus') != 'public' or status.get('uploadStatus') != 'processed'
            or video.get('processingDetails',{}).get('processingStatus') != 'succeeded'
            or video.get('contentDetails',{}).get('definition') != 'hd'):
        raise CleanupNotEligible('public_hd_not_ready')


def cleanup(store, client, run_id, state):
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', run_id):
        raise ValueError('Invalid run ID')
    verify_public(client, state)  # Fresh YouTube proof, including on cleanup-only retries.
    key = f'runs/{run_id}/cleanup.json'
    journal = store.load(key, None)
    if journal is None:
        files = []
        for name in MEDIA:
            media_key = f'runs/{run_id}/{name}'
            file_id = store.find(media_key)
            if file_id:
                files.append({'id': file_id, 'name': name})
        journal = {'run': run_id, 'video_id': state['video_id'], 'files': files, 'deleted': []}
        store.save(key, journal)  # Durable exact-ID manifest before any deletion.
    if journal.get('run') != run_id or journal.get('video_id') != state['video_id']:
        raise RuntimeError('Cleanup journal identity mismatch')
    deleted_before=len(journal['deleted'])
    for entry in journal['files']:
        file_id, name = entry['id'], entry['name']
        if name not in MEDIA:
            raise RuntimeError('Unsafe cleanup manifest entry')
        if file_id in journal['deleted']:
            continue
        media_key = f'runs/{run_id}/{name}'
        try:
            remote = drive_retry(lambda: store.client.files().get(fileId=file_id,
                fields='id,name,parents,appProperties,mimeType,trashed').execute())
            if (remote.get('id') != file_id or remote.get('name') != media_key.replace('/', '__')
                    or store.folder not in remote.get('parents', [])
                    or remote.get('appProperties', {}).get('workflow_key') != hashlib.sha256(media_key.encode()).hexdigest()
                    or remote.get('mimeType') == 'application/vnd.google-apps.folder'):
                raise RuntimeError('Unsafe cleanup target rejected')
            store.check_private(file_id)
            drive_retry(lambda: store.client.files().delete(fileId=file_id).execute())
        except Exception as error:
            if getattr(getattr(error, 'resp', None), 'status', None) != 404:
                raise
            # The previous attempt may have deleted the file before saving its checkpoint.
        journal['deleted'].append(file_id)
        store.save(key, journal)
    journal['complete'] = True
    journal['verified_at']=dt.datetime.now(dt.timezone.utc).isoformat()
    store.save(key, journal)
    if state.get('phase')=='scheduled':
        state['phase']='published'
        store.save(f'runs/{run_id}/state.json',state)
    print(json.dumps({'run': run_id, 'video_id': state['video_id'],
                      'cleanup_complete': True, 'deleted_media': len(journal['deleted']),
                      'deleted_this_check':len(journal['deleted'])-deleted_before}), flush=True)
    return journal



def run_states(store):
    """Read only tagged checkpoints in this automation's private owned folder."""
    token=None
    while True:
        query=f"'{store.folder}' in parents and trashed=false and name contains 'runs__'"
        result=drive_retry(lambda:store.client.files().list(q=query,pageSize=1000,
            pageToken=token,fields='nextPageToken,files(id,name,mimeType,appProperties)').execute())
        for item in result.get('files',[]):
            match=re.fullmatch(r'runs__([a-zA-Z0-9_-]{1,80})__state\.json',item.get('name',''))
            if not match or item.get('mimeType')=='application/vnd.google-apps.folder':
                continue
            run_id=match.group(1)
            key=f'runs/{run_id}/state.json'
            if item.get('appProperties',{}).get('workflow_key') != hashlib.sha256(key.encode()).hexdigest():
                continue
            try:
                store.check_private(item['id'])
                state=json.loads(drive_retry(lambda:store.client.files().get_media(fileId=item['id']).execute()))
            except Exception as error:
                state={'_read_error':type(error).__name__}
            yield run_id,state
        token=result.get('nextPageToken')
        if not token:
            break


def quota(store):
    result=drive_retry(lambda:store.client.about().get(fields='storageQuota').execute())
    return result.get('storageQuota',{})


def sweep(store,client,dry_run=False):
    report=dict(checked_at=dt.datetime.now(dt.timezone.utc).isoformat(),
        quota_before=quota(store),cleaned=[],pending=[],preserved=[],review=[],eligible=[],failed=[])
    for run_id,state in run_states(store):
        if isinstance(state,dict) and state.get('_read_error'):
            report['failed'].append(dict(run=run_id,error_type=state['_read_error']))
            continue
        if not isinstance(state,dict) or state.get('phase') not in ('published','scheduled'):
            report['preserved'].append(run_id)
            continue
        try:
            journal=store.load(f'runs/{run_id}/cleanup.json',None)
            if journal and journal.get('complete') and journal.get('run')==run_id and journal.get('video_id')==state.get('video_id'):
                continue
            if dry_run:
                verify_public(client,state)
                report['eligible'].append(run_id)
                continue
            journal=cleanup(store,client,run_id,state)
            report['cleaned'].append(dict(run=run_id,deleted_media=len(journal['deleted'])))
        except PublicationPending:
            report['pending'].append(run_id)
        except CleanupNotEligible as error:
            report['preserved'].append(run_id)
            report['review'].append(dict(run=run_id,reason=error.reason,fields=error.fields))
        except Exception as error:
            # Keep failed runs visible, finish checking the rest, never dump API
            # responses/credentials, never interpret an error as permission to delete.
            report['failed'].append(dict(run=run_id,error_type=type(error).__name__,
                http_status=getattr(getattr(error,'resp',None),'status',None)))
    report['quota_after']=quota(store)
    return report


def main():
    parser = argparse.ArgumentParser()
    choice=parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--run-id')
    choice.add_argument('--sweep',action='store_true')
    parser.add_argument('--dry-run',action='store_true',help='Read-only eligibility audit; requires --sweep')
    args = parser.parse_args()
    if args.dry_run and not args.sweep:
        parser.error('--dry-run requires --sweep')
    if args.run_id and not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', args.run_id):
        raise ValueError('Invalid run ID')
    from pipeline import youtube_client
    store = Store()
    client=youtube_client()
    if args.sweep:
        report=sweep(store,client,dry_run=args.dry_run)
    else:
        state=store.load(f'runs/{args.run_id}/state.json',{})
        try:
            journal=cleanup(store,client,args.run_id,state)
            report=dict(cleaned=[dict(run=args.run_id,deleted_media=len(journal['deleted']))],pending=[],failed=[])
        except PublicationPending:
            report=dict(cleaned=[],pending=[args.run_id],failed=[])
        except CleanupNotEligible as error:
            report=dict(cleaned=[],pending=[],preserved=[args.run_id],
                        review=[dict(run=args.run_id,reason=error.reason,fields=error.fields)],failed=[])
    output=Path('output/drive-cleanup-report.json')
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2))
    print(json.dumps(report),flush=True)
    for item in report.get('review',[]):
        print(f"::warning::Cleanup preserved {item['run']}: {item['reason']}; fields={','.join(item['fields']) or 'none'}. No media deleted for this episode.",flush=True)
    if report['failed']:
        raise RuntimeError('Some cleanup checks failed; preserved media and saved report for review')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('Drive cleanup failed: ' + type(error).__name__ + '. Media and cleanup journal are retained for retry.')
        raise SystemExit(1)
