"""Center-crop an episode to a 1080x1350 Facebook feed canvas."""
import hashlib
import json
from pathlib import Path
import subprocess

VERSION='facebook-feed-4x5-crop-v1'


def digest(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def probe(path):
    return json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)]))


def verify(source,target):
    original,result=probe(source),probe(target)
    video=next(s for s in result['streams'] if s['codec_type']=='video')
    if (video['width'],video['height'])!=(1080,1350):raise ValueError('Facebook feed dimensions must be 1080x1350')
    if abs(float(original['format']['duration'])-float(result['format']['duration']))>.15:
        raise ValueError('Facebook feed duration differs from original')
    if any(s['codec_type']=='audio' for s in original['streams']) and not any(s['codec_type']=='audio' for s in result['streams']):
        raise ValueError('Facebook feed export lost audio')


def render(source,target):
    source,target=Path(source),Path(target)
    target.parent.mkdir(parents=True,exist_ok=True)
    receipt=target.with_suffix('.json')
    identity=dict(version=VERSION,source_sha256=digest(source))
    if receipt.exists() and target.exists():
        saved=json.loads(receipt.read_text())
        if saved.get('identity')==identity and saved.get('output_sha256')==digest(target):
            verify(source,target);return target
    temporary=target.with_suffix('.tmp.mp4')
    filters='scale=1080:1350:force_original_aspect_ratio=increase,crop=1080:1350,setsar=1'
    try:
        subprocess.run(['ffmpeg','-y','-v','error','-i',str(source),'-filter_complex_threads','2',
                        '-vf',filters,'-map','0:v:0','-map','0:a?',
                        '-c:v','libx264','-threads','4','-preset','fast','-crf','20',
                        '-pix_fmt','yuv420p','-c:a','copy','-movflags','+faststart',str(temporary)],check=True)
        verify(source,temporary)
        temporary.replace(target)
        receipt.write_text(json.dumps(dict(identity=identity,output_sha256=digest(target)),indent=2))
    finally:
        temporary.unlink(missing_ok=True)
    return target


def prepare(source,store,run_id):
    source=Path(source)
    target=source.parent/'facebook-feed'/'video.mp4'
    key=f'facebook/{run_id}/video/feed-4x5-crop.mp4'
    saved=store.find(key)
    if saved:
        target.parent.mkdir(parents=True,exist_ok=True)
        store.download(saved,target)
        verify(source,target)
    else:
        render(source,target)
        # Preserve exact upload bytes across new runners and encoder upgrades.
        store.upload(target,key)
    return target
