"""Explicit, validated YouTube upload settings, checkpointed before upload."""
import datetime as dt
import json
import os
from pathlib import Path
import re
import time
from zoneinfo import ZoneInfo

SETTINGS = Path(__file__).with_name('upload_settings.json')

def load_settings(now=None):
    settings = json.loads(SETTINGS.read_text())
    for env, field in [('UPLOAD_MODE','mode'),('PUBLISH_AT','publish_at'),('VIDEO_LANGUAGE','language'),
                       ('AUDIO_LANGUAGE','audio_language'),('VIDEO_CATEGORY_ID','category_id')]:
        if os.getenv(env):
            settings[field] = os.environ[env]
    if settings['mode'] not in ('public', 'scheduled'):
        raise ValueError('Upload mode must be public or scheduled')
    for field in ('language','audio_language'):
        if not re.fullmatch(r'[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*', settings[field]):
            raise ValueError('Invalid language code')
    if not re.fullmatch(r'[1-9][0-9]*', settings['category_id']):
        raise ValueError('Invalid YouTube category ID')
    for field in ('made_for_kids','contains_synthetic_media','embeddable','public_stats_viewable',
                  'notify_subscribers','paid_product_placement'):
        if type(settings[field]) is not bool:
            raise ValueError('Expected boolean setting: ' + field)
    if not settings['made_for_kids'] or not settings['contains_synthetic_media']:
        raise ValueError('Kids and AI disclosures are required for this pipeline')
    if settings['license'] not in ('youtube','creativeCommon'):
        raise ValueError('Invalid license')
    if settings['mode'] == 'scheduled' and not settings.get('publish_at'):
        if settings.get('schedule_policy') != 'new_york_6am_after_72h':
            raise ValueError('Automatic schedule policy missing')
    elif settings['mode'] == 'scheduled':
        when = dt.datetime.fromisoformat((settings.get('publish_at') or '').replace('Z','+00:00'))
        if when.tzinfo is None or when <= (now or dt.datetime.now(dt.timezone.utc)):
            raise ValueError('Scheduled publication needs a future ISO timestamp with timezone')
        settings['publish_at'] = when.astimezone(dt.timezone.utc).isoformat().replace('+00:00','Z')
    elif settings.get('publish_at'):
        raise ValueError('publish_at must be empty for public mode')
    return settings


def upload_body(song, description, tags, settings):
    status = dict(privacyStatus='private' if settings['mode']=='scheduled' else 'public',
        selfDeclaredMadeForKids=settings['made_for_kids'], containsSyntheticMedia=settings['contains_synthetic_media'],
        license=settings['license'], embeddable=settings['embeddable'], publicStatsViewable=settings['public_stats_viewable'])
    if settings['mode']=='scheduled' and settings.get('publish_at'):
        status['publishAt'] = settings['publish_at']
    return dict(snippet=dict(title=song['title'],description=description,tags=tags,
        categoryId=settings['category_id'],defaultLanguage=settings['language'],defaultAudioLanguage=settings['audio_language']),
        status=status, paidProductPlacementDetails=dict(hasPaidProductPlacement=settings['paid_product_placement']))


def new_york_publish_time(upload_finished):
    """First 06:00 America/New_York slot at least 72 elapsed hours after upload."""
    if upload_finished.tzinfo is None:
        raise ValueError('Upload completion must include a timezone')
    earliest = upload_finished.astimezone(dt.timezone.utc) + dt.timedelta(hours=72)
    zone = ZoneInfo('America/New_York')
    local_day = earliest.astimezone(zone).date()
    candidate = dt.datetime.combine(local_day, dt.time(6), tzinfo=zone)
    if candidate.astimezone(dt.timezone.utc) < earliest:
        candidate = dt.datetime.combine(local_day+dt.timedelta(days=1),dt.time(6),tzinfo=zone)
    return candidate.astimezone(dt.timezone.utc).isoformat().replace('+00:00','Z')


