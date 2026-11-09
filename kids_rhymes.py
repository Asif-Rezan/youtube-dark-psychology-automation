"""Offline rhyme planning, checkpointed music parts and five-second story scenes."""
import hashlib
import json
import math
import os
import re
import shutil
from pathlib import Path
import subprocess

from rhyme_writer import write_rhyme, REFRAIN, CHORUS
SONG_FORM = 'chorus-first-verse-chorus-v2-episode-hook'
MIN_SECONDS, MAX_SECONDS, DEFAULT_SECONDS = 180, 300, 240


def song_form(seconds):
    """Open on the full chorus hook, then alternate four-line verses and choruses."""
    slots=seconds//5
    form=[('chorus',min(4,slots))]
    used=form[0][1]
    while slots-used>4:
        for kind in ('verse','chorus'):
            n=min(4,slots-used)
            if n>0:
                form.append((kind,n))
                used+=n
    if used<slots:
        form.append(('chorus',slots-used))
    return form


# Distinct dance poses so consecutive chorus scenes never repeat a composition.
CHORUS_POSES = (
    'All dance together, waving arms and stepping feet.',
    'All clap hands together above their heads, big happy smiles.',
    'All jump up high together with arms stretched wide.',
    'All spin around in a happy circle, holding hands.',
    'All wiggle and shake side to side, tiny feet tapping.',
    'All march in a line, knees up, swinging arms.',
    'All bounce and bob together, paws and hands in the air.',
    'All twirl and pose, one leg lifted, arms out like stars.',
)


def episode_lighting(outline):
    """One time of day for every scene and the thumbnail, from the saved world."""
    world=(outline.get('visual_world','')+' '+outline.get('characters','')).lower()
    if re.search(r'\b(night|moon|moonlit|moonlight|stars?|starry|evening|dusk|sunset|twilight)\b',world):
        return 'soft moonlit evening'
    return 'bright sunny daytime'
from scene_actions import plan_scene

def scene_prompt(row,outline,dance=False,lighting=None,pose=None):
    """Restore the original soft animal-led look, with children as companions."""
    cast=outline.get('characters','')
    animals=list(dict.fromkeys(re.findall(r'\b(bunny|rabbit|hare|duckling|duck|chick|puppy|dog|kitten|cat|turtle|elephant|panda|lamb|fox|bear|deer|calf|penguin|squirrel)\b',cast,re.I)))[:2]
    subjects=' and '.join('baby '+animal.lower() for animal in animals) or 'cute baby animal friends'
    action = ((pose or CHORUS_POSES[0]) if dance
              else 'All play together. ' + row['visual'])
    return ('Cute colorful 3D storybook cartoon. Two cute human toddlers in colorful clothes '
        'beside adorable '+subjects+'. Both babies and animals equally prominent, '
        'separate full bodies, smiling faces, visible hands and feet. '+action+' '
        'Dreamy natural flower garden, soft light, rounded shapes, pastel colors. '
        +outline.get('visual_world','Dreamy natural flower garden')+'. '+cast+'. '
        'The two human babies stay visible alongside the animals, no solo animal portrait, '
        'wide landscape, no text. Consistent '+(lighting or episode_lighting(outline))+
        ' lighting and the same pastel color palette in every scene.')


def make_song(day, history, draft_path=None, generation_id=None, vocal_gender_override='female'):
    if vocal_gender_override not in ('auto', 'female'):
        raise ValueError('Dudi Dam TV uses female vocals')
    seconds = int(os.getenv('VIDEO_DURATION_SECONDS', str(DEFAULT_SECONDS)))
    if not MIN_SECONDS <= seconds <= MAX_SECONDS or seconds % 5:
        raise ValueError(f'VIDEO_DURATION_SECONDS must be {MIN_SECONDS}-{MAX_SECONDS}, in five-second steps')
    identity = generation_id or day
    form = song_form(seconds)
    verse_count = sum(n for kind, n in form if kind == 'verse')
    written = write_rhyme(day, identity, seconds, history, draft_path, verse_count=verse_count)
    outline = written['outline']
    lighting = episode_lighting(outline)
    chorus = tuple(outline.get('chorus') or CHORUS)
    rows = iter([row for section in written['sections'] for row in section])
    scenes = []
    for kind, count in form:
        for j in range(count):
            i = len(scenes)
            if kind == 'verse':
                row = next(rows)
                lyric, dance = row['lyric'], False
                motion_text = row['lyric']+' '+row['visual']
            else:
                row, lyric, dance = {}, chorus[j % len(chorus)], True
                # Chorus words pick literal moves: clapping, then jumping and spinning.
                motion_text = 'Two human toddlers and cute baby animals dancing together, '+lyric
            motion_text += ' at 130 BPM'
            scenes.append(dict(index=i,start=i*5,end=(i+1)*5,lyric=lyric,section=kind,
                prompt=scene_prompt(row,outline,dance,lighting,CHORUS_POSES[i % len(CHORUS_POSES)] if dance else None),
                cast_style='cute-babies-and-animals-together-v4',visual_action=motion_text,story_action=plan_scene(motion_text,i)))
    outline=written['outline']
    song = dict(title=outline['title'], lyrics='\n'.join(scene['lyric'] for scene in scenes),duration=seconds,
        song_form=SONG_FORM, lighting=lighting,
        chorus=list(chorus), hook=chorus[0],
        prompt=('Upbeat bouncy kids pop dance song, 130 BPM, 4/4, strong steady groove toddlers can clap and jump to. '
            'Starts instantly on the first beat with the full high-energy chorus, no instrumental intro. '
            'Punchy kick drum on every beat, snappy snare and loud handclaps on 2 and 4, bouncy staccato bass, '
            'bright marimba and glockenspiel riff answering each vocal line, cheerful ukulele strums. '
            'Short simple repetitive sing-along melody; the chorus hook "'+chorus[0]+'" is a catchy chant with call-and-response kids backing vocals. '
            'Cute sweet adult female lead voice, clear English diction, C major. '
            'Continuous lively backing under every line, no silent breaks, no slow ballad sections, no shouting. '
            'Ends with a short energetic final chorus and a crisp button ending with a cymbal hit, no long fade-out.'),
        description=outline['description'],story_summary=outline['story_summary'],
        visual_identity=dict(characters=outline.get('characters',''), world=outline.get('visual_world','')),
        lyric_writer=dict(backend='local-qwen-cpu',version=written['writer_version'],novelty_checked=True),
        vocal_gender='female',song_date=day,scenes=scenes,bpm=130,
        audio_mastering='continuous-kids-mix-v3',
        tags=['Dudi Dam TV','kids rhymes','nursery rhymes','kids dance song',chorus[0][:40]])
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


def tagged_lyrics(scenes):
    """ACE-Step section tags so the chorus is sung as the energetic hook."""
    lines, previous = [], None
    last = max((i for i, s in enumerate(scenes) if s.get('section') == 'verse'), default=None)
    for i, scene in enumerate(scenes):
        section = scene.get('section')
        if section and section != previous:
            if section == 'verse':
                lines.append('[Verse]')
            elif last is not None and i > last:
                lines.append('[Final Chorus - big energetic finish]')
            else:
                lines.append('[Chorus - high energy]')
        previous = section
        lines.append(scene['lyric'])
    return '\n'.join(lines)


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
    # keep episodes within that contract, with no audio looping.
    parts = []
    scenes = song['scenes']
    for i in range(0, len(scenes), 24):
        group = scenes[i:i+24]
        part = dict(song, duration=len(group)*5, lyrics=tagged_lyrics(group), _segment=True)
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
