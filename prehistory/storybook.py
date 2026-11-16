"""Place the existing character rig inside Blender-rendered prehistoric sets."""
import json
import math
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from PIL import Image, ImageDraw

from .character_rig import character
from .editorial import TOPICS
from .visuals import STAGING, caption_font, save_cover

BLENDER_SCRIPT = Path(__file__).with_name('blender_scene.py')
BLENDER_FPS = 12
POSITIONS = {'left': -1.95, 'center': 0, 'right': 1.95}


def draw_actor(path, member, direction, elapsed, index):
    image = Image.new('RGBA',(384,448))
    action = member['action']
    # A watcher holds their pose. Work and walking have distinct, task-specific cycles.
    work = elapsed * (math.tau/.68) if action=='work' else elapsed*4 if action in ('gather','share') else None
    step_phase = elapsed*8 if action in ('walk','carry') and elapsed < 2.05 else None
    character(ImageDraw.Draw(image),192,424,female=member['sex']=='female',
              facing=direction,islamic=False,scale=1.48,variant=index,
              walk_phase=step_phase,
              basket=action=='carry',work=work,point=action in ('show','react'),
              expression='surprised' if action=='react' else 'curious' if work is not None else 'calm',
              blink=elapsed%4 > 3.86,breathing=.55*math.sin(elapsed*2))
    image.save(path)


def build_shot(beat, index, count, work, *, cover=False):
    cast = beat.get('cast') or [{'sex':'female' if (index//3)%2 else 'male',
                                'action':beat.get('action','show'),'position':'left'}]
    lead = next((member for member in cast if member['action'] in ('work','gather','share')),cast[0])
    lead_x = POSITIONS[lead['position']]
    focus_x = lead_x + (-.57 if lead_x>0 else .57) if lead['action'] in ('work','gather','share') else 0
    actors = []
    for number, member in enumerate(cast):
        directory = work/f'actor-{number}'
        directory.mkdir()
        x = POSITIONS[member['position']]
        direction = 1 if x <= focus_x else -1
        for frame in range(1,count+1):
            draw_actor(directory/f'pose-{frame:04d}.png',member,direction,
                       .24 if cover else (frame-1)/BLENDER_FPS,number)
        actors.append({'name':f'{member["sex"].title()} · {member["action"]}',
                       'texture':str((directory/'pose-0001.png').resolve()),
                       'x':x,'y':number*.08,'height':2.45 if member['sex']=='male' else 2.32,
                       'direction':direction,'action':member['action']})
    return {'actors':actors,'focus':(focus_x,.26 if lead['action']=='work' else .48,1.1),'prop':beat['prop'],
            'action':lead['action'],'lead':cast.index(lead),'setting':beat.get('setting','workshop'),
            'framing':beat.get('framing','medium'),'index':index,'frames':count,
            'fps':BLENDER_FPS,'cover':cover}


def run_blender(shot, output):
    size = (1920,1080) if shot['cover'] else (768,432)
    settings = json.dumps(dict(shot,output=str(output.resolve()),size=size))
    log = output.parent/'blender.log'
    with log.open('w') as stream:
        try:
            subprocess.run(
                [os.environ['PREHISTORY_BLENDER'],'-b','-t','4','--python-exit-code','1',
                 '--python',str(BLENDER_SCRIPT)],
                env=dict(os.environ,PREHISTORY_SHOT=settings),stdout=stream,stderr=subprocess.STDOUT,
                check=True,timeout=240)
        except (subprocess.SubprocessError,OSError) as error:
            lines = log.read_text(errors='replace').splitlines()
            raise RuntimeError(f'Blender shot {shot["index"]+1} failed: '+ '\n'.join(lines[-8:])) from error


def clip(beat, index, frames, target, chapter_label=None):
    with TemporaryDirectory(prefix='storybook-',dir=target.parent) as temp:
        work = Path(temp)
        count = math.ceil(frames/2)
        shot = build_shot(beat,index,count,work)
        run_blender(shot,work/'shot-')
        # Keep the measured narration duration exactly, including odd 24 fps frame counts.
        command = ['ffmpeg','-v','error','-y','-f','rawvideo','-pix_fmt','rgb24',
                   '-s','768x432','-r','24','-i','pipe:0','-vf','scale=1920:1080:flags=lanczos',
                   '-c:v','libx264','-threads','4','-preset','veryfast','-pix_fmt','yuv420p',str(target)]
        with subprocess.Popen(command,stdin=subprocess.PIPE) as process:
            for index in range(frames):
                if index%2==0:
                    with Image.open(work/f'shot-{index//2+1:04d}.png') as source:
                        plate = source.convert('RGB')
                frame = plate
                if chapter_label and 6 <= index < 55:
                    frame = plate.copy()
                    draw = ImageDraw.Draw(frame)
                    face = caption_font(22)
                    label = chapter_label.upper()
                    while draw.textlength(label,font=face) > 630 and face.size > 14:
                        face = caption_font(face.size-1)
                    width = round(draw.textlength(label,font=face))
                    draw.rounded_rectangle((22,16,width+51,51),radius=9,fill='#29343c',outline='#efb66d',width=2)
                    draw.text((37,33),label,anchor='lm',font=face,fill='#fff6db')
                process.stdin.write(frame.tobytes())
            process.stdin.close()
            if process.wait():
                raise RuntimeError('Could not encode the Blender shot')


def cover(plan, target):
    kind = TOPICS[plan['topic']][3]
    _,_,left_action,_,_,right_action,_,_,_ = STAGING[kind]
    setting = {'stone':'workshop','fire':'camp','map':'journey','food':'grassland',
               'art':'cave','shelter':'camp'}[kind]
    beat = {'prop':kind,'setting':setting,'framing':'wide','cast':[
        {'sex':'male','action':left_action,'position':'left'},
        {'sex':'female','action':right_action,'position':'right'}]}
    with TemporaryDirectory(prefix='storybook-cover-',dir=target.parent) as temp:
        work = Path(temp)
        shot = build_shot(beat,0,1,work,cover=True)
        plate = work/'cover.png'
        run_blender(shot,plate)
        with Image.open(plate) as image:
            save_cover(image.convert('RGB'),plan['hook'],kind,target)
