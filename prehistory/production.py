"""Generate, render and publish a prehistoric documentary through existing services."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import tempfile
import wave

import numpy as np

from storage import Store
from .editorial import generate,metadata
from .visuals import SIZE,cover,scene

FPS = 24
RATE = 24000
FULL_RUNTIME = (900,1200)
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

    def speak(text,target):
        clips = [samples.numpy() for _,_,samples in engine(text,voice='am_michael',speed=.95) if samples is not None]
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


def runtime_timing(lengths,bounds=None):
    if not lengths or any(not math.isfinite(length) or length<=0 for length in lengths):
        raise ValueError('Narration timings must be positive and finite')
    tempo = 1.0
    if bounds:
        total = sum(lengths)
        lower, upper = bounds
        estimate = total+len(lengths)*.33
        if estimate < lower+1 or estimate > upper-1:
            target = lower+2 if estimate < lower+1 else upper-2
            tempo = total/(target-len(lengths)*.33)
        if not .85 <= tempo <= 1.15:
            raise RuntimeError('Narration is outside the 15–20 minute range at a natural speaking speed')
    return tempo


def narration_filter(tempo, source_rate):
    """Shift pitch down while preserving the requested playback duration."""
    pitch = 2**(VOICE_PITCH_SEMITONES/12)
    shifted_rate = round(source_rate*pitch)
    compensation = tempo*source_rate/shifted_rate
    return f'asetrate={shifted_rate},aresample={RATE},atempo={compensation:.8f},apad'


def render(plan,root,speak=None,*, minimum=0,runtime_bounds=None):
    from pipeline import duration
    speak = speak or speech_writer()
    cover(plan,root/'thumbnail.jpg')
    with tempfile.TemporaryDirectory(dir=root) as directory:
        work = Path(directory)
        inputs = {'video':[],'audio':[]}
        sound_beats = []
        starts, total_frames = [], 0
        planned = []
        for chapter in plan['chapters']:
            for beat_index,beat in enumerate(chapter['beats']):
                index = len(planned)
                raw = work/f'raw-{index}.wav'
                speak(beat['narration'],raw)
                planned.append((beat,raw,duration(raw),chapter['label'] if beat_index==0 else None))
        tempo = runtime_timing([entry[2] for entry in planned],runtime_bounds)
        frame_counts = [max(math.ceil(minimum*FPS),math.ceil((length/tempo+.33)*FPS))
                        for _,_,length,_ in planned]
        if runtime_bounds and not runtime_bounds[0] <= sum(frame_counts)/FPS <= runtime_bounds[1]:
            raise RuntimeError('Adjusted narration falls outside the 15–20 minute window')
        print(json.dumps({'stage':'narration timing','planned_seconds':round(sum(frame_counts)/FPS,2),
                          'tempo':round(tempo,4),'chapters':len(plan['chapters'])}),flush=True)
        for index,((beat,raw,_,label),frames) in enumerate(zip(planned,frame_counts)):
            if label is not None:
                starts.append(total_frames/FPS)
            seconds = frames/FPS
            video, audio = work/f'v-{index}.mp4',work/f'a-{index}.wav'
            clip(beat,index,frames,video,label if index else None)
            sound_beats.append((total_frames/FPS,seconds,beat))
            with wave.open(str(raw),'rb') as voice:
                audio_filter = narration_filter(tempo,voice.getframerate())
            ffmpeg('-i',raw,'-af',audio_filter,'-ar',RATE,'-ac',1,'-t',f'{seconds:.6f}',audio)
            inputs['video'].append(video.name)
            inputs['audio'].append(audio.name)
            total_frames += frames
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
        raise RuntimeError('Finished documentary must run between 15 and 20 minutes')
    if abs(actual-total_frames/FPS)>.15:
        raise RuntimeError('Rendered video differs from the measured storyboard')
    write_json(root/'song.json',metadata(plan,starts))
    if (root/'prehistory-plan.json').exists():
        write_json(root/'prehistory-render.json',{
            name:asset_digest(root/name) for name in ('prehistory-plan.json','video.mp4','thumbnail.jpg','song.json')
        })


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
    if song['genre'] != 'prehistory' or song['title'] != plan['title']:
        raise ValueError('Publication metadata differs from the prehistory storyboard')
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
    parser.add_argument('stage',choices=('plan','render','publish'))
    parser.add_argument('--run-id',required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',args.run_id):
        parser.error('Invalid run ID')
    root = Path('output')/args.run_id
    root.mkdir(parents=True,exist_ok=True)
    if args.stage == 'plan':
        make_plan(args.run_id,root)
    elif args.stage == 'render':
        render(json.loads((root/'prehistory-plan.json').read_text()),root,runtime_bounds=FULL_RUNTIME)
    else:
        publish_episode(args.run_id,root)


if __name__ == '__main__':
    main()