def schedule_uploaded_video(client, state, save, now=None, *, deadline=None):
    """Upload privately, then set a stable post-upload schedule; retries reuse it."""
    settings = state['upload_settings']
    if settings['mode'] != 'scheduled' or settings.get('publish_at') or state.get('schedule_configured'):
        return
    if settings.get('schedule_policy') != 'new_york_6am_after_72h':
        raise ValueError('Unsupported automatic schedule policy')
    if not state.get('video_id'):
        raise ValueError('Upload must complete before scheduling')
    current = now or dt.datetime.now(dt.timezone.utc)
    # When recovering an upload checkpoint without a timestamp, using now is a
    # conservative upper bound: it can delay release, never shorten the 72h wait.
    if not state.get('upload_completed_at'):
        state['upload_completed_at'] = current.isoformat()
    if not state.get('schedule_target'):
        finished = dt.datetime.fromisoformat(state['upload_completed_at'].replace('Z','+00:00'))
        state['schedule_target'] = new_york_publish_time(finished)
        state['upload_body']['status']['publishAt'] = state['schedule_target']
        save()  # Freeze the target before mutating YouTube so retries cannot drift.
    expected = state['schedule_target']
    if dt.datetime.fromisoformat(expected.replace('Z','+00:00')) <= current:
        raise RuntimeError('Unconfirmed schedule is in the past; reconcile the existing video')
    # A newly uploaded video may not yet accept status writes. Read ownership,
    # privacy and processing before each retry; never retry quota/auth failures.
    from googleapiclient.errors import HttpError
    started = time.monotonic()
    stop_at = min(deadline, started + 1800) if deadline is not None else started + 1800
    # Processing routinely exceeds two minutes. Poll for up to thirty minutes,
    # while retaining an independent attempt bound for a stalled clock/test.
    for attempt in range(90):
        if time.monotonic() >= stop_at:
            break
        items = client.videos().list(part='snippet,status,processingDetails',
            id=state['video_id']).execute(num_retries=5).get('items', [])
        if len(items) != 1 or items[0].get('id') != state['video_id']:
            raise RuntimeError('Uploaded video unavailable')
        video = items[0]
        channel = os.getenv('EXPECTED_CHANNEL_ID')
        if channel and video.get('snippet', {}).get('channelId') != channel:
            raise RuntimeError('Uploaded channel mismatch')
        status = video.get('status', {})
        processing = video.get('processingDetails', {}).get('processingStatus')
        print(json.dumps({'check':'YouTube schedule readiness','upload_status':status.get('uploadStatus'),
            'processing_status':processing,'privacy':status.get('privacyStatus')}),flush=True)
        if status.get('uploadStatus') in ('failed','rejected','deleted') or processing in ('failed','terminated'):
            raise RuntimeError('YouTube rejected upload')
        remote_time = status.get('publishAt')
        if (status.get('privacyStatus') == 'private' and remote_time and
                dt.datetime.fromisoformat(remote_time.replace('Z','+00:00')) ==
                dt.datetime.fromisoformat(expected.replace('Z','+00:00'))):
            state['schedule_configured'] = True
            state.pop('schedule_pending', None)
            save()
            return
        if status.get('privacyStatus') != 'private':
            raise RuntimeError('Scheduling requires an existing private video; reconcile visibility')
        if processing != 'processing' and status.get('uploadStatus') != 'uploaded':
            try:
                client.videos().update(part='status', body={'id':state['video_id'],
                    'status':state['upload_body']['status']}).execute(num_retries=5)
            except HttpError as error:
                try:
                    reasons = {item.get('reason') for item in json.loads(error.content).get('error',{}).get('errors',[])}
                except (ValueError, TypeError):
                    reasons = set()
                code = getattr(error.resp, 'status', None)
                finished = dt.datetime.fromisoformat(state['upload_completed_at'].replace('Z','+00:00'))
                recent = (current - finished).total_seconds() + (time.monotonic() - started) < 900
                temporary = code in (429,500,502,503,504) or (
                    code == 403 and reasons == {'forbidden'} and channel and recent)
                print(json.dumps({'check':'YouTube scheduling update','http_status':code,
                    'reasons':sorted(str(r) for r in reasons),'retryable':bool(temporary)}),flush=True)
                if not temporary:
                    raise RuntimeError('YouTube scheduling permission or quota denied; saved video retained') from None
        # Save pending state even if a runner stops during the wait. Readback on
        # the next attempt reconciles successful writes with a lost response.
        state['schedule_pending'] = True
        save()
        if attempt < 89 and time.monotonic() < stop_at:
            print(json.dumps({'check':'wait for YouTube schedule readiness','attempt':attempt+1}),flush=True)
            time.sleep(min(20, max(0, stop_at - time.monotonic())))
    raise TimeoutError('YouTube schedule pending; resume the existing video ID')


