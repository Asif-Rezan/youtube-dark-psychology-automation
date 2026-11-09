"""Render review-only landscape/portrait motion checks from saved episode layers."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
from PIL import Image,ImageOps,ImageDraw

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from scene_actions import actor_parts,compose_scene,plan_scene,actor_profile


def render(assets,output,baseline=None):
    output.mkdir(parents=True,exist_ok=True)
    root=next(assets.glob('*/characters'))
    configurations=[('landscape-cast','scene-112-source',(1024,576)),
                    ('portrait-cast','scene-112-source',(576,1024)),
                    ('landscape-single','scene-000-source',(1024,576))]
    report=[]
    clips=[]
    contact=Image.new('RGB',(960,540*len(configurations)),'white')
    previous=None
    if baseline:
        spec=importlib.util.spec_from_file_location('previous_motion',baseline)
        previous=importlib.util.module_from_spec(spec);spec.loader.exec_module(previous)
    for row,(name,scene,size) in enumerate(configurations):
        folder=root/scene
        bg=Image.open(folder/'background.png').convert('RGBA')
        fg=Image.open(folder/'foreground.png').convert('RGBA')
        if size!=bg.size:
            bg=ImageOps.fit(bg,size)
            subject=fg.crop(fg.getbbox())
            subject.thumbnail((round(size[0]*.80),round(size[1]*.65)),Image.Resampling.LANCZOS)
            fg=Image.new('RGBA',size)
            fg.alpha_composite(subject,((size[0]-subject.width)//2,round(size[1]*.86)-subject.height))
        parts=actor_parts(fg)
        if 'cast' in name and len(parts)<2:
            raise RuntimeError('Multi-character fixture did not preserve both actors')
        plan=plan_scene('children and animal friends discover a butterfly',row)
        frames=[]
        measurements={}
        for label,engine in [('updated',compose_scene)]+([('previous',previous.compose_scene)] if previous else []):
            started=time.perf_counter()
            for t in (.0,.5,1.5,2.5,3.5,4.96):engine(bg,parts,plan,t)
            measurements[label+'_frame_ms']=(time.perf_counter()-started)*1000/6
        target=output/f'{name}.mp4'
        args=['ffmpeg','-y','-v','error','-f','rawvideo','-pix_fmt','rgb24','-s',f'{size[0]}x{size[1]}',
              '-r','25','-i','pipe:0','-an','-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p','-movflags','+faststart',str(target)]
        proc=subprocess.Popen(args,stdin=subprocess.PIPE)
        started=time.perf_counter()
        for frame in range(125):
            im=compose_scene(bg,parts,plan,frame/25)
            proc.stdin.write(im.tobytes())
            if frame in (0,35,65,100,124):
                im.save(output/f'{name}-{frame:03d}.jpg')
            if frame in (0,124):frames.append(im.copy())
        proc.stdin.close()
        if proc.wait():raise RuntimeError('Motion encoding failed')
        elapsed=time.perf_counter()-started
        subprocess.run(['ffmpeg','-v','error','-xerror','-i',str(target),'-f','null','-'],check=True)
        info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(target)]))
        assert abs(float(info['format']['duration'])-5)<.05
        for column,im in enumerate(frames):
            im=ImageOps.contain(im,(480,500));contact.paste(im,(column*480,row*540+30))
            ImageDraw.Draw(contact).text((column*480+8,row*540+8),f'{name}: {"start" if column==0 else "end"}',fill='black')
        report.append(dict(scene=name,dimensions=size,actors=len(parts),profiles=[actor_profile(plan,i,len(parts)) for i in range(len(parts))],
                           render_seconds=round(elapsed,2),**measurements))
        # Review reel uses landscape framing with the portrait clip contained.
        reel=output/f'{name}-reel.mp4'
        subprocess.run(['ffmpeg','-y','-v','error','-i',str(target),'-vf','scale=960:540:force_original_aspect_ratio=decrease,pad=960:540:(ow-iw)/2:(oh-ih)/2:color=white',
            '-an','-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p',str(reel)],check=True)
        clips.append(reel)
    contact.save(output/'contact.jpg')
    listing=output/'clips.txt';listing.write_text(''.join(f"file '{p.name}'\n" for p in clips))
    subprocess.run(['ffmpeg','-y','-v','error','-f','concat','-safe','1','-i',str(listing),'-c','copy','-movflags','+faststart',str(output/'motion-review.mp4')],check=True)
    (output/'validation.json').write_text(json.dumps(dict(passed=True,source_run=41316394479,scenes=report),indent=2))
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--assets',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=Path('output/motion-improvements/review'))
    parser.add_argument('--baseline',type=Path)
    args=parser.parse_args()
    render(args.assets,args.output,args.baseline)
