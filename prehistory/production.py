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


def clip(beat,index,frames,target):
    command = ['ffmpeg','-y','-v','error','-f','rawvideo','-pix_fmt','rgb24',
               '-s',f'{SIZE[0]}x{SIZE[1]}','-r',str(FPS),'-i','pipe:0',
               '-vf','scale=1920:1080','-an','-c:v','libx264','-threads','4',
               '-preset','veryfast','-pix_fmt','yuv420p',str(target)]
    with subprocess.Popen(command,stdin=subprocess.PIPE) as process:
        try:
            for frame in range(frames):
                process.stdin.write(scene(beat,frame/FPS,frames/FPS,index).tobytes())
        finally:
            process.stdin.close()
        if process.wait():
            raise RuntimeError(f'Prehistory shot {index+1} failed to encode')


def render(plan,root,speak=None,*, minimum=0):
    from pipeline import duration
    speak = speak or speech_writer()
    cover(plan,root/'thumbnail.jpg')
    with tempfile.TemporaryDirectory(dir=root) as directory:
        work = Path(directory)
        inputs = {'video':[],'audio':[]}
        starts, total_frames = [], 0
        for chapter in plan['chapters']:
            starts.append(total_frames/FPS)
            for beat in chapter['beats']:
                index = len(inputs['video'])
                raw = work/f'raw-{index}.wav'
                speak(beat['narration'],raw)
                frames = max(math.ceil(minimum*FPS),math.ceil((duration(raw)+.33)*FPS))
                seconds = frames/FPS
                video, audio = work/f'v-{index}.mp4',work/f'a-{index}.wav'
                clip(beat,index,frames,video)
                ffmpeg('-i',raw,'-af','apad','-ar',RATE,'-ac',1,'-t',f'{seconds:.6f}',audio)
                inputs['video'].append(video.name)
                inputs['audio'].append(audio.name)
                total_frames += frames
        for kind,paths in inputs.items():
            (work/f'{kind}.txt').write_text(''.join(f"file '{path}'\n" for path in paths))
        ffmpeg('-f','concat','-safe',0,'-i',work/'video.txt','-f','concat','-safe',0,'-i',work/'audio.txt',
               '-f','lavfi','-i',"aevalsrc='0.052*(sin(2*PI*98*t)+0.38*sin(2*PI*147*t))*pow(sin(PI*t/5),2)':s=24000",
               '-filter_complex','[1:a]loudnorm=I=-16:TP=-2:LRA=8,aresample=48000[voice];'
               '[2:a]aresample=48000[bed];[voice][bed]amix=inputs=2:duration=first:normalize=0,'
               'alimiter=limit=0.90:level=0:latency=1[a]',
               '-map','0:v','-map','[a]','-c:v','copy','-c:a','aac','-b:a','160k',
               '-metadata:s:a:0','language=eng','-movflags','+faststart','-shortest',root/'video.mp4')
    if abs(duration(root/'video.mp4')-total_frames/FPS)>.15:
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
        plan = generate(run_id,store.load('history.json',[]))
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
        render(json.loads((root/'prehistory-plan.json').read_text()),root)
    else:
        publish_episode(args.run_id,root)


if __name__ == '__main__':
    main()
