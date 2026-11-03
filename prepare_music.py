"""Prepare song assets; optionally verify publication history before generation."""
import argparse
from motion_video import render_is_current
import datetime as dt
import gc
import json
import re
import time
from pathlib import Path
from zoneinfo import ZoneInfo
from pipeline import make_song, render, duration, validate_duration, validate_song, song_duplicate_reason, pipeline_failure_message
from music_cpu import generate
import os


def prepare(run_id, stage='all', check_history=False, vocal_gender='female'):
    if vocal_gender not in ('auto', 'male', 'female'):
        raise ValueError('Vocal choice must be auto, male or female')
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', run_id):
        raise ValueError('Invalid run ID')
    root = Path('output')/run_id
    root.mkdir(parents=True, exist_ok=True)
    checkpoint = root/'generation-state.json'
    state = json.loads(checkpoint.read_text()) if checkpoint.exists() else {}
    def save():
        temporary = checkpoint.with_suffix('.tmp')
        temporary.write_text(json.dumps(state))
        temporary.replace(checkpoint)
    history = []
    lyric_history = []
    store = None
    if check_history:
        from storage import Store
        print(json.dumps({'phase': 'verify publication history'}), flush=True)
        store = Store()
        history = store.load('history.json', [])
        lyric_history = store.load('lyrics-history.json', [])
        history += lyric_history
        # A rerun of an already published identity must resume, not regenerate it.
        history = [entry for entry in history if entry.get('run') != run_id]
    if (root/'song.json').exists():
        song = validate_song(json.loads((root/'song.json').read_text()))
    else:
        song = make_song(dt.datetime.now(ZoneInfo('Asia/Dhaka')).date().isoformat(), history, root/'song-draft.json', generation_id=run_id, vocal_gender_override=vocal_gender)
        (root/'song.json').write_text(json.dumps(song, ensure_ascii=False, indent=2))
    if vocal_gender != 'auto' and song.get('vocal_gender') != vocal_gender:
        raise ValueError('Saved song voice differs from the request; use a new run ID')
    if stage == 'lyrics':
        from rhyme_writer import VERSION, verse_lines, novelty_reason
        if song.get('lyric_writer', {}).get('version') != VERSION:
            raise ValueError('Saved lyrics use the old template writer; use a new run ID')
        lines = verse_lines(song)
        reason = novelty_reason(lines, history)
        if reason or song_duplicate_reason(song, history):
            from pipeline import DuplicateSongError
            raise DuplicateSongError()
        if store:
            entry = dict(run=run_id, title=song['title'], story_summary=song['story_summary'],
                visual_identity=song.get('visual_identity', {}),
                verse_lines=lines, hash=__import__('hashlib').sha256(song['lyrics'].encode()).hexdigest())
            lyric_history = [h for h in lyric_history if h.get('run') != run_id]
            lyric_history.append(entry)
            store.save('lyrics-history.json', lyric_history)
        print(json.dumps({'phase':'lyrics ready', 'run_id':run_id}), flush=True)
        return
    import lyrics_cpu
    if lyrics_cpu._model is not None:
        lyrics_cpu._model.close()
        lyrics_cpu._model = None
    gc.collect()
    if stage == 'images':
        from song_images import generate_song_images
        generate_song_images(root, song)
        print(json.dumps({'phase': 'images ready', 'run_id': run_id}), flush=True)
        return
    if stage == 'all':
        from song_images import generate_song_images
        generate_song_images(root, song)
        import image_cpu
        image_cpu._pipeline = None
        gc.collect()
    if not (root/'song.wav').exists():
        if stage == 'render':
            raise RuntimeError('Music artifact missing; publishing cannot generate through a remote service')
        generate(song, root/'song.wav', state, save)
    validate_duration(duration(root/'song.wav'))
    if stage == 'music':
        print(json.dumps({'phase':'music ready', 'run_id':run_id}), flush=True)
        return
    if not render_is_current(root):
        render(root)
    validate_duration(duration(root/'video.mp4'))
    print(json.dumps({'run_id': run_id, 'phase': 'prepared', 'title': song['title'],
        'duration': duration(root/'video.mp4')}), flush=True)

def prepare_with_retries(run_id, stage='all', check_history=False, vocal_gender='female'):
    """Resume saved lyrics only for explicitly retryable model/content failures."""
    from lyrics_cpu import StoryGenerationError
    for attempt in range(3):
        try:
            result=prepare(run_id,stage,check_history=check_history,vocal_gender=vocal_gender)
            failure=Path('output')/run_id/'failure.json'
            if failure.exists():
                try:
                    previous=json.loads(failure.read_text())
                except (OSError,ValueError):
                    previous={}
                if previous.get('stage')==stage:
                    failure.unlink(missing_ok=True)
            if attempt:
                print(json.dumps({'phase':'lyrics stage recovered','attempt':attempt+1}),flush=True)
            return result
        except StoryGenerationError as error:
            record_failure(run_id,stage,error)
            if stage != 'lyrics' or not error.retryable or attempt == 2:
                raise
            print(json.dumps({'phase':'resume saved lyrics after retryable failure',
                'attempt':attempt+1,'maximum_attempts':3,'error_code':error.code}),flush=True)
            time.sleep(5*(attempt+1))


def record_failure(run_id,stage,error):
    """Persist safe diagnostics even if the first model response never completed."""
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}',run_id):
        return
    root=Path('output')/run_id
    root.mkdir(parents=True,exist_ok=True)
    info={'stage':stage,'error_type':type(error).__name__,
        'error_code':getattr(error,'code','pipeline_error'),
        'retryable':getattr(error,'retryable',False),
        'details':getattr(error,'details',{}),
        'message':pipeline_failure_message(error)}
    temp=root/'failure.tmp'
    temp.write_text(json.dumps(info,indent=2))
    temp.replace(root/'failure.json')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--stage', choices=['all', 'lyrics', 'music', 'images', 'render'], default='all')
    parser.add_argument('--check-history', action='store_true',
                        help='Verify title and lyrics against Drive publication history before costly stages')
    parser.add_argument('--vocal-gender', choices=['auto', 'male', 'female'], default='female')
    args = parser.parse_args()
    try:
        prepare_with_retries(args.run_id, args.stage, check_history=args.check_history, vocal_gender=args.vocal_gender)
    except Exception as error:
        try:
            record_failure(args.run_id,args.stage,error)
        except OSError:
            print("Could not save failure checkpoint; original failure follows.",flush=True)
        print(pipeline_failure_message(error), flush=True)
        raise SystemExit(1)
