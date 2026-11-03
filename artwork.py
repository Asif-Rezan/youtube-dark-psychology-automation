"""Compose song-specific artwork from two freshly generated cinematic scenes.

The SSD-1B image job supplies a separate background and thumbnail source.
"""
from pathlib import Path
import re
from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps

ASSETS = Path(__file__).resolve().parent / 'assets' / 'artwork'
MOODS = {
    'romance': ('#ffdf96', 'HINDI LOVE SONG', 'TERE SAATH'),
    'heartbreak': ('#c4dcff', 'HINDI SAD SONG', 'ADHURI BAATEIN'),
    'healing': ('#ffe4a1', 'HINDI SOULFUL SONG', 'NAYI SUBAH'),
}


def visual_mood(song):
    if song.get('visual_mood') in MOODS:
        return song['visual_mood']
    # Backwards-compatible inference for older song.json artifacts.
    text = (song.get('prompt', '') + ' ' + song.get('title', '')).lower()
    if any(word in text for word in ('sad', 'heartbreak', 'longing', 'दर्द', 'अधूर')):
        return 'heartbreak'
    if any(word in text for word in ('hope', 'healing', 'uplifting', 'नई सुबह')):
        return 'healing'
    return 'romance'


def font(size):
    for path in (ASSETS/'Oswald.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
                 '/Library/Fonts/Arial Bold.ttf', 'DejaVuSans-Bold.ttf'):
        try:
            face = ImageFont.truetype(str(path), size)
            if Path(path).name == 'Oswald.ttf':
                face.set_variation_by_axes([650])
            return face
        except OSError:
            pass
    raise RuntimeError('A scalable bold font is required for artwork')


def hook_text(song, mood):
    hook = song.get('thumbnail_text', '').strip().upper()
    hook = ' '.join(re.sub(r'\b20\d{2}\b', '', hook).split())
    if (not re.fullmatch(r'[A-Z0-9 !?]{3,26}', hook) or
            not 2 <= len(hook.split()) <= 4 or 'HEART' in hook or 'MIND' in hook):
        return MOODS[mood][2]
    return hook


def brighten_scene(image):
    """Lift dark photographic midtones while preserving black and white endpoints."""
    import math
    import numpy as np
    color = image.convert('RGB')
    median = float(np.median(np.asarray(ImageOps.grayscale(color))))
    if 0 < median < 120:
        gamma = max(0.55, min(1.0, math.log(120/255) / math.log(median/255)))
        lut = [round(255*(value/255)**gamma) for value in range(256)]
        color = color.point(lut * 3)
    return color


def poster_finish(image):
    """Rich, clean album-poster color without grain, distress or monochrome conversion."""
    image = ImageEnhance.Color(image.convert('RGB')).enhance(1.14)
    return ImageEnhance.Contrast(image).enhance(1.04)


def poster_thumbnail(source, song, mood):
    """Export the text-free thumbnail scene without drawing text or overlays."""
    return ImageOps.fit(source.convert('RGB'), (1280, 720), method=Image.Resampling.LANCZOS)


def create_artwork(root, song):
    root = Path(root)
    mood = visual_mood(song)
    accent, label, _ = MOODS[mood]
    def compose(kind):
        scene = root/f'{kind}-source.png'
        if not scene.exists():
            raise RuntimeError('Generated song artwork missing; run the images stage first')
        with Image.open(scene) as source:
            base = brighten_scene(ImageOps.fit(source.convert('RGB'), (1920, 1080), method=Image.Resampling.LANCZOS))
        overlay = Image.new('RGBA', base.size)
        gradient = ImageDraw.Draw(overlay)
        for x in range(base.width):
            alpha = int(45 * max(0, 1-x/1450))
            gradient.line((x, 0, x, 1080), fill=(8, 12, 24, alpha))
        return Image.alpha_composite(base.convert('RGBA'), overlay).convert('RGB')
    base = compose('background')
    cover = base
    draw = ImageDraw.Draw(cover)
    # Keep the video scene calm; waveform sits below the people, not across their faces.
    draw.text((92, 86), 'HEART & MIND', font=font(28), fill='#f0e9e2')
    draw.text((92, 825), hook_text(song, mood), font=font(64), fill=accent)
    draw.text((96, 918), label, font=font(24), fill='#ffffff')
    cover = poster_finish(cover)
    cover.save(root/'cover.png')
    with Image.open(root/'thumbnail-source.png') as source:
        thumb = poster_thumbnail(source, song, mood)
    thumb.save(root/'thumbnail.jpg', quality=92, optimize=True)
