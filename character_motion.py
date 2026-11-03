"""Automatic CPU character cutouts, clean plates and layered storybook motion.

No image API or inference credits. BiRefNet isolates the foreground, LaMa fills
its original location, and Pillow animates the extracted original artwork.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess

import numpy as np
from PIL import Image, ImageFilter, ImageOps

VERSION = 'dudi-layered-characters-v11-tempo-aware-dance'
FPS, SECONDS = 25, 5
_SESSION = None
_LAMA = None
LAMA_URL = 'https://github.com/enesmsahin/simple-lama-inpainting/releases/download/v0.1.0/big-lama.pt'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic_json(path, data):
    temp=path.with_suffix('.tmp.json')
    temp.write_text(json.dumps(data,indent=2))
    temp.replace(path)


class InvalidForegroundMask(ValueError):
    """Segmentation did not find a safe character silhouette."""


def mask_for(image):
    global _SESSION
    from rembg import new_session, remove
    if _SESSION is None:
        _SESSION=new_session('birefnet-general-lite',providers=['CPUExecutionProvider'])
    mask=remove(image,session=_SESSION,only_mask=True).convert('L')
    mask=mask.point(lambda value:0 if value<12 else value)
    # Animate the main character/group, not unrelated distant butterflies or stars.
    # Preserve substantial companions and their antialiased edges too.
    from scipy import ndimage
    labels,count=ndimage.label(np.asarray(mask)>64)
    if count:
        areas=np.bincount(labels.ravel())
        areas[0]=0
        principal=ndimage.binary_dilation(np.isin(labels,np.flatnonzero(areas >= max(areas.max()*.03,mask.width*mask.height*.0008))),iterations=3)
        mask=Image.fromarray(np.where(principal,np.asarray(mask),0).astype('uint8'))
    # Reject implausible extraction instead of publishing a moving rectangle.
    coverage=float((np.asarray(mask)>128).mean())
    if not .025 <= coverage <= .72:
        raise InvalidForegroundMask(f'Character extraction needs review: foreground coverage {coverage:.3f}')
    return mask


def clean_plate(image,mask):
    global _LAMA
    import torch
    import torch.nn.functional as functional
    torch.set_num_threads(min(os.cpu_count() or 2,4))
    if _LAMA is None:
        model=Path.home()/'.cache/torch/hub/checkpoints/dudi-big-lama-v0.1.0.pt'
        model.parent.mkdir(parents=True,exist_ok=True)
        if not model.exists():
            temp=model.with_suffix('.download')
            torch.hub.download_url_to_file(LAMA_URL,str(temp))
            temp.replace(model)
        _LAMA=torch.jit.load(str(model),map_location='cpu').eval()
    small=ImageOps.contain(image,(768,768))
    # A dilated binary mask removes antialiased character edges and old shadows.
    hole=mask.point(lambda p:255 if p>24 else 0).filter(ImageFilter.MaxFilter(17))
    lowmask=hole.resize(small.size,Image.Resampling.NEAREST)
    pixels=torch.from_numpy(np.asarray(small).copy()).permute(2,0,1).float()[None]/255
    holes=torch.from_numpy(np.asarray(lowmask).copy()).float()[None,None]/255
    height,width=small.height,small.width
    padding=(0,(-width)%8,0,(-height)%8)
    pixels=functional.pad(pixels,padding,mode='reflect')
    holes=functional.pad(holes,padding,mode='reflect')
    with torch.inference_mode():
        result=_LAMA(pixels,holes)[0,:,:height,:width]
    filled=Image.fromarray((result.permute(1,2,0).clamp(0,1).numpy()*255).astype('uint8'))
    filled=filled.resize(image.size,Image.Resampling.LANCZOS)
    return Image.composite(filled,image,hole.filter(ImageFilter.GaussianBlur(2)))


def prepare_layers(source,folder,extract=mask_for,inpaint=clean_plate):
    folder.mkdir(parents=True,exist_ok=True)
    identity={'version':VERSION,'source_sha256':digest(source),'mask_model':'birefnet-general-lite','inpaint':'big-lama-v0.1.0'}
    record=folder/'layers.json'
    if record.exists():
        try:
            saved=json.loads(record.read_text())
        except (OSError,ValueError):
            saved={}
        if saved.get('identity')==identity and all((folder/name).is_file() and digest(folder/name)==sha
                for name,sha in saved.get('assets',{}).items()) and len(saved.get('assets',{}))==2:
            return saved
    image=Image.open(source).convert('RGB')
    mask=extract(image).convert('L')
    if mask.size != image.size:
        raise ValueError('Character mask dimensions must match the scene')
    coverage=float((np.asarray(mask)>128).mean())
    if not .025 <= coverage <= .72:
        raise InvalidForegroundMask('Invalid foreground mask; scene needs review')
    foreground=image.convert('RGBA')
    foreground.putalpha(mask)
    foreground.save(folder/'foreground.png')
    background=inpaint(image,mask).convert('RGB')
    if background.size != image.size:
        raise ValueError('Inpainting changed the scene dimensions')
    background.save(folder/'background.png')
    result={'identity':identity,'foreground_fraction':round(coverage,4),
            'assets':{name:digest(folder/name) for name in ('foreground.png','background.png')}}
    atomic_json(record,result)
    return result


def deform(asset,t,index,rabbit=False):
    width,height=asset.size
    mesh=[]
    def point(x,y):
        u,v=x/width,y/height
        # Ear bending is used only for rabbit/hare scenes; other silhouettes
        # retain their face and head shape. Breathing/hops work for all subjects.
        ear=max(0,(.36-v)/.36)**1.6 if rabbit else 0
        tail=max(0,min(1,(u-.75)/.2))*math.exp(-((v-.72)/.18)**4) if rabbit else 0
        return (x+width*.018*math.sin(t*4.5+index+u*2)*ear,
                y+height*.009*math.sin(t*6+index)*tail)
    for y in range(0,height,40):
        for x in range(0,width,40):
            right,bottom=min(width,x+40),min(height,y+40)
            quad=[point(x,y),point(x,bottom),point(right,bottom),point(right,y)]
            mesh.append(((x,y,right,bottom),tuple(c for p in quad for c in p)))
    return asset.transform(asset.size,Image.Transform.MESH,mesh,Image.Resampling.BICUBIC)


def clip_identity(source,width,height,index,prompt):
    return dict(version=VERSION,source=digest(source),width=width,height=height,index=index,
                prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),fps=FPS,seconds=SECONDS)


def cached_clip(source,target,width,height,index,prompt):
    record=target.with_suffix('.json')
    try:
        saved=json.loads(record.read_text())
        return (target.is_file() and saved.get('identity')==clip_identity(source,width,height,index,prompt)
                and saved.get('video_sha256')==digest(target))
    except (OSError,ValueError):
        return False


def render_clip(source,target,width=1920,height=1080,index=0,prompt=''):
    folder=source.parent/'characters'/source.stem
    try:
        layers=prepare_layers(source,folder)
    except InvalidForegroundMask as error:
        # Some valid wide shots contain tiny characters. Preserve their artwork
        # and use camera motion rather than inventing a cutout or losing a shard.
        return render_camera_clip(source,target,width,height,index,prompt,str(error))
    bg=Image.open(folder/'background.png').convert('RGBA')
    fg=Image.open(folder/'foreground.png').convert('RGBA')
    bbox=fg.getbbox()
    if bbox is None:
        raise ValueError('No foreground character')
    subject=fg.crop(bbox)
    # Compose at native generation resolution, then upscale once in FFmpeg.
    # This bounds CPU work and preserves the same 1080p output as production.
    native=bg.size
    from scene_actions import plan_scene, actor_parts, compose_scene, actor_profile
    plan=plan_scene(prompt,index)
    parts=actor_parts(fg,split_touching=plan['kind']=='dance')
    rig=parts[0][2] if len(parts)==1 else None
    target.parent.mkdir(parents=True,exist_ok=True)
    temp=target.with_suffix('.tmp.mp4')
    args=['ffmpeg','-y','-v','error','-f','rawvideo','-pix_fmt','rgb24','-s',f'{native[0]}x{native[1]}',
          '-r',str(FPS),'-i','pipe:0','-vf',f'scale={width}:{height}:flags=lanczos,setsar=1',
          '-an','-frames:v',str(FPS*SECONDS),'-c:v','libx264','-threads','4','-preset','fast','-crf','20',
          '-pix_fmt','yuv420p','-movflags','+faststart',str(temp)]
    proc=subprocess.Popen(args,stdin=subprocess.PIPE)
    try:
        for frame in range(FPS*SECONDS):
            t=frame/FPS
            canvas=compose_scene(bg,parts,plan,t)
            proc.stdin.write(canvas.convert('RGB').tobytes())
    finally:
        proc.stdin.close()
    if proc.wait():
        temp.unlink(missing_ok=True)
        raise RuntimeError('Character-motion encoding failed')
    verify_clip(temp,width,height)
    temp.replace(target)
    atomic_json(target.with_suffix('.json'),{'identity':clip_identity(source,width,height,index,prompt),
        'video_sha256':digest(target),'layers':layers,'passed':True,
        'story_plan':plan,'camera_motion':'continuous-safe-zoom-pan','background_motion':'sky-parallax-foliage-sway',
        'actor_profiles':[actor_profile(plan,i,len(parts)) for i in range(len(parts))],
        'story_plan_version':plan['version'],'actor_count':len(parts),'face_rigs':[part[2] for part in parts],
        'facial_motion':any(part[2] for part in parts),
        'body_motion':'gentle-local-arms-legs-waist' if plan['action']=='dance' else None,
        'facial_note':'2D blink, head turn and cheek lift' if rig else 'No confident single face; original face preserved'})
    return target


def render_camera_clip(source,target,width,height,index,prompt,reason):
    target.parent.mkdir(parents=True,exist_ok=True)
    temp=target.with_suffix('.tmp.mp4')
    print(json.dumps({'warning':'character_extraction_fallback','source':str(source),
                      'reason':reason,'motion_mode':'camera'}),flush=True)
    # Render every frame at output resolution with a small centered push-in.
    filters=(f"scale={width}:{height}:force_original_aspect_ratio=increase,"
             f"crop={width}:{height},"
             f"zoompan=z='1+0.04*on/{FPS*SECONDS-1}':"
             f"x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d={FPS*SECONDS}:"
             f"s={width}x{height}:fps={FPS},setsar=1")
    try:
        subprocess.run(['ffmpeg','-y','-v','error','-i',str(source),'-vf',filters,
                        '-an','-frames:v',str(FPS*SECONDS),'-c:v','libx264','-threads','4',
                        '-preset','fast','-crf','20','-pix_fmt','yuv420p',
                        '-movflags','+faststart',str(temp)],check=True)
        verify_clip(temp,width,height)
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)
    atomic_json(target.with_suffix('.json'),{
        'identity':clip_identity(source,width,height,index,prompt),
        'video_sha256':digest(target),'motion_mode':'camera',
        'fallback_reason':reason,'passed':True})
    return target


def verify_clip(path,width,height):
    info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)]))
    video=next(s for s in info['streams'] if s['codec_type']=='video')
    if (video['width'],video['height'])!=(width,height) or abs(float(info['format']['duration'])-SECONDS)>.05:
        raise ValueError('Character clip dimensions or duration invalid')
    subprocess.run(['ffmpeg','-v','error','-xerror','-i',str(path),'-f','null','-'],check=True)


def prepare_shard(root):
    song=json.loads((root/'song.json').read_text())
    portrait=os.getenv('IMAGE_VARIANT')=='portrait'
    artwork=root/'portrait' if portrait else root
    shard,count=int(os.getenv('IMAGE_SHARD','0')),int(os.getenv('IMAGE_SHARDS','1'))
    if count<1 or not 0<=shard<count:
        raise ValueError('Invalid character motion shard')
    from song_images import image_plan
    from scene_actions import motion_prompt
    entries=[p for i,p in enumerate(image_plan(song)) if i%count==shard and p['kind'].startswith('scene-')]
    width,height=(1080,1920) if portrait else (1920,1080)
    for plan in entries:
        index=int(plan['kind'].split('-')[1])
        source=artwork/f"{plan['kind']}-source.png"
        target=artwork/'motion'/f'clip-{index:03d}.mp4'
        prompt=motion_prompt(song['scenes'][index])
        if not cached_clip(source,target,width,height,index,prompt):
            render_clip(source,target,width,height,index,prompt)
        print(json.dumps({'character_motion':True,'scene':index,'shard':shard}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',required=True,type=Path)
    prepare_shard(parser.parse_args().root)
