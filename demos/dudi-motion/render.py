"""Review-only CPU puppet motion derived from an actual Dudi Dam TV scene."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
from PIL import Image, ImageDraw, ImageFilter, ImageOps

FPS, SECONDS = 25, 15
W,H=1280,720


def animate(asset,t):
    """Bend ears and tail independently using a continuous inverse image mesh."""
    width,height=asset.size
    def point(x,y):
        u,v=x/width,y/height
        ear=max(0,(.43-v)/.43)**1.6
        tail=max(0,min(1,(u-.7)/.18))*math.exp(-((v-.72)/.19)**4)
        dx=width*.027*math.sin(t*4.5+(0 if u<.45 else 1.3))*ear
        dy=height*.014*math.sin(t*7)*tail
        return x+dx,y+dy
    mesh=[]
    for y in range(0,height,32):
        for x in range(0,width,32):
            right,bottom=min(width,x+32),min(height,y+32)
            quad=[point(x,y),point(x,bottom),point(right,bottom),point(right,y)]
            mesh.append(((x,y,right,bottom),tuple(c for p in quad for c in p)))
    return asset.transform(asset.size,Image.Transform.MESH,mesh,Image.Resampling.BICUBIC)


def render(output,audio):
    output.mkdir(parents=True,exist_ok=True)
    assets=Path(__file__).parent/'assets'
    bg=ImageOps.fit(Image.open(assets/'garden-plate.png').convert('RGB'),(W,H))
    rabbit=Image.open(assets/'rabbit.png').convert('RGBA')
    if rabbit.getextrema()[3][0] != 0:
        raise RuntimeError('Rabbit must have true alpha transparency')
    rabbit=rabbit.crop(rabbit.getbbox())
    rabbit.thumbnail((650,580),Image.Resampling.LANCZOS)
    path=output/'dudi-dam-rabbit-motion.mp4'
    args=['ffmpeg','-y','-v','error','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}',
          '-r',str(FPS),'-i','pipe:0','-i',str(audio),'-map','0:v','-map','1:a',
          '-af','afade=t=in:d=0.3,afade=t=out:st=14:d=1','-t',str(SECONDS),
          '-c:v','libx264','-preset','fast','-crf','19','-pix_fmt','yuv420p','-c:a','aac',
          '-b:a','192k','-movflags','+faststart',str(path)]
    proc=subprocess.Popen(args,stdin=subprocess.PIPE)
    try:
        for frame in range(FPS*SECONDS):
            t=frame/FPS
            canvas=bg.copy().convert('RGBA')
            # Smooth hop arcs and a modest lateral dance; feet are anchored while resting.
            cycle=t%3.6
            lift=math.sin(math.pi*(cycle-1.1)/1.25)*90 if 1.1<cycle<2.35 else 0
            lift=max(0,lift)
            landing=math.exp(-((cycle-2.45)/.13)**2)
            stretch=1+.018*math.sin(t*2.8)+.07*(lift/90)-.065*landing
            body=animate(rabbit,t)
            body=body.resize((round(body.width/(stretch**.4)),round(body.height*stretch)),Image.Resampling.LANCZOS)
            angle=math.sin(t*2)*1.1+math.sin(t*3.4)*lift/90*2
            body=body.rotate(angle,Image.Resampling.BICUBIC,expand=True)
            cx=660+math.sin(t*.9)*48
            floor=655
            shadow=Image.new('RGBA',(W,H))
            d=ImageDraw.Draw(shadow)
            radius=140-lift*.4
            d.ellipse((cx-radius,floor-20,cx+radius,floor+10),fill=(30,38,38,round(70-lift*.35)))
            canvas=Image.alpha_composite(canvas,shadow.filter(ImageFilter.GaussianBlur(12)))
            canvas.alpha_composite(body,(round(cx-body.width/2),round(floor-body.height-lift)))
            # Slow camera drift is separate from the character animation.
            scale=1.015+.007*math.sin(t*.6)
            view=canvas.resize((round(W*scale),round(H*scale)),Image.Resampling.LANCZOS)
            left=(view.width-W)//2
            top=(view.height-H)//2
            view=view.crop((left,top,left+W,top+H)).convert('RGB')
            if frame in (0,60,150,300):
                view.save(output/f'frame-{frame:03}.jpg',quality=93)
            proc.stdin.write(view.tobytes())
    finally:
        proc.stdin.close()
    if proc.wait():
        raise RuntimeError('Video render failed')
    info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)]))
    assert abs(float(info['format']['duration'])-SECONDS)<.1
    assert any(s['codec_type']=='audio' for s in info['streams'])
    subprocess.run(['ffmpeg','-v','error','-xerror','-i',str(path),'-f','null','-'],check=True)
    manifest={'passed':True,'seconds':SECONDS,'frames':FPS*SECONDS,'resolution':[W,H],
              'original_scene_run':41254581826,'original_scene':'scene-000-source.png',
              'method':'CPU layered puppet animation; AI-extracted rabbit and cleaned original background',
              'motion':['ear bending','tail movement','breathing','hops','landing squash','camera drift'],
              'assets':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in assets.glob('*.png')}}
    (output/'validation.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps(manifest),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--audio-dir',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=Path('output/dudi-motion-demo'))
    args=parser.parse_args()
    candidates=sorted(args.audio_dir.rglob('*.wav'))
    if not candidates:
        raise RuntimeError('Original rhyme audio is required')
    render(args.output,candidates[0])
