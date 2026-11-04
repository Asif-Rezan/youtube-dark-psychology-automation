"""Offline rhyme planning, checkpointed music parts and five-second story scenes."""
import hashlib
import json
import math
import os
import re
import shutil
from pathlib import Path
import subprocess

REFRAIN = 'dudi dudi dam dam dudi dudi dam'
from rhyme_writer import write_rhyme
from scene_actions import plan_scene

def scene_prompt(row,outline,dance=False):
    """Restore the original soft animal-led look, with children as companions."""
    cast=outline.get('characters','')
    animals=list(dict.fromkeys(re.findall(r'\b(bunny|rabbit|hare|duckling|duck|chick|puppy|dog|kitten|cat|turtle|elephant|panda|lamb|fox|bear|deer|calf|penguin|squirrel)\b',cast,re.I)))[:2]
    subjects=' and '.join('baby '+animal.lower() for animal in animals) or 'cute baby animal friends'
    action = ('All dance together, waving arms and stepping feet.' if dance
              else 'All play together. ' + row['visual'])
    return ('Cute colorful 3D storybook cartoon. Two cute human toddlers in colorful clothes '
        'beside adorable '+subjects+'. Both babies and animals equally prominent, '
        'separate full bodies, smiling faces, visible hands and feet. '+action+' '
        'Dreamy natural flower garden, soft light, rounded shapes, pastel colors. '
        +outline.get('visual_world','Dreamy natural flower garden')+'. '+cast+'. '
        'The two human babies stay visible alongside the animals, no solo animal portrait, '
        'wide landscape, no text.')


