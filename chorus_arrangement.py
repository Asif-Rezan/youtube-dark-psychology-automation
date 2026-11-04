"""Separate a reusable reference chorus from independently generated new verses."""
import hashlib
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys

REFRAIN = 'दूदी दूदी दम दम दूदी दूदी दम'
PART_SECONDS = 15.1875
CROSSFADE_SECONDS = .25


def selective_plan(verses, identity):
    if len(verses) != 2 or any(not v.strip() or REFRAIN in v for v in verses):
        raise ValueError('Two original verse blocks without the fixed chorus are required')
    if verses[0].strip() == verses[1].strip():
        raise ValueError('Verse blocks must differ')
    common = dict(_segment=True, duration=16, vocal_language='hi', vocal_gender='female', bpm=123)
    chorus = dict(common, lyrics='[Chorus]\n'+REFRAIN+'\n'+REFRAIN,
        reference_cover=True, cover_strength=1.0, cover_noise_strength=.95,
        generation_seed=20261107,
        prompt='Preserve the reference Dudi hook melody, rhythm, voice and backing. '
               'Sweet clear single female nursery vocal, D major, 123 BPM. '
               'Sing the identical Dudi chorus twice, finish the vocal phrase before 15 seconds.')
    requests = {'chorus': chorus}
    for i, lyrics in enumerate(verses):
        key = 'verse-'+str(i+1)
        seed = int(hashlib.sha256((identity+lyrics).encode()).hexdigest()[:8],16)
        requests[key] = dict(common, lyrics='[Verse]\n'+lyrics, reference_cover=False,
            generation_seed=seed,
            prompt='New original Hindi nursery verse melody for these lyrics. '
                   'Same sweet clear female vocal style, D major, 123 BPM, '
                   'bouncy ukulele, xylophone, handclaps and continuous bass. '
                   'Do not copy the reference verse melody or sing the Dudi refrain. '
                   'Finish the four lyric lines naturally before 15 seconds.')
    return dict(version='selective-chorus-v1', duration=60, requests=requests,
                sequence=['chorus','verse-1','verse-2','chorus'],
                retained_seconds=PART_SECONDS, crossfade_seconds=CROSSFADE_SECONDS)


def assemble(plan, paths, target):
    from pipeline import duration
    for key in plan['sequence']:
        if duration(paths[key]) < PART_SECONDS:
            raise ValueError('Generated '+key+' is too short; do not pad or loop verse audio')
    command=['ffmpeg','-y','-v','error']
    for key in plan['sequence']:
        command += ['-i',str(paths[key])]
    filters=[f'[{i}:a]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo,'
             f'atrim=duration={PART_SECONDS},asetpts=PTS-STARTPTS[a{i}]' for i in range(4)]
    filters += ['[a0][a1]acrossfade=d=0.25:c1=tri:c2=tri[j1]',
                '[j1][a2]acrossfade=d=0.25:c1=tri:c2=tri[j2]',
                '[j2][a3]acrossfade=d=0.25:c1=tri:c2=tri,'
                'alimiter=limit=0.84:level=false[out]']
    subprocess.run(command+['-filter_complex',';'.join(filters),'-map','[out]',
                   '-t','60','-ar','44100','-ac','2',str(target)],check=True)
    if abs(duration(target)-60) > .05:
        raise ValueError('Selective chorus arrangement is not 60 seconds: '+str(duration(target)))


def render(plan, root):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    (root/'arrangement.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2))
    paths={}
    for key, request in plan['requests'].items():
        part=root/key;part.mkdir(exist_ok=True)
        request_path=part/'song.json'
        request_path.write_text(json.dumps(request,ensure_ascii=False,indent=2))
        target=part/'audio.wav'
        approved = os.environ.get('DUDI_APPROVED_CHORUS') if key == 'chorus' else None
        if approved:
            from pipeline import duration
            if not Path(approved).is_file() or duration(approved) < PART_SECONDS:
                raise ValueError('Approved chorus asset is missing or too short')
            shutil.copyfile(approved,target)
            paths[key]=target
            continue
        # Fresh process per block avoids reinitializing PyTorch thread pools.
        subprocess.run([sys.executable,'-u',str(Path(__file__).with_name('music_cpu.py')),
            '--song',str(request_path),'--target',str(target),'--source',os.environ['ACESTEP_SOURCE_DIR'],
            '--models',os.environ['ACESTEP_CHECKPOINTS_DIR']],check=True,timeout=18000)
        paths[key]=target
    target=root/'dudi-new-verses-60s.wav'
    assemble(plan,paths,target)
    subprocess.run(['ffmpeg','-y','-v','error','-i',str(target),'-codec:a','libmp3lame',
                    '-b:a','192k',str(target.with_suffix('.mp3'))],check=True)
    (root/'arrangement-report.json').write_text(json.dumps(dict(
        seconds=60,unique_syntheses=3,chorus_reused=True,
        verse_generation='independent text2music with voice-style reference only',
        waveform_alignment='Crossfaded sections; vocal word alignment requires listening review'),indent=2))
    return target