def ensure_synthetic_disclosure(client, video, state, save):
    """Submit the required disclosure on the existing upload, preserving visibility.

    Some API responses omit this writeable field. Record a successful explicit
    write for that video; never treat an explicit false value as verified.
    """
    if state['upload_body']['status'].get('containsSyntheticMedia') is not True:
        raise ValueError('AI disclosure is required')
    status=video.get('status',{})
    if status.get('containsSyntheticMedia') is True:
        return
    receipt=state.get('synthetic_disclosure_receipt',{})
    if ('containsSyntheticMedia' not in status and receipt.get('video_id')==state['video_id']
            and receipt.get('accepted') is True):
        return
    if video.get('id')!=state['video_id']:
        raise RuntimeError('Uploaded video unavailable')
    # Status updates replace mutable properties: preserve the live visibility,
    # schedule and other settings instead of restoring an old private status.
    fields=('privacyStatus','publishAt','license','embeddable','publicStatsViewable','selfDeclaredMadeForKids')
    update={field:status[field] for field in fields if field in status}
    update['containsSyntheticMedia']=True
    response=client.videos().update(part='status',body={'id':state['video_id'],'status':update}).execute()
    returned=response.get('status',{})
    print(json.dumps({'check':'AI disclosure update','readback_present':'containsSyntheticMedia' in returned,
                      'readback_value':returned.get('containsSyntheticMedia')}),flush=True)
    if response.get('id')!=state['video_id'] or returned.get('containsSyntheticMedia') is False:
        raise RuntimeError('Uploaded setting mismatch: containsSyntheticMedia')
    state['synthetic_disclosure_receipt']={'video_id':state['video_id'],'accepted':True,
        'accepted_at':dt.datetime.now(dt.timezone.utc).isoformat()}
    save()


def normalized_tags(tags):
    # YouTube may normalize casing/spacing while processing a Short.
    return {' '.join(tag.split()).casefold() for tag in tags}


def ensure_uploaded_tags(client, video, state, save):
    """Repair metadata on the existing ID, never upload a second video."""
    wanted = state['upload_body']['snippet']
    actual = video.get('snippet', {}).get('tags', [])
    if normalized_tags(actual) == normalized_tags(wanted['tags']):
        return False
    if video.get('id') != state['video_id']:
        raise RuntimeError('Uploaded video unavailable')
    # Tags are public metadata; log these alone, never API bodies or credentials.
    print(json.dumps({'check':'reconcile uploaded tags',
        'expected_tags':wanted['tags'], 'actual_tags':actual}), flush=True)
    attempts = state.get('tag_repair_attempts', 0)
    if attempts >= 2:
        raise RuntimeError('Uploaded tags mismatch')
    state['tag_repair_attempts'] = attempts + 1
    save()
    client.videos().update(part='snippet',body={'id':state['video_id'],
        'snippet':wanted}).execute(num_retries=5)
    return True


def verified_phase(video, body, channel_id, disclosure_receipt=None):
    """Return a terminal phase only for matching remote metadata and processed HD."""
    snippet, status = video.get('snippet',{}), video.get('status',{})
    if snippet.get('channelId') != channel_id:
        raise RuntimeError('Uploaded channel mismatch')
    if status.get('uploadStatus') in ('failed','rejected','deleted'):
        raise RuntimeError('YouTube rejected upload')
    for field in ('title','description','categoryId','defaultLanguage','defaultAudioLanguage'):
        if snippet.get(field) != body['snippet'][field]:
            raise RuntimeError('Uploaded metadata mismatch: ' + field)
    if normalized_tags(snippet.get('tags',[])) != normalized_tags(body['snippet']['tags']):
        raise RuntimeError('Uploaded tags mismatch')
    for field in ('selfDeclaredMadeForKids','containsSyntheticMedia','license','embeddable','publicStatsViewable'):
        if (field=='containsSyntheticMedia' and field not in status
                and body['status'][field] is True and disclosure_receipt
                and disclosure_receipt.get('accepted') is True
                and disclosure_receipt.get('video_id')==video.get('id')):
            continue
        if status.get(field) != body['status'][field]:
            raise RuntimeError('Uploaded setting mismatch: ' + field)
    if video.get('paidProductPlacementDetails',{}).get('hasPaidProductPlacement',False) != body['paidProductPlacementDetails']['hasPaidProductPlacement']:
        raise RuntimeError('Paid placement disclosure mismatch')
    if 'publishAt' in body['status'] and status.get('privacyStatus') == 'private':
        wanted=dt.datetime.fromisoformat(body['status']['publishAt'].replace('Z','+00:00'))
        got=dt.datetime.fromisoformat(status.get('publishAt','').replace('Z','+00:00'))
        if got!=wanted:
            raise RuntimeError('Scheduled time mismatch')
        phase='scheduled'
    elif status.get('privacyStatus')=='public':
        phase='published'
    else:
        raise RuntimeError('YouTube did not retain requested visibility')
    if status.get('uploadStatus')=='processed' and video.get('contentDetails',{}).get('definition')=='hd' and video.get('processingDetails',{}).get('processingStatus')=='succeeded':
        return phase
    return None
