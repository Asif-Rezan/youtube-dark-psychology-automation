"""Generate, render and publish a prehistoric documentary through existing services."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
import wave

import numpy as np

from storage import Store
from .editorial import ancient_humans_title,generate,metadata
from .visuals import SIZE,cover,scene

FPS = 24
RATE = 24000
FULL_RUNTIME = (900,1500)
DEFAULT_NARRATION_SPEED = .95
NARRATION_PAUSE = .33
NARRATION_WPM = (105,185)
VOICE_PITCH_SEMITONES = -2
MASTER_GAIN = 2.0


def ffmpeg(*args):
    subprocess.run(['ffmpeg','-v','error','-y',*map(str,args)],check=True)


def write_json(path,data):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    temp.replace(path)


def speech_writer():
    from kokoro import KPipeline
    engine = KPipeline(lang_code='a',device='cpu',repo_id='hexgrad/Kokoro-82M')

    def speak(text,target,*,speed=DEFAULT_NARRATION_SPEED):
        clips = [samples.numpy() for _,_,samples in engine(text,voice='am_michael',speed=speed) if samples is not None]
        if not clips:
            raise RuntimeError('Kokoro returned no narration')
        audio = np.clip(np.concatenate(clips),-1,1)
        with wave.open(str(target),'wb') as stream:
            stream.setparams((1,2,RATE,0,'NONE',''))
            stream.writeframes((audio*32767).astype('<i2').tobytes())
    return speak


def clip(beat,index,frames,target,chapter_label=None):
    command = ['ffmpeg','-y','-v','error','-f','rawvideo','-pix_fmt','rgb24',
               '-s',f'{SIZE[0]}x{SIZE[1]}','-r',str(FPS),'-i','pipe:0',
               '-vf','scale=1920:1080','-an','-c:v','libx264','-threads','4',
               '-preset','veryfast','-pix_fmt','yuv420p',str(target)]
    with subprocess.Popen(command,stdin=subprocess.PIPE) as process:
        try:
            for frame in range(frames):
                process.stdin.write(scene(beat,frame/FPS,frames/FPS,index,chapter_label).tobytes())
        finally:
            process.stdin.close()
        if process.wait():
            raise RuntimeError(f'Prehistory shot {index+1} failed to encode')


def soundtrack(target,seconds,beats):
    """Light documentary music with quiet activity sounds tied to the animation."""
    total = round(seconds*RATE)
    signal = np.zeros(total,dtype=np.float32)
    chords = ((45,52,57),(48,55,60),(41,48,53),(43,50,55))
    for index,start in enumerate(range(0,total,round(3.2*RATE))):
        count = min(round(3.2*RATE),total-start)
        t = np.arange(count,dtype=np.float32)/RATE
        envelope = np.sin(np.pi*t/3.2)**2
        for note in chords[index%len(chords)]:
            frequency = 440*2**((note-69)/12)
            signal[start:start+count] += .026*envelope*np.sin(2*np.pi*frequency*t)
        for pulse in range(4):
            offset = round(pulse*.8*RATE)
            length = min(count-offset,round(.7*RATE))
            if length > 0:
                dt = t[:length]
                hz = 440*2**((chords[index%len(chords)][pulse%3]+12-69)/12)
                signal[start+offset:start+offset+length] += (
                    .024*np.minimum(dt*90,1)*np.exp(-6*dt)*np.sin(2*np.pi*hz*dt)
                )
    rng = np.random.default_rng(813)
    for start,duration,beat in beats:
        actions = [member['action'] for member in beat.get('cast',())] or [beat.get('action')]
        if beat['prop']=='stone' and 'work' in actions:
            for at in np.arange(.22,min(duration,3.5),.90):
                offset = round((start+at)*RATE)
                count = min(round(.09*RATE),total-offset)
                t = np.arange(count,dtype=np.float32)/RATE
                signal[offset:offset+count] += (
                    (.030*np.sin(2*np.pi*740*t)+.016*rng.uniform(-1,1,count))*np.exp(-42*t)
                )
    fade = min(total//2,round(.6*RATE))
    if fade:
        signal[:fade] *= np.linspace(0,1,fade)
        signal[-fade:] *= np.linspace(1,0,fade)
    with wave.open(str(target),'wb') as file:
        file.setparams((1,2,RATE,0,'NONE',''))
        file.writeframes((signal*32767).astype('<i2').tobytes())


def runtime_timing(lengths,bounds=None,*,word_count=None):
    if not lengths or any(not math.isfinite(length) or length<=0 for length in lengths):
        raise ValueError('Narration timings must be positive and finite')
    tempo = 1.0
    if bounds:
        total = sum(lengths)
        lower, upper = bounds
        pauses = len(lengths)*NARRATION_PAUSE
        estimate = total + pauses
        # Each shot rounds up to a whole frame. Allow headroom for every
        # rounding and the audio/video container duration.
        upper_target = upper - len(lengths)/FPS - 1
        if estimate < lower+1 or estimate > upper_target:
            target = lower+2 if estimate < lower+1 else upper_target
            tempo = total/(target-pauses)
        if not .85 <= tempo <= 1.15:
            # The synthesized pace varies by script. For larger corrections,
            # check the resulting spoken pace as well as the stretch ratio.
            adjusted_wpm = 60 * word_count * tempo / total if word_count else None
            if (not .65 <= tempo <= 1.5 or adjusted_wpm is None
                    or not NARRATION_WPM[0] <= adjusted_wpm <= NARRATION_WPM[1]):
                raise RuntimeError(
                    'Narration is outside the 15–25 minute range at a natural speaking speed '
                    f'(raw={total:.1f}s, words={word_count}, required_tempo={tempo:.3f}, '
                    f'adjusted_wpm={adjusted_wpm})')
    return tempo


def calibrate_narration_speed(speak,work,beats,bounds,measure):
    """Measure representative lines before committing to an episode-length TTS pass."""
    if not beats:
        raise ValueError('Cannot calibrate narration without spoken beats')
    words, measured = 0, 0
    for index in sorted({0,len(beats)//2,len(beats)-1}):
        text = beats[index]['narration']
        target = work/f'calibration-{index}.wav'
        speak(text,target,speed=DEFAULT_NARRATION_SPEED)
        seconds = measure(target)
        if not math.isfinite(seconds) or seconds<=0:
            raise RuntimeError(f'Invalid narration calibration audio at beat {index+1}')
        measured += seconds
        words += len(text.split())
    total_words = sum(len(beat['narration'].split()) for beat in beats)
    estimate = measured*total_words/words
    target = sum(bounds)/2-len(beats)*NARRATION_PAUSE
    speed = round(max(.68,min(1.20,DEFAULT_NARRATION_SPEED*estimate/target)),3)
    print(json.dumps({'stage':'Kokoro speed calibration','estimated_raw_seconds':round(estimate,2),
                      'native_speed':speed,'target_seconds':round(target,2)}),flush=True)
    return speed


def narration_filter(tempo, source_rate):
    """Shift pitch down while preserving the requested playback duration."""
    pitch = 2**(VOICE_PITCH_SEMITONES/12)
    shifted_rate = round(source_rate*pitch)
    compensation = tempo*source_rate/shifted_rate
    return f'asetrate={shifted_rate},aresample={RATE},atempo={compensation:.8f},apad'


def prepare_audio(plan, work, speak=None, *, minimum=0, runtime_bounds=None):
    from pipeline import duration

    work.mkdir(parents=True,exist_ok=True)
    native_voice = speak is None
    speak = speak or speech_writer()
    voice_speed = DEFAULT_NARRATION_SPEED
    if native_voice and runtime_bounds:
        beats = [beat for chapter in plan['chapters'] for beat in chapter['beats']]
        voice_speed = calibrate_narration_speed(speak,work,beats,runtime_bounds,duration)
    planned = []
    for chapter in plan['chapters']:
        for beat_index,beat in enumerate(chapter['beats']):
            index = len(planned)
            raw = work/f'raw-{index}.wav'
            if native_voice:
                speak(beat['narration'],raw,speed=voice_speed)
            else:
                speak(beat['narration'],raw)
            planned.append((beat,raw,duration(raw),chapter['label'] if beat_index==0 else None))
    lengths = [entry[2] for entry in planned]
    word_count = sum(len(beat['narration'].split()) for beat, *_ in planned)
    tempo = runtime_timing(lengths,runtime_bounds,word_count=word_count)
    frame_counts = [max(math.ceil(minimum*FPS),math.ceil((length/tempo+NARRATION_PAUSE)*FPS))
                    for _,_,length,_ in planned]
    if runtime_bounds and not runtime_bounds[0] <= sum(frame_counts)/FPS <= runtime_bounds[1]:
        raise RuntimeError('Adjusted narration falls outside the 15–25 minute window')
    print(json.dumps({'stage':'narration timing','planned_seconds':round(sum(frame_counts)/FPS,2),
                      'tempo':round(tempo,4),'raw_seconds':round(sum(lengths),2),
                      'words':word_count,'spoken_wpm':round(60*word_count*tempo/sum(lengths),1),
                      'chapters':len(plan['chapters'])}),flush=True)
    for index,((_,raw,_,_),frames) in enumerate(zip(planned,frame_counts)):
        with wave.open(str(raw),'rb') as voice:
            audio_filter = narration_filter(tempo,voice.getframerate())
        ffmpeg('-i',raw,'-af',audio_filter,'-ar',RATE,'-ac',1,'-t',f'{frames/FPS:.6f}',work/f'a-{index}.wav')
        raw.unlink()
    write_json(work/'timing.json',{'plan_sha256':plan_digest(plan),'frames':frame_counts})


def plan_digest(plan):
    return hashlib.sha256(json.dumps(plan,sort_keys=True).encode()).hexdigest()


def timed_shots(plan,work):
    timing = json.loads((work/'timing.json').read_text())
    frame_counts = timing['frames']
    beats = [(chapter_index,beat,chapter['label'] if index==0 else None)
             for chapter_index,chapter in enumerate(plan['chapters'])
             for index,beat in enumerate(chapter['beats'])]
    if (timing['plan_sha256'] != plan_digest(plan) or len(frame_counts) != len(beats)
            or any(type(frames) is not int or frames <= 0 for frames in frame_counts)):
        raise ValueError('Prehistory narration timings do not match the saved plan')
    return [(index,chapter,beat,label,frames)
            for index,((chapter,beat,label),frames) in enumerate(zip(beats,frame_counts))]


def render_shots(plan,work,chapter=None):
    render_clip, render_cover = clip, cover
    if os.environ.get('PREHISTORY_BLENDER'):
        from .storybook import clip as render_clip, cover as render_cover
    if chapter is not None and not 0 <= chapter < len(plan['chapters']):
        raise ValueError('Unknown prehistory chapter')
    if chapter is None or chapter == 0:
        render_cover(plan,work/'thumbnail.jpg')
    for index,chapter_index,beat,label,frames in timed_shots(plan,work):
        if chapter is None or chapter_index == chapter:
            print(json.dumps({'stage':'render shot','shot':index+1,'frames':frames}),flush=True)
            render_clip(beat,index,frames,work/f'v-{index}.mp4',label if index else None)


def assemble(plan,root,work,*,runtime_bounds=None):
    import shutil
    from pipeline import duration

    inputs = {'video':[],'audio':[]}
    sound_beats = []
    starts, total_frames = [], 0
    for index,_,beat,label,frames in timed_shots(plan,work):
        if label is not None:
            starts.append(total_frames/FPS)
        for kind,prefix,suffix in (('video','v','mp4'),('audio','a','wav')):
            path = work/f'{prefix}-{index}.{suffix}'
            if not path.is_file():
                raise ValueError(f'Missing {kind} for prehistory shot {index+1}')
            inputs[kind].append(path.name)
        sound_beats.append((total_frames/FPS,frames/FPS,beat))
        total_frames += frames
    shutil.copyfile(work/'thumbnail.jpg',root/'thumbnail.jpg')
    for kind,paths in inputs.items():
        (work/f'{kind}.txt').write_text(''.join(f"file '{path}'\n" for path in paths))
    score = work/'score.wav'
    soundtrack(score,total_frames/FPS,sound_beats)
    ffmpeg('-f','concat','-safe',0,'-i',work/'video.txt','-f','concat','-safe',0,'-i',work/'audio.txt',
           '-i',score,
           '-filter_complex','[1:a]loudnorm=I=-16:TP=-2:LRA=8,aresample=48000[voice];'
           '[2:a]aresample=48000[bed];[voice][bed]amix=inputs=2:duration=first:normalize=0,'
           f'volume={MASTER_GAIN},alimiter=limit=0.89:level=0:latency=1[a]',
           '-map','0:v','-map','[a]','-c:v','copy','-c:a','aac','-b:a','160k',
           '-metadata:s:a:0','language=eng','-movflags','+faststart','-shortest',root/'video.mp4')
    actual = duration(root/'video.mp4')
    if runtime_bounds and not runtime_bounds[0] <= actual <= runtime_bounds[1]:
        raise RuntimeError('Finished documentary must run between 15 and 25 minutes')
    if abs(actual-total_frames/FPS)>.15:
        raise RuntimeError('Rendered video differs from the measured storyboard')
    write_json(root/'song.json',metadata(plan,starts))
    if (root/'prehistory-plan.json').exists():
        write_json(root/'prehistory-render.json',{
            name:asset_digest(root/name) for name in ('prehistory-plan.json','video.mp4','thumbnail.jpg','song.json')
        })


def render(plan,root,speak=None,*,minimum=0,runtime_bounds=None):
    with tempfile.TemporaryDirectory(dir=root) as directory:
        work = Path(directory)
        prepare_audio(plan,work,speak,minimum=minimum,runtime_bounds=runtime_bounds)
        render_shots(plan,work)
        assemble(plan,root,work,runtime_bounds=runtime_bounds)


def asset_digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def verify_render(root):
    receipt = json.loads((root/'prehistory-render.json').read_text())
    expected = ('prehistory-plan.json','video.mp4','thumbnail.jpg','song.json')
    if set(receipt)!=set(expected) or any(asset_digest(root/name)!=receipt[name] for name in expected):
        raise RuntimeError('Finished prehistory video and original plan do not match')


def make_plan(run_id,root):
    store = Store()
    key = f'runs/{run_id}/prehistory-plan.json'
    plan = store.load(key,None)
    if plan is None:
        draft_key = f'runs/{run_id}/prehistory-draft.json'
        plan = generate(run_id,store.load('history.json',[]),store.load(draft_key,None),
                        lambda draft: store.save(draft_key,draft))
        store.save(key,plan)
    write_json(root/'prehistory-plan.json',plan)


def publish_episode(run_id,root):
    from pipeline import publish,youtube_client
    verify_render(root)
    store = Store()
    client = youtube_client()
    key = f'runs/{run_id}/state.json'
    state = store.load(key,{})
    song = json.loads((root/'song.json').read_text())
    plan = json.loads((root/'prehistory-plan.json').read_text())
    if song['genre'] != 'prehistory' or song['title'] not in (plan['title'],ancient_humans_title(plan['title'])):
        raise ValueError('Publication metadata differs from the prehistory storyboard')
    branded_title = ancient_humans_title(song['title'])
    if not state or state.get('song',{}).get('title') == branded_title:
        song['title'] = branded_title
    digest = hashlib.sha256(json.dumps(plan['chapters'],sort_keys=True).encode()).hexdigest()
    history = store.load('history.json',[])
    if any(row.get('run') != run_id and (row.get('hash') == digest or row.get('title') == song['title'])
           for row in history):
        raise RuntimeError('Prehistory episode has already been published')
    if state and (state.get('hash') != digest or state.get('song') != song):
        raise RuntimeError('Publication checkpoint belongs to a different episode')
    def save():
        store.save(key,state)
    if not state:
        state.update(song=song,hash=digest)
        save()
    if not state.get('video_id'):
        if state.get('upload_started'):
            raise RuntimeError('Ambiguous upload; reconcile YouTube before retry to avoid duplicates')
        for name in ('video.mp4','thumbnail.jpg'):
            store.upload(root/name,f'runs/{run_id}/{name}')
    if state.get('phase') != 'published':
        publish(client,root,song,state,save)
    if not any(row.get('run') == run_id for row in history):
        history.append({'run':run_id,'title':song['title'],'hash':digest,'video_id':state['video_id'],
                        'prehistory_topic':plan['topic']})
        store.save('history.json',history)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=('plan','audio','chapter','assemble','render','publish'))
    parser.add_argument('--run-id',required=True)
    parser.add_argument('--chapter',type=int)
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',args.run_id):
        parser.error('Invalid run ID')
    root = Path('output')/args.run_id
    root.mkdir(parents=True,exist_ok=True)
    if args.stage == 'plan':
        make_plan(args.run_id,root)
    elif args.stage == 'publish':
        publish_episode(args.run_id,root)
    else:
        plan = json.loads((root/'prehistory-plan.json').read_text())
        work = root/'render-parts'
        if args.stage == 'audio':
            prepare_audio(plan,work,runtime_bounds=FULL_RUNTIME)
        elif args.stage == 'chapter':
            if args.chapter is None:
                parser.error('--chapter is required for the chapter stage')
            render_shots(plan,work,args.chapter)
        elif args.stage == 'assemble':
            assemble(plan,root,work,runtime_bounds=FULL_RUNTIME)
        else:
            render(plan,root,runtime_bounds=FULL_RUNTIME)


if __name__ == '__main__':
    main()
