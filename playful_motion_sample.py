"""Render a labeled animation sampler from verified existing character layers."""
import argparse
import json
from pathlib import Path
import subprocess
from PIL import Image, ImageDraw, ImageFont, ImageOps
from character_motion import digest
from scene_actions import actor_parts, compose_scene, plan_scene, VERSION

MOVES = [
    ('Tummy wiggle', 'tummy wiggle dance'),
    ('Jelly bounce', 'jelly bounce dance'),
    ('Clap + side step', 'clap hands dance'),
    ('Penguin walk', 'penguin walk dance'),
    ('Floating balloons', 'balloons dance'),
    ('Glowing fireflies', 'fireflies dance'),
    ('Ripple hops', 'ripple hop dance'),
    ('Floating bubbles', 'gentle dance'),
]


def verified_layers(root):
    candidates=[]
    for record in sorted(Path(root).rglob('layers.json')):
        saved=json.loads(record.read_text())
        folder=record.parent
        if set(saved.get('assets',{})) != {'foreground.png','background.png'}:
            continue
        if not all((folder/name).is_file() and digest(folder/name)==sha
                   for name,sha in saved['assets'].items()):
            continue
        source=folder.parent.parent/(folder.name+'.png')
        if not source.is_file() or digest(source)!=saved['identity']['source_sha256']:
            continue
        fg=Image.open(folder/'foreground.png').convert('RGBA')
        count=len(actor_parts(fg,split_touching=True))
        if count:
            candidates.append((min(count,3),saved.get('foreground_fraction',0),folder))
    if not candidates:
        raise ValueError('No verified source artwork and character layers available')
    return max(candidates,key=lambda item:item[:2])[2]


def render(root, output, audio=None):
    seconds=5*len(MOVES)
    folder=verified_layers(root)
    bg=Image.open(folder/'background.png').convert('RGBA')
    fg=Image.open(folder/'foreground.png').convert('RGBA')
    native=ImageOps.contain(bg,(768,432)).size
    # Even dimensions are required by yuv420p.
    native=tuple(max(2,n//2*2) for n in native)
    bg=bg.resize(native,Image.Resampling.LANCZOS)
    fg=fg.resize(native,Image.Resampling.LANCZOS)
    parts=actor_parts(fg,split_touching=True)
    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    silent=output.with_name(output.stem+'-silent.mp4')
    args=['ffmpeg','-y','-v','error','-f','rawvideo','-pix_fmt','rgb24',
          '-s',f'{native[0]}x{native[1]}','-r','25','-i','pipe:0',
          '-vf','scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2',
          '-an','-c:v','libx264','-threads','4','-preset','fast','-crf','19','-pix_fmt','yuv420p',str(silent)]
    fontpath=Path('assets/artwork/Oswald.ttf')
    font=ImageFont.truetype(str(fontpath),22)
    proc=subprocess.Popen(args,stdin=subprocess.PIPE)
    try:
        for index,(label,prompt) in enumerate(MOVES):
            plan=plan_scene(prompt+' 100 bpm',index)
            if label=='Floating bubbles':
                plan['dance_variant']='sway'
            for frame in range(125):
                image=compose_scene(bg,parts,plan,frame/25)
                draw=ImageDraw.Draw(image)
                draw.rectangle((0,0,native[0],42),fill=(30,40,65))
                draw.text((12,5),f'{index+1}/{len(MOVES)}  {label}',font=font,fill='white')
                proc.stdin.write(image.tobytes())
    finally:
        proc.stdin.close()
    if proc.wait():
        raise RuntimeError('Sampler encoding failed')
    args=['ffmpeg','-y','-v','error','-i',str(silent)]
    if audio:
        args+=['-stream_loop','-1','-i',str(audio),'-map','0:v:0','-map','1:a:0',
               '-c:a','aac','-af',f'volume=0.6,afade=t=in:d=0.5,afade=t=out:st={seconds-1}:d=1']
    args+=['-c:v','copy','-t',str(seconds),'-movflags','+faststart',str(output)]
    subprocess.run(args,check=True)
    silent.unlink()
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(output)]))
    video=next(s for s in probe['streams'] if s['codec_type']=='video')
    assert (video['width'],video['height'])==(1280,720)
    assert abs(float(probe['format']['duration'])-seconds)<.1
    report=dict(version=VERSION,source=str(folder),actor_count=len(parts),duration=seconds,
                output_sha256=digest(output),moves=MOVES)
    output.with_suffix('.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report),flush=True)
    return output


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=Path('output/playful-motion-sample.mp4'))
    parser.add_argument('--audio',type=Path)
    args=parser.parse_args()
    render(args.source,args.output,args.audio)
