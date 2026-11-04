"""Replace verse words inside one source-backed arrangement, preserving fixed sections."""
import array
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import wave

RATE=44100
VERSE_WINDOWS=((19.,28.5),(39.5,49.))


def read_pcm(path):
    with wave.open(str(path),'rb') as audio:
        if (audio.getnchannels(),audio.getsampwidth(),audio.getframerate()) != (2,2,RATE):
            raise ValueError('Expected stereo 16-bit 44100Hz PCM')
        return audio.readframes(audio.getnframes())


def write_pcm(path,data):
    with wave.open(str(path),'wb') as audio:
        audio.setnchannels(2);audio.setsampwidth(2);audio.setframerate(RATE);audio.writeframes(data)


def source_arrangement(reference,root):
    from chorus_arrangement import selective_plan, reference_sections
    # Reuse only reference musical material as the verse placeholder/context.
    plan=selective_plan(['temporary first verse','temporary second verse'],'source')
    paths=reference_sections(reference,plan,root/'reference-sections')
    intro=read_pcm(paths['intro']);refrain=read_pcm(paths['refrain'])
    placeholder=refrain[:int(9.5*RATE)*4]
    data=intro+placeholder+refrain+placeholder+refrain
    target=root/'source-arrangement.wav';write_pcm(target,data)
    return target,paths['refrain']


def protect_fixed_sections(source,edited,target,blend_seconds=.1):
    original=read_pcm(source);generated=read_pcm(edited)
    if len(original) != 60*RATE*4 or len(generated) < int(49*RATE)*4:
        raise ValueError('Source or edited audio is too short')
    result=bytearray(original)
    for start,end in VERSE_WINDOWS:
        first,last=int(start*RATE)*4,int(end*RATE)*4
        old=array.array('h',original[first:last]);new=array.array('h',generated[first:last])
        # Edges blend inside the verse window; original fixed sections stay untouched.
        frames=len(new)//2;blend=min(round(blend_seconds*RATE),frames//2)
        for frame in range(blend):
            alpha=frame/max(1,blend)
            for channel in range(2):
                a=frame*2+channel;b=(frames-1-frame)*2+channel
                new[a]=round(old[a]*(1-alpha)+new[a]*alpha)
                new[b]=round(old[b]*(1-alpha)+new[b]*alpha)
        result[first:last]=new.tobytes()
    write_pcm(target,bytes(result))


def render_coherent(verses,identity,root):
    from music_cpu import reference_audio
    from chorus_arrangement import REFRAIN
    if len(verses)!=2 or len(set(verses))!=2 or any(not v.strip() or REFRAIN in v for v in verses):
        raise ValueError('Two distinct new verse blocks required')
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    source,refrain=source_arrangement(reference_audio(),root)
    request=dict(_segment=True,duration=60,vocal_language='hi',reference_repaint=True,
        edit_source=str(source.resolve()),edit_start=19,edit_end=49,
        generation_seed=int(hashlib.sha256((identity+'\n'.join(verses)).encode()).hexdigest()[:8],16),
        lyrics='\n'.join(['[Intro]','[Verse]',verses[0],'[Chorus]',REFRAIN,REFRAIN,
                         '[Verse]',verses[1],'[Chorus]',REFRAIN,REFRAIN]),
        prompt='Continue this exact source song, same singer, instruments, accompaniment, '
               'tempo, tonal center, groove, melody phrasing and mix. Only replace the '
               'verse words with the supplied Hindi lyrics, fitting the existing musical '
               'phrases. First verse at 19-28.5 seconds, second at 39.5-49 seconds. '
               'No new genre, instrumentation, voice or opening-hook repetitions.')
    (root/'song.json').write_text(json.dumps(request,ensure_ascii=False,indent=2))
    edited=root/'edited-full-mix.wav'
    env=dict(os.environ,REFERENCE_AUDIO_PATH=str(refrain.resolve()))
    subprocess.run([sys.executable,'-u',str(Path(__file__).with_name('music_cpu.py')),
        '--song',str(root/'song.json'),'--target',str(edited),
        '--source',env['ACESTEP_SOURCE_DIR'],'--models',env['ACESTEP_CHECKPOINTS_DIR']],
        env=env,check=True,timeout=18000)
    decoded=root/'edited-pcm.wav'
    subprocess.run(['ffmpeg','-y','-v','error','-i',str(edited),'-ar',str(RATE),'-ac','2',
        '-c:a','pcm_s16le',str(decoded)],check=True)
    target=root/'dudi-new-verses-60s.wav';protect_fixed_sections(source,decoded,target)
    subprocess.run(['ffmpeg','-y','-v','error','-i',str(target),'-codec:a','libmp3lame',
        '-b:a','192k',str(target.with_suffix('.mp3'))],check=True)
    (root/'arrangement-report.json').write_text(json.dumps(dict(seconds=60,
        method='single source-context repaint; restore original fixed sections',
        opening_hook_uses=1,refrain_uses=2,verse_windows=VERSE_WINDOWS,
        fixed_pcm_sections_preserved=True,
        quality='Verse words, backing consistency and phrasing require listening review'),indent=2))
    return target
