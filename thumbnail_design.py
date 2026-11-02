"""Episode-specific 3D storybook thumbnails with integrated headlines."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps
from itertools import combinations
from visual_style import STORYBOOK_STYLE


def _font(size):
    for path in ('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
                 '/System/Library/Fonts/Supplemental/Arial Bold.ttf'):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def hook_layout(text):
    """Find a readable one to three line layout before artwork is generated."""
    words = text.upper().split()
    if not 2 <= len(words) <= 5 or len(text) > 30 or not text.endswith('?'):
        raise ValueError('Thumbnail hook must be a short historical question')
    measure = ImageDraw.Draw(Image.new('RGB', (1, 1)))
    for size in range(96, 55, -4):
        font = _font(size)
        for count in (1, 2, 3):
            for breaks in combinations(range(1, len(words)), count - 1):
                cuts = (0,) + breaks + (len(words),)
                lines = [' '.join(words[cuts[i]:cuts[i + 1]]) for i in range(count)]
                if all(measure.textbbox((0, 0), line, font=font, stroke_width=3)[2] <= 500
                       for line in lines):
                    return lines, size
    raise ValueError('Thumbnail hook cannot fit at readable size')


PALETTES = ('amber rim light, deep cobalt background',
            'cyan rim light, warm coral background',
            'golden rim light, dark teal background')


def art_direction(identity):
    import hashlib
    digest = hashlib.sha256(identity.encode()).digest()
    return ('right' if digest[0] % 2 else 'left'), PALETTES[digest[1] % len(PALETTES)]


def complete_thumbnail_prompt(visual, text, identity):
    """Short artwork brief: the CPU model is unreliable at rendering letters."""
    import re
    hook_layout(text)
    side, palette = art_direction(identity)
    visual = re.sub(r'\b(?:no text|no written letters|no letters|no embedded letters)\b', '', visual, flags=re.I)
    visual = re.sub(r'(?:open |empty )?dark space on the (?:left|right)', '', visual, flags=re.I)
    visual = re.sub(r'\b(?:on the |at |at the |on )?(?:right|left)(?: side| foreground)?\b', '', visual, flags=re.I)
    visual = visual.split('. ')[0].strip(' ,. ')
    # Subject and scale lead, before the encoders truncate longer instructions.
    return (f'3D storybook illustration. {visual}. '
            f'Large focal subject on {side}, opposite side uncluttered. '
            f'{palette}. Expressive human face, mature psychological drama, '
            'one visual clue, simple background, strong silhouette, no writing.')


def render_thumbnail(source, text, target, category='History', *, text_side='left'):
    """Composite exact readable type over a reserved area, preserving the subject."""
    lines, size = hook_layout(text)
    if text_side not in ('left', 'right'):
        raise ValueError('Invalid thumbnail text side')
    with Image.open(source) as original:
        image = ImageOps.fit(original.convert('RGB'), (1280,720), method=Image.Resampling.LANCZOS)
    overlay = Image.new('RGBA', image.size, (0,0,0,0))
    draw = ImageDraw.Draw(overlay)
    for x in range(640):
        opacity = round(185 * (1-x/640))
        px = x if text_side == 'left' else 1279-x
        draw.line((px,0,px,719), fill=(5,10,22,opacity))
    image = Image.alpha_composite(image.convert('RGBA'), overlay)
    draw = ImageDraw.Draw(image)
    font = _font(size)
    x = 90 if text_side == 'left' else 690
    # Keep type away from edges and the bottom-right timestamp.
    top = (620-len(lines)*(size+16))//2
    for i,line in enumerate(lines):
        draw.text((x,top+i*(size+16)),line,font=font,
                  fill='#FFFFFF' if i == 0 else '#FFE04B',
                  stroke_width=5,stroke_fill='#070B16')
    output = Path(target)
    output.parent.mkdir(parents=True, exist_ok=True)
    for quality in (92,85,75):
        image.convert('RGB').save(output,quality=quality,optimize=True)
        if output.stat().st_size < 2*1024*1024:
            return output
    raise RuntimeError('Thumbnail exceeds YouTube size limit')


def generate_thumbnail(story, root, identity):
    import hashlib
    import json
    from image_cpu import generate
    root = Path(root)
    root.mkdir(parents=True,exist_ok=True)
    prompt = complete_thumbnail_prompt(story['thumbnail_prompt'],story['thumbnail_text'],identity)
    seed = int(hashlib.sha256((identity+prompt).encode()).hexdigest()[:8],16)
    source = root/'thumbnail-source.png'
    generate(prompt,source,seed=seed,style='storybook-3d')
    subject_side, _ = art_direction(identity)
    text_side = 'left' if subject_side == 'right' else 'right'
    target = render_thumbnail(source,story['thumbnail_text'],root/'thumbnail.jpg',text_side=text_side)
    with Image.open(target) as mobile:
        mobile.resize((320,180),Image.Resampling.LANCZOS).save(root/'thumbnail-mobile.jpg')
    (root/'thumbnail-design.json').write_text(json.dumps(dict(
        version='storybook-mobile-v3',seed=seed,prompt=prompt,text=story['thumbnail_text'],
        text_side=text_side,text_mode='composited-exact',
        visual_review='Inspect subject, factual fit and mobile preview; CTR requires analytics'),indent=2))
    return target
