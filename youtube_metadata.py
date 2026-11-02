"""Consistent upload settings and URL-free public descriptions."""
import re
import json

UPLOAD_PARTS = 'snippet,status,paidProductPlacementDetails'
UPLOAD_SETTINGS = {
    'categoryId': '24', 'defaultLanguage': 'en', 'defaultAudioLanguage': 'en',
    'containsSyntheticMedia': True, 'hasPaidProductPlacement': False,
}


def public_description(text):
    # Remove citation blocks from older checkpoints, retaining ordinary prose.
    text = re.split(r'(?im)^Sources and further reading:\s*$', text)[0]
    text = re.sub(r'(?im)^\s*Source:\s*.*$', '', text)
    text = re.sub(r'\[([^\]]+)\]\((?:https?://|www\.)[^)]+\)', r'\1', text)
    text = re.sub(r'(?:https?://|www\.)\S+', '', text, flags=re.I)
    return re.sub(r'\n{3,}', '\n\n', text).strip()


def upload_body(story, description):
    return {
        'snippet': {'title': story['title'], 'description': description,
                    'tags': story['tags'], 'categoryId': '24',
                    'defaultLanguage': 'en', 'defaultAudioLanguage': 'en'},
        'status': {'privacyStatus': 'private', 'selfDeclaredMadeForKids': False,
                   'containsSyntheticMedia': True},
        'paidProductPlacementDetails': {'hasPaidProductPlacement': False},
    }


def verify_upload_settings(video):
    for section, expected in (
        ('snippet', {k: UPLOAD_SETTINGS[k] for k in
                     ('categoryId', 'defaultLanguage', 'defaultAudioLanguage')}),
        ('status', {'containsSyntheticMedia': True}),
        ('paidProductPlacementDetails', {'hasPaidProductPlacement': False}),
    ):
        actual = video.get(section, {})
        for field, value in expected.items():
            actual_value = actual.get(field, False) if field == 'hasPaidProductPlacement' else actual.get(field)
            if field == 'containsSyntheticMedia' and field not in actual:
                receipt = video.get('_ai_disclosure_submission', {})
                if (receipt.get('video_id') == video.get('id')
                        and receipt.get('channel_id') == video.get('snippet', {}).get('channelId')
                        and receipt.get('requested_value') is True
                        and receipt.get('api_update_accepted') is True):
                    continue
            if actual_value != value:
                raise RuntimeError(f'YouTube upload setting mismatch: {field}')


def ensure_upload_settings(client, video_id, video, channel_id, *, pause=None):
    """Repair post-insert disclosure omissions on this upload, then confirm readback.

    A bounded update is idempotent; never insert a replacement video. Preserve
    every writable status field so visibility and an existing schedule survive.
    """
    import time
    pause = pause or time.sleep
    if video.get('id') != video_id or video.get('snippet', {}).get('channelId') != channel_id:
        raise RuntimeError('Refusing metadata repair on a different video or channel')
    try:
        verify_upload_settings(video)
        return video
    except RuntimeError:
        pass
    # Snippet errors are not repaired here: avoid changing titles/descriptions.
    for field in ('categoryId', 'defaultLanguage', 'defaultAudioLanguage'):
        if video['snippet'].get(field) != UPLOAD_SETTINGS[field]:
            raise RuntimeError(f'YouTube upload setting mismatch: {field}')
    status = video.get('status', {})
    if status.get('privacyStatus') not in ('private', 'unlisted', 'public'):
        raise RuntimeError('Cannot safely repair metadata without known visibility')
    parts, body = [], {'id': video_id}
    if status.get('containsSyntheticMedia') is not True:
        parts.append('status')
        body['status'] = {k: v for k, v in status.items() if k in (
            'privacyStatus', 'license', 'embeddable', 'publicStatsViewable',
            'selfDeclaredMadeForKids', 'publishAt')}
        body['status']['containsSyntheticMedia'] = True
    if video.get('paidProductPlacementDetails', {}).get('hasPaidProductPlacement', False) is not False:
        parts.append('paidProductPlacementDetails')
        body['paidProductPlacementDetails'] = {'hasPaidProductPlacement': False}
    receipt = None
    if parts:
        response = client.videos().update(part=','.join(parts), body=body).execute(num_retries=3)
        if response.get('id') != video_id:
            raise RuntimeError('YouTube metadata update did not acknowledge the expected video')
        if 'status' in parts and response.get('status', {}).get('containsSyntheticMedia') is not False:
            receipt = dict(video_id=video_id, channel_id=channel_id,
                           requested_value=True, api_update_accepted=True,
                           confirmation='API update accepted; readback field unavailable')
        print(json.dumps({'check': 'YouTube disclosure update', 'video_id': video_id,
                          'api_update_accepted': True,
                          'response_ai_field': response.get('status', {}).get('containsSyntheticMedia', 'omitted')}), flush=True)
    for attempt in range(6):
        items = client.videos().list(
            part=UPLOAD_PARTS + ',processingDetails,contentDetails', id=video_id
        ).execute(num_retries=3).get('items', [])
        if items:
            actual = items[0]
            if actual.get('id') != video_id or actual.get('snippet', {}).get('channelId') != channel_id:
                raise RuntimeError('Metadata readback returned a different video or channel')
            if attempt == 5 and 'containsSyntheticMedia' not in actual.get('status', {}) and receipt:
                actual['_ai_disclosure_submission'] = receipt
                print(json.dumps({'check': 'YouTube AI disclosure',
                                  'confirmation': receipt['confirmation'], 'video_id': video_id}), flush=True)
            try:
                verify_upload_settings(actual)
                if actual['status'].get('privacyStatus') != status['privacyStatus'] or actual['status'].get('publishAt') != status.get('publishAt'):
                    raise RuntimeError('Visibility or schedule changed during metadata repair')
                return actual
            except RuntimeError:
                if attempt == 5:
                    raise
        if attempt < 5:
            pause(5)
    raise RuntimeError('Uploaded video unavailable during metadata repair; preserve existing upload')