def make_song(day, history, draft_path=None, generation_id=None, vocal_gender_override='female'):
    if vocal_gender_override not in ('auto', 'female'):
        raise ValueError('Dudi Dam TV uses female vocals')
    seconds = int(os.getenv('VIDEO_DURATION_SECONDS', '600'))
    if not 480 <= seconds <= 720 or seconds % 5:
        raise ValueError('VIDEO_DURATION_SECONDS must be 480-720, in five-second steps')
    identity = generation_id or day
    written = write_rhyme(day, identity, seconds, history, draft_path)
    outline = written['outline']
    scenes = []
    for section in written['sections']:
        for row in section:
            # Put both cast types and the established style before the encoder
            # token limit. Refrains get a distinct dancing composition.
            for lyric in (row['lyric'], REFRAIN):
                i=len(scenes)
                dance=lyric==REFRAIN
                prompt=scene_prompt(row,outline,dance)
                motion_text=('Two human toddlers and cute baby animals dancing together' if dance
                             else row['lyric']+' '+row['visual'])+' at 120 BPM'
                scenes.append(dict(index=i,start=i*5,end=(i+1)*5,lyric=lyric,prompt=prompt,
                    cast_style='cute-babies-and-animals-together-v4',visual_action=motion_text,story_action=plan_scene(motion_text,i)))
    scenes=scenes[:seconds//5]
    outline=written['outline']
    song = dict(title=outline['title'], lyrics='\n'.join(scene['lyric'] for scene in scenes),duration=seconds,
        prompt='Joyful nursery rhyme, cute sweet adult female singing voice, clear English diction, playful dudi dudi dam dam refrain, C major, 120 BPM, bouncy ukulele, bright xylophone, steady handclaps and gentle bass. Continuous lively instrumental backing under every vocal line, no silent breaks, no stop-start pauses, no shouting.',
        description=outline['description'],story_summary=outline['story_summary'],
        visual_identity=dict(characters=outline.get('characters',''), world=outline.get('visual_world','')),
        lyric_writer=dict(backend='local-qwen-cpu',version=written['writer_version'],novelty_checked=True),
        vocal_gender='female',song_date=day,scenes=scenes,bpm=120,
        audio_mastering='continuous-kids-mix-v3',
        tags=['Dudi Dam TV','kids rhymes','nursery rhymes','Dudi Dudi Dam Dam','kids dance'])
    validate_storyboard(song)
    return song


def validate_storyboard(song):
    if song.get('vocal_gender') != 'female':
        raise ValueError('Female vocal required')
    scenes = song.get('scenes', [])
    if len(scenes) != song['duration'] / 5:
        raise ValueError('One scene per five seconds required')
    for i, scene in enumerate(scenes):
        if (scene.get('index'), scene.get('start'), scene.get('end')) != (i, i*5, (i+1)*5):
            raise ValueError('Non-contiguous storyboard')
        if not scene.get('lyric') or not scene.get('prompt'):
            raise ValueError('Scene lyric and prompt required')
    if song['lyrics'] != '\n'.join(scene['lyric'] for scene in scenes):
        raise ValueError('Storyboard lyrics must match sung lyrics')


def upload_description(song):
    return song['description'] + '\n\nOriginal kids rhyme arrangement by Dudi Dam TV.\n#KidsRhymes #DudiDamTV #NurseryRhymes'


def metadata_tags(song):
    return list(dict.fromkeys(song.get('tags', []) + ['Dudi Dam TV', 'kids rhymes']))


def generate_music(song, target, state, save):
    from pipeline import validate_song, validate_duration, duration
    from music_cpu import generate_segment
    validate_song(song)
    from audio_mastering import VERSION, AudioGapError, verify_continuity, master_parts, uses_continuous_mix
    continuous=uses_continuous_mix(song)
    if target.exists() and (not continuous or state.get('mastering_version')==VERSION):
        validate_duration(duration(target))
        return
    # ACE-Step documents up to 600 seconds per request. Short independent parts
    # keep 8-12 minute episodes within that contract, with no audio looping.
    parts = []
    scenes = song['scenes']
    for i in range(0, len(scenes), 24):
        group = scenes[i:i+24]
        part = dict(song, duration=len(group)*5, lyrics='\n'.join(s['lyric'] for s in group), _segment=True)
        path = target.parent / f'part-{i//24:03d}.wav'
        part_state = state.setdefault('parts', {}).setdefault(str(i//24), {})
        if continuous and not path.exists():
            for candidate in sorted(path.parent.glob(path.stem+'.rejected*.wav'),reverse=True):
                try:
                    window=verify_continuity(candidate,part['duration'])
                except (AudioGapError,subprocess.CalledProcessError,OSError,ValueError):
                    continue
                shutil.copyfile(candidate,path)
                part_state.update(recovered_candidate=candidate.name,quality_window=window)
                save()
                print(json.dumps({'phase':'recovered saved music candidate','part':i//24,
                    'candidate':candidate.name}),flush=True)
                break
        for attempt in range(3 if continuous else 1):
            generate_segment(part,path,part_state,save)
            try:
                if continuous:
                    part_state['quality_window']=verify_continuity(path,part['duration'])
                    part_state.update(audio_ready=True,generation_started=False)
                    part_state.pop('last_quality_error',None)
                    save()
                break
            except AudioGapError as error:
                print(json.dumps({'phase':'retry invalid music part','part':i//24,
                    'attempt':attempt+1,'reason':error.code,'detail':str(error)}),flush=True)
                part_state['last_quality_error']=dict(code=error.code,detail=str(error))
                part_state.update(audio_ready=False,continuity_retries=attempt+1)
                save()
                path.replace(path.with_suffix(f'.rejected-gap-{attempt+1}.wav'))
                if attempt==2:
                    raise AudioGapError(f'Music part {i//24} failed three quality attempts ({error.code}); saved parts retained. '+str(error),code=error.code) from error
        parts.append(path)
    # Normalize every part to the planned boundary, refusing short generations.
    normalized = []
    for i, path in enumerate(parts):
        requested = min(120, song['duration']-i*120)
        if duration(path) < requested - .25:
            raise RuntimeError('Music part is too short; regenerate rather than pad or loop')
        dest = target.parent / f'normalized-{i:03d}.wav'
        subprocess.run(['ffmpeg', '-y', '-i', str(path), '-t', str(requested), '-ar', '44100', '-ac', '2', str(dest)], check=True, capture_output=True)
        normalized.append(dest)
    if continuous:
        state['mastering']=master_parts(normalized,target,song['duration'])
        state.update(audio_ready=True,mastering_version=VERSION)
        save()
        return
    listing = target.parent/'audio-parts.txt'
    listing.write_text(''.join(f"file '{p.name}'\n" for p in normalized))
    temporary = target.with_suffix('.tmp.wav')
    subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '1', '-i', str(listing), '-c', 'copy', str(temporary)], check=True, capture_output=True)
    validate_duration(duration(temporary))
    temporary.replace(target)
    state['audio_ready'] = True
    save()


def render_video(root):
    from PIL import Image, ImageOps
    from pipeline import duration, validate_duration, validate_song
    root = Path(root)
    song = validate_song(json.loads((root/'song.json').read_text()))
    seconds = duration(root/'song.wav')
    validate_duration(seconds)
    if abs(seconds-song['duration']) > .25:
        raise ValueError('Audio does not match storyboard duration')
    from motion_video import render_animated
    render_animated(root, song)
