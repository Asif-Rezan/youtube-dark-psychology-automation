"""Opening hook once, then new verses interleaved with the separate reference refrain."""
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys

REFRAIN = 'दूदी दूदी दम दम दूदी दूदी दम'
HOOK_END = 19.0
CROSSFADE_SECONDS = .25


def selective_plan(verses, identity, reference_seconds=30):
    if len(verses) != 2 or any(not v.strip() or REFRAIN in v for v in verses):
        raise ValueError('Two original verse blocks without the fixed refrain are required')
    if verses[0].strip() == verses[1].strip():
        raise ValueError('Verse blocks must differ')
    refrain_seconds = float(reference_seconds) - HOOK_END
    verse_seconds = (60 + 4*CROSSFADE_SECONDS - HOOK_END - 2*refrain_seconds)/2
    if not math.isfinite(refrain_seconds) or refrain_seconds <= 0 or verse_seconds < 4:
        raise ValueError('Reference refrain does not fit the one-minute arrangement')
    requests = {}
    for i, lyrics in enumerate(verses):
        key = 'verse-'+str(i+1)
        seed = int(hashlib.sha256((identity+lyrics).encode()).hexdigest()[:8],16)
        requests[key] = dict(_segment=True, duration=math.ceil(verse_seconds)+2,
            vocal_language='hi', vocal_gender='female', bpm=123,
            lyrics='[Verse]\n'+lyrics, reference_cover=False, generation_seed=seed,
            prompt='New original Hindi nursery verse melody for these new lyrics. '
                   'Sweet clear female vocal, D major, 123 BPM, playful ukulele, '
                   'xylophone, handclaps and continuous bass. Do not sing the Dudi refrain '
                   'or repeat the opening hook. Finish the lyric phrase before '
                   f'{verse_seconds-.3:.1f} seconds, followed by instrumental backing.')
    return dict(version='intro-once-reference-refrain-v2', duration=60, requests=requests,
        sequence=['intro','verse-1','refrain','verse-2','refrain'],
        retained_seconds=dict(intro=HOOK_END,refrain=refrain_seconds,
                              **{'verse-1':verse_seconds,'verse-2':verse_seconds}),
        reference_windows=dict(intro=[0,HOOK_END],refrain=[HOOK_END,float(reference_seconds)]),
        crossfade_seconds=CROSSFADE_SECONDS)


def reference_sections(reference, plan, root):
    from pipeline import duration
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    if abs(duration(reference)-plan['reference_windows']['refrain'][1]) > .05:
        raise ValueError('Reference length differs from the arranged reference')
    paths={}
    for key,(start,end) in plan['reference_windows'].items():
        target=root/(key+'.wav')
        subprocess.run(['ffmpeg','-y','-v','error','-i',str(reference),'-ss',str(start),
            '-t',str(end-start),'-ar','44100','-ac','2',str(target)],check=True)
        if abs(duration(target)-(end-start)) > .05:
            raise ValueError('Extracted '+key+' duration mismatch')
        paths[key]=target
    return paths


def assemble(plan, paths, target):
    from pipeline import duration
    sequence=plan['sequence'];lengths=plan['retained_seconds']
    if sequence.count('intro') != 1 or sequence[0] != 'intro':
        raise ValueError('Opening hook must occur exactly once at the beginning')
    if Path(paths['intro']).resolve() == Path(paths['refrain']).resolve():
        raise ValueError('Opening hook and recurring refrain must be separate clips')
    command=['ffmpeg','-y','-v','error'];filters=[]
    for i,key in enumerate(sequence):
        if duration(paths[key]) + .01 < lengths[key]:
            raise ValueError('Audio '+key+' is too short; do not pad or loop verses')
        command += ['-i',str(paths[key])]
        filters.append(f'[{i}:a]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo,'
            f'atrim=duration={lengths[key]},asetpts=PTS-STARTPTS[a{i}]')
    previous='a0'
    for i in range(1,len(sequence)):
        label='j'+str(i)
        filters.append(f'[{previous}][a{i}]acrossfade=d={plan["crossfade_seconds"]}:c1=tri:c2=tri[{label}]')
        previous=label
    filters.append(f'[{previous}]alimiter=limit=0.84:level=false[out]')
    subprocess.run(command+['-filter_complex',';'.join(filters),'-map','[out]',
        '-t','60','-ar','44100','-ac','2',str(target)],check=True)
    if abs(duration(target)-60) > .05:
        raise ValueError('Arrangement is not 60 seconds: '+str(duration(target)))


def render(plan, root):
    from music_cpu import reference_audio
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    reference=Path(reference_audio())
    paths=reference_sections(reference,plan,root/'reference-sections')
    (root/'arrangement.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2))
    for key,request in plan['requests'].items():
        part=root/key;part.mkdir(exist_ok=True)
        request_path=part/'song.json';request_path.write_text(json.dumps(request,ensure_ascii=False,indent=2))
        target=part/'audio.wav'
        env=dict(os.environ, REFERENCE_AUDIO_PATH=str(paths['refrain'].resolve()))
        # The opening hook is never passed into verse conditioning.
        subprocess.run([sys.executable,'-u',str(Path(__file__).with_name('music_cpu.py')),
            '--song',str(request_path),'--target',str(target),
            '--source',env['ACESTEP_SOURCE_DIR'],'--models',env['ACESTEP_CHECKPOINTS_DIR']],
            env=env,check=True,timeout=18000)
        paths[key]=target
    target=root/'dudi-new-verses-60s.wav';assemble(plan,paths,target)
    subprocess.run(['ffmpeg','-y','-v','error','-i',str(target),'-codec:a','libmp3lame',
        '-b:a','192k',str(target.with_suffix('.mp3'))],check=True)
    (root/'arrangement-report.json').write_text(json.dumps(dict(seconds=60,
        unique_syntheses=2,opening_hook_uses=1,opening_hook_window=[0,19],
        refrain_window=plan['reference_windows']['refrain'],refrain_uses=2,
        reference_sha256=hashlib.sha256(reference.read_bytes()).hexdigest(),
        verse_generation='new text2music; voice-style reference excludes the opening hook',
        vocal_alignment='Generative vocal timing and joins require listening review'),indent=2))
    return target
