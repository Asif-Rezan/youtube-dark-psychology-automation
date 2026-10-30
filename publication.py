"""Durable, DST-aware YouTube publication after upload verification."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def next_publish_time(now):
    earliest = now.astimezone(timezone.utc) + timedelta(hours=72)
    local = earliest.astimezone(ZoneInfo('America/New_York'))
    slot = local.replace(hour=6, minute=0, second=0, microsecond=0)
    if slot.astimezone(timezone.utc) < earliest:
        slot += timedelta(days=1)
    return slot.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def parse_time(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def publish_verified(client, store, key, state, video, mode):
    if mode == 'private':
        return
    if mode not in ('scheduled', 'public'):
        raise ValueError('Invalid publication mode')
    intent = state.get('publication')
    if intent is None:
        intent = {'mode': mode}
        if mode == 'scheduled':
            intent['publish_at'] = next_publish_time(datetime.now(timezone.utc))
        state['publication'] = intent
        store.save(key, state)  # Save intent before an ambiguous API response.
    elif intent['mode'] != mode:
        raise RuntimeError('Publication mode differs from saved intent')
    status = video['status']
    if status['privacyStatus'] == 'public':
        if mode == 'scheduled' and datetime.now(timezone.utc) < parse_time(intent['publish_at']):
            raise RuntimeError('Video became public before its saved schedule')
    elif mode == 'scheduled' and status.get('publishAt') and parse_time(status['publishAt']) == parse_time(intent['publish_at']):
        if status['privacyStatus'] != 'private':
            raise RuntimeError('Unexpected scheduled visibility')
    else:
        if status['privacyStatus'] != 'private':
            raise RuntimeError('Only a verified private upload can be published')
        desired = {k: v for k, v in status.items() if k in (
            'privacyStatus', 'license', 'embeddable', 'publicStatsViewable',
            'selfDeclaredMadeForKids', 'containsSyntheticMedia')}
        desired['privacyStatus'] = 'public' if mode == 'public' else 'private'
        if mode == 'scheduled':
            if parse_time(intent['publish_at']) <= datetime.now(timezone.utc):
                raise RuntimeError('Saved schedule expired without confirmation; reconcile manually')
            desired['publishAt'] = intent['publish_at']
        else:
            desired.pop('publishAt', None)
        client.videos().update(part='status', body={'id': state['video_id'], 'status': desired}).execute()
    items = client.videos().list(part='status', id=state['video_id']).execute().get('items', [])
    if not items:
        raise RuntimeError('Publication readback unavailable; preserve media')
    actual = items[0]['status']
    published = actual['privacyStatus'] == 'public' and (mode == 'public' or datetime.now(timezone.utc) >= parse_time(intent['publish_at']))
    scheduled = (mode == 'scheduled' and actual['privacyStatus'] == 'private'
        and actual.get('publishAt') and parse_time(actual['publishAt']) == parse_time(intent['publish_at']))
    if not (published or scheduled):
        raise RuntimeError('YouTube did not confirm publication; preserve media')
    intent['confirmed'] = True
    store.save(key, state)
