"""Gentle layered storybook motion, rendered in bounded five-second clips."""
import hashlib
import json
from pathlib import Path
import subprocess
from PIL import Image

VERSION = 'storybook-scene-stories-v5-hd-thumbnail'
FPS = 25
SCENE_SECONDS = 5
TRANSITION = .28


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def render_identity(root):
    root = Path(root)
    song = json.loads((root/'song.json').read_text())
    sources = [root/'song.json',root/'song.wav',root/'thumbnail-source.png']
    sources += [root/f"scene-{s['index']:03d}-source.png" for s in song['scenes']]
    from character_motion import VERSION as character_version
    return dict(version=VERSION, character_version=character_version, fps=FPS, scene_seconds=SCENE_SECONDS,
        sources={p.name:digest(p) for p in sources})


def render_is_current(root):
    root=Path(root)
    if not (root/'video.mp4').is_file() or not (root/'render-state.json').is_file():
        return False
    try:
        return json.loads((root/'render-state.json').read_text()) == render_identity(root)
    except (OSError,ValueError,KeyError):
        return False


def run_ffmpeg(args):
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y',*args],check=True,capture_output=True)


def render_scenes(root, scenes, width=1920, height=1080):
    """Render sequentially to bound RAM; each clip covers exactly five seconds."""
    root=Path(root)
    work=root/'motion'
    work.mkdir(exist_ok=True)
    from character_motion import cached_clip, verify_clip
    from scene_actions import motion_prompt
    clips=[]
    for scene in scenes:
        index=scene['index']
        source=root/f'scene-{index:03d}-source.png'
        target=work/f'clip-{index:03d}.mp4'
        with Image.open(source) as image:
            image.verify()
        if not cached_clip(source,target,width,height,index,motion_prompt(scene)):
            raise RuntimeError(f'Scene {index} needs current character-motion clips; regenerate its image shard')
        verify_clip(target,width,height)
        clips.append(target)
    listing=work/'clips.txt'
    listing.write_text(''.join(f"file '{p.name}'\n" for p in clips))
    return listing


def render_animated(root, song):
    from pipeline import duration,validate_duration
    root=Path(root)
    identity=render_identity(root)
    listing=render_scenes(root,song['scenes'])
    from thumbnail_export import export_thumbnail
    export_thumbnail(root/'thumbnail-source.png',root/'thumbnail.jpg')
    temp=root/'video.tmp.mp4'
    run_ffmpeg(['-f','concat','-safe','1','-i',str(listing),'-i',str(root/'song.wav'),
        '-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','192k',
        '-t',str(song['duration']),'-movflags','+faststart',str(temp)])
    measured=duration(temp)
    validate_duration(measured)
    if abs(measured-song['duration'])>.1:
        raise ValueError('Animated video differs from storyboard duration')
    temp.replace(root/'video.mp4')
    checkpoint=root/'render-state.tmp'
    checkpoint.write_text(json.dumps(identity,indent=2))
    checkpoint.replace(root/'render-state.json')
