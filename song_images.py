"""Generate a distinct lyric scene for each five-second slot, with resumable cache."""
import hashlib
import json
import os
import random
from pathlib import Path
from PIL import Image
from image_cpu import MODEL, REVISION


THUMBNAIL_REFERENCE = Path(__file__).resolve().parent/'assets/thumbnail/kids-dance-reference.png'

THUMBNAIL_REFERENCES = (
    THUMBNAIL_REFERENCE,
    THUMBNAIL_REFERENCE.parent/'rose-garden.jpg',
    THUMBNAIL_REFERENCE.parent/'flower-dance.jpg',
    THUMBNAIL_REFERENCE.parent/'animal-costumes.jpg',
    THUMBNAIL_REFERENCE.parent/'rainbow-party.jpg',
)


def thumbnail_reference(identity=''):
    override = os.getenv('THUMBNAIL_REFERENCE_IMAGE')
    # Stable pseudo-random selection: shards and retries of the same generation agree.
    selection_seed = os.getenv('SONG_RUN_ID', '') + ':' + identity
    path = Path(override) if override else random.Random(selection_seed).choice(THUMBNAIL_REFERENCES)
    if not path.is_absolute():
        path = Path(__file__).resolve().parent/path
    strength = float(os.getenv('THUMBNAIL_DENOISE_STRENGTH', '0.50'))
    if not 0 < strength <= 1:
        raise ValueError('Thumbnail strength must be greater than zero and at most one')
    with Image.open(path) as image:
        image.verify()
    root = Path(__file__).resolve().parent
    return dict(reference_image=str(path.relative_to(root)) if path.is_relative_to(root) else str(path),
                reference_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), strength=strength)


def image_plan(song):
    from kids_rhymes import validate_storyboard
    validate_storyboard(song)
    identity = hashlib.sha256(json.dumps(song, sort_keys=True).encode()).hexdigest()
    portrait = os.getenv('IMAGE_VARIANT') == 'portrait'
    scenes = song['scenes']
    if portrait:
        from shorts import validate_clip
        start, seconds = int(os.getenv('CLIP_START', '0')), int(os.getenv('CLIP_SECONDS', '40'))
        validate_clip(start, seconds)
        if start + seconds > song['duration']:
            raise ValueError('Portrait clip exceeds song duration')
        scenes = scenes[start//5:(start+seconds)//5]
        identity += '-portrait-v2'
    entries = [(f"scene-{s['index']:03d}", s['prompt']) for s in scenes]
    if portrait:
        entries = [(kind, 'Portrait 9:16 composition, full-height storybook scene. ' +
                    prompt.replace('wide landscape', 'vertical composition') +
                    ' Keep characters and lyric props visible, no borders or panels.')
                   for kind, prompt in entries]
    else:
        entries.append(('thumbnail',
            'Cute colorful 3D storybook cartoon, stylized animated children, rounded toy-like shapes. '
            'Five happy toddlers dancing with baby animal friends, one large central child, '
            'two friends on each side, joyful expressive faces, raised hands, colorful rompers. '
            'Vibrant dreamy garden party, glowing festive lights, flowers, soft magical light. '
            'Polished nursery rhyme thumbnail, no text, no photography. ' + song['scenes'][0]['prompt']))
    plans = [dict(kind=kind, prompt=prompt, seed=int(hashlib.sha256((identity+kind).encode()).hexdigest()[:8],16),
        model=MODEL, revision=REVISION, width=int(os.getenv('CPU_IMAGE_WIDTH','576' if portrait else '1024')),
        height=int(os.getenv('CPU_IMAGE_HEIGHT','1024' if portrait else '576')), steps=int(os.getenv('CPU_IMAGE_STEPS','16')),
        visual_style='dudi-storybook-v2', allow_text=False) for kind,prompt in entries]
    if not portrait:
        thumbnail=plans[-1]
        thumbnail.update(width=int(os.getenv('THUMBNAIL_IMAGE_WIDTH','1344')),
                         height=int(os.getenv('THUMBNAIL_IMAGE_HEIGHT','768')),
                         steps=int(os.getenv('THUMBNAIL_IMAGE_STEPS','20')),
                         visual_style='dudi-reference-storybook-hd-v1', **thumbnail_reference(identity))
        w,h,steps=thumbnail['width'],thumbnail['height'],thumbnail['steps']
        if (w%8 or h%8 or not 256<=w<=1536 or not 256<=h<=1536
                or abs(w/h-16/9)>.1 or not 1<=steps<=50):
            raise ValueError('Thumbnail requires near-16:9 dimensions, multiples of eight in 256–1536 and 1–50 steps')
    return plans


def generate_song_images(root, song):
    from image_cpu import generate
    root = Path(root)
    if os.getenv('IMAGE_VARIANT') == 'portrait':
        root = root/'portrait'
    root.mkdir(parents=True, exist_ok=True)
    shard, count = int(os.getenv('IMAGE_SHARD','0')), int(os.getenv('IMAGE_SHARDS','1'))
    if not 0 <= shard < count:
        raise ValueError('Invalid image shard')
    manifest = root/f'image-manifest-{shard:02d}.json'
    previous = json.loads(manifest.read_text()) if manifest.exists() else {}
    completed = {}
    for i, plan in enumerate(image_plan(song)):
        if i % count != shard:
            continue
        kind = plan['kind']
        target = root/f'{kind}-source.png'
        valid = False
        if previous.get(kind) == plan and target.exists():
            try:
                with Image.open(target) as im:
                    im.verify()
                valid = True
            except (OSError,ValueError):
                pass
        if not valid:
            temporary = target.with_suffix('.tmp.png')
            reference_options = {}
            if 'reference_image' in plan:
                reference = Path(plan['reference_image'])
                if not reference.is_absolute():
                    reference = Path(__file__).resolve().parent/reference
                reference_options = dict(reference_image=reference, strength=plan['strength'])
            generate(plan['prompt'], temporary, seed=plan['seed'], allow_text=False,
                     width=plan['width'], height=plan['height'], steps=plan['steps'], **reference_options)
            with Image.open(temporary) as im:
                im.verify()
            temporary.replace(target)
        completed[kind] = plan
        temp = manifest.with_suffix('.tmp')
        temp.write_text(json.dumps(completed,indent=2))
        temp.replace(manifest)
    return completed
