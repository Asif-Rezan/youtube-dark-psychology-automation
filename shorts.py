"""Turn a finished rhyme into a vertical Short using portrait illustrations and independently synthesized short music."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

VERSION = 'dudi-shorts-v4-layered-characters'


def atomic_json(path, value):
    temporary = path.with_suffix('.tmp.json')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False))
    temporary.replace(path)


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def probe(path):
    return json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams',
        '-show_format', '-of', 'json', str(path)], text=True))


def validate_clip(start, seconds):
    # Whole lyric/refrain pairs are ten seconds; avoid cutting a sung line.
    if type(start) is not int or start < 0 or start % 10:
        raise ValueError('Short start must be a nonnegative multiple of ten seconds')
    if type(seconds) is not int or seconds not in (20, 30, 40, 50):
        raise ValueError('Short duration must be 20, 30, 40 or 50 seconds')


def verify_video(path, seconds, vertical=False):
    info = probe(path)
    streams = info.get('streams', [])
    video = next((s for s in streams if s['codec_type'] == 'video'), None)
    audio = next((s for s in streams if s['codec_type'] == 'audio'), None)
    if not video or not audio:
        raise ValueError('Video must contain both picture and audio')
    if abs(float(info['format']['duration']) - seconds) > .25:
        raise ValueError('Short duration does not match the requested clip')
    if vertical and (video['width'], video['height']) != (1080, 1920):
        raise ValueError('Short must be 1080x1920')
    if vertical and video.get('sample_aspect_ratio') not in (None, '1:1'):
        raise ValueError('Short must use square pixels')
    # A valid container alone does not prove the clip decodes to completion.
    subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-i', str(path),
        '-map', '0:v:0', '-map', '0:a:0', '-f', 'null', '-'], check=True, capture_output=True)


def render_short(source_root, target, start=0, seconds=40):
    validate_clip(start, seconds)
    source = source_root / 'short-audio' / f'clip-{start}-{seconds}' / 'song.wav'
    info = probe(source)
    if abs(seconds - float(info['format']['duration'])) > .1:
        raise ValueError('Independent Short music duration mismatch')
    if not any(s['codec_type'] == 'audio' for s in info.get('streams', [])):
        raise ValueError('Source video has no audio')
    from PIL import Image
    portrait = source_root / 'portrait'
    song=json.loads((source_root/'song.json').read_text())
    scenes=song['scenes'][start//5:(start+seconds)//5]
    if [s['index'] for s in scenes] != list(range(start//5,(start+seconds)//5)):
        raise ValueError('Short storyboard does not cover the clip')
    images = {}
    for scene in scenes:
        path = portrait / f"scene-{scene['index']:03d}-source.png"
        with Image.open(path) as im:
            if im.width * 16 != im.height * 9:
                raise ValueError('Short illustration must have native 9:16 dimensions')
            im.verify()
        images[path.name] = digest(path)
    from character_motion import VERSION as character_version
    plan = dict(version=VERSION, character_version=character_version, portrait_images=images, source_sha256=digest(source), start=start, seconds=seconds,
                width=1080, height=1920)
    target.mkdir(parents=True, exist_ok=True)
    manifest = target / 'render.json'
    output = target / 'video.mp4'
    if manifest.exists() and output.exists():
        try:
            saved = json.loads(manifest.read_text())
        except (OSError, ValueError):
            saved = {}
        if saved.get('plan') == plan and saved.get('output_sha256') == digest(output):
            verify_video(output, seconds, vertical=True)
            return plan
    temporary = target / 'video.tmp.mp4'
    from motion_video import render_scenes
    listing = render_scenes(portrait, scenes, width=1080, height=1920)
    try:
        subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'concat', '-safe', '1',
            '-i', str(listing), '-i', str(source),
            '-t', str(seconds), '-map', '0:v:0', '-map', '1:a:0',
            '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k',
            '-af', f'afade=t=in:d=0.1,afade=t=out:st={seconds-.25}:d=0.25',
            '-movflags', '+faststart', str(temporary)], check=True, capture_output=True)
        verify_video(temporary, seconds, vertical=True)
        temporary.replace(output)
        atomic_json(manifest, dict(plan=plan, output_sha256=digest(output)))
    finally:
        temporary.unlink(missing_ok=True)
    return plan


def short_metadata(song, start, seconds):
    # Previous story-based Shorts packaging; retained for easy restoration:
    #     return dict(title=song['title'][:90].rstrip() + ' #Shorts',
    #         description=f"{seconds} seconds of {song['title']}! Sing and dance with Dudi Dam TV.\n#Shorts",
    #         tags=list(dict.fromkeys(song.get('tags', []) + ['Shorts', 'kids rhymes'])),
    #         source_title=song['title'], clip_start=start, clip_seconds=seconds)
    from upload_metadata import fixed_metadata
    return dict(fixed_metadata('shorts'), source_title=song['title'],
                clip_start=start, clip_seconds=seconds)


def run(run_id, start=0, seconds=40, publish=False):
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', run_id):
        raise ValueError('Invalid source run ID')
    validate_clip(start, seconds)
    source = Path('output') / run_id
    target = Path('output/shorts') / run_id / f'music-portrait-clip-{start}-{seconds}'
    target.mkdir(parents=True, exist_ok=True)
    song = json.loads((source / 'song.json').read_text())
    metadata = short_metadata(song, start, seconds)
    plan = render_short(source, target, start, seconds)
    atomic_json(target / 'song.json', metadata)
    if not publish:
        print(json.dumps({'phase':'short rendered','path':str(target / 'video.mp4')}), flush=True)
        return
    from pipeline import publish as publish_video, youtube_client
    from storage import Store
    store = Store()
    client = youtube_client()
    # Stable source/clip identity is shared by automatic and manual workflows.
    # Keep this checkpoint outside runs/ so long-video cleanup cannot delete it.
    key = f'shorts/{run_id}/music-portrait-clip-{start}-{seconds}/state.json'
    state = store.load(key, {})
    if state and state.get('source_plan') != plan:
        raise ValueError('Short source changed; use a new source run ID')
    state.setdefault('source_plan', plan)
    def save():
        # Write locally first so Actions can preserve a checkpoint even on a
        # temporary Drive failure. Remote failure must stop before an upload.
        atomic_json(target / 'state.json', state)
        store.save(key, state)
    save()
    # Shorts use YouTube's video frames; do not call the long-video thumbnail API.
    publish_video(client, target, metadata, state, save, upload_thumbnail=False, metadata_kind='shorts')
    print(json.dumps({'phase':state['phase'],'short_url':
        'https://www.youtube.com/shorts/' + state['video_id']}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--start', type=int, default=0)
    parser.add_argument('--seconds', type=int, default=40)
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    run(args.run_id, args.start, args.seconds, args.publish)
