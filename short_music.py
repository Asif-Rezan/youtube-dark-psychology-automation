"""Synthesize a separate short rhyme arrangement from the selected storyboard."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import shutil

from shorts import atomic_json, digest, probe, validate_clip


def prepare(run_id, start=0, seconds=40):
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', run_id):
        raise ValueError('Invalid source run ID')
    validate_clip(start, seconds)
    root = Path('output')/run_id
    song = json.loads((root/'song.json').read_text())
    from kids_rhymes import validate_storyboard
    validate_storyboard(song)
    if start + seconds > song['duration']:
        raise ValueError('Short music exceeds storyboard')
    scenes = song['scenes'][start//5:(start+seconds)//5]
    request = dict(song, _segment=True, duration=seconds,
        lyrics='\n'.join(s['lyric'] for s in scenes), scenes=scenes,
        prompt=song['prompt'] + ' A fresh standalone short dance arrangement, immediate cheerful vocal hook, '
            'playful rhythmic accents, a complete happy musical ending within this short duration.')
    target = root/'short-audio'/f'clip-{start}-{seconds}'
    target.mkdir(parents=True, exist_ok=True)
    identity = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
    checkpoint = target/'music-state.json'
    state = json.loads(checkpoint.read_text()) if checkpoint.exists() else {}
    if state and state.get('identity') != identity:
        raise ValueError('Saved Shorts music belongs to another request')
    state['identity'] = identity
    def save():
        atomic_json(checkpoint, state)
    save()
    atomic_json(target/'song.json', request)
    output = target/'song.wav'
    if output.exists() and state.get('output_sha256') == digest(output):
        verify_audio(output, seconds)
        return output
    from music_cpu import generate_segment
    raw = target/'generated.wav'
    from audio_mastering import VERSION, AudioGapError, verify_continuity, uses_continuous_mix
    continuous=uses_continuous_mix(request)
    # Failed older runs retained the native syntheses even if generated.wav was
    # removed by the old retry loop. Reuse a valid candidate before inference.
    recovered=False
    recovery_rejections=[]
    if continuous:
        candidates=([raw] if raw.exists() else [])+sorted((target/'cpu-audio').glob('*.wav'))
        for candidate in candidates:
            try:
                window=verify_continuity(candidate,seconds)
            except AudioGapError as error:
                recovery_rejections.append(dict(candidate=candidate.name,code=error.code,detail=str(error)))
                continue
            except (subprocess.CalledProcessError,ValueError) as error:
                recovery_rejections.append(dict(candidate=candidate.name,code='unreadable_candidate',error_type=type(error).__name__))
                continue
            if candidate!=raw:
                shutil.copyfile(candidate,raw)
            state['recovered_candidate']=candidate.name
            state['quality_window']=window
            save()
            recovered=True
            break
        state['recovery_rejections']=recovery_rejections
        save()
    last_error=None
    for attempt in range(0 if recovered else 3):
        generate_segment(request,raw,state,save)
        try:
            measured=float(probe(raw)['format']['duration'])
            if measured<seconds-.1:
                raise AudioGapError(f'Generated audio is {measured:.3f}s; requires {seconds}s','too_short')
            if continuous:
                state['quality_window']=verify_continuity(raw,seconds)
            break
        except AudioGapError as error:
            last_error=error
            detail=dict(attempt=attempt+1,code=error.code,detail=str(error))
            state.setdefault('quality_attempts',[]).append(detail)
            state['quality_attempts']=state['quality_attempts'][-10:]
            raw.replace(target/f'rejected-{attempt+1}.wav')
            state.update(short_duration_retries=attempt+1,audio_ready=False)
            save()
            print(json.dumps({'phase':'retry Shorts audio quality',**detail}),flush=True)
    if not recovered and last_error is not None and not raw.exists():
        raise ValueError(f'Shorts audio failed three quality attempts ({last_error.code}); candidates and music-state.json retained')
    temporary = target/'song.tmp.wav'
    try:
        from audio_mastering import master_parts
        if continuous:
            state['mastering']=master_parts([raw],temporary,seconds)
        else:
            subprocess.run(['ffmpeg','-y','-v','error','-i',str(raw),'-t',str(seconds),
                '-ar','44100','-ac','2',str(temporary)],check=True,capture_output=True)
        verify_audio(temporary, seconds)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    state['output_sha256'] = digest(output)
    state['audio_ready'] = True
    state['generation_started'] = False
    save()
    print(json.dumps({'phase':'independent Shorts music ready','seconds':seconds}),flush=True)
    return output


def verify_audio(path, seconds):
    info = probe(path)
    if not any(s['codec_type']=='audio' for s in info.get('streams', [])):
        raise ValueError('Short music has no audio stream')
    if abs(float(info['format']['duration']) - seconds) > .1:
        raise ValueError('Short music duration mismatch')


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--run-id',required=True)
    parser.add_argument('--start',type=int,default=0)
    parser.add_argument('--seconds',type=int,default=40)
    args=parser.parse_args()
    prepare(args.run_id,args.start,args.seconds)
