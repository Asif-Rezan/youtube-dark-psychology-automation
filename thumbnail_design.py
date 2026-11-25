"""Complete episode-specific artwork with a heavy top-only headline."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps
from itertools import combinations


def _font(size):
    bundled = Path(__file__).resolve().parent/'assets/brand/Oswald.ttf'
    if bundled.exists():
        font = ImageFont.truetype(str(bundled), size)
        font.set_variation_by_axes([700])
        return font
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
    for size in range(112, 55, -4):
        font = _font(size)
        for count in (1, 2, 3):
            for breaks in combinations(range(1, len(words)), count - 1):
                cuts = (0,) + breaks + (len(words),)
                lines = [' '.join(words[cuts[i]:cuts[i + 1]]) for i in range(count)]
                if all(measure.textbbox((0, 0), line, font=font, stroke_width=3)[2] <= 500
                       for line in lines):
                    return lines, size
    raise ValueError('Thumbnail hook cannot fit at readable size')


PALETTES = ('deep crimson and black textured background',)


def art_direction(identity):
    return 'center', PALETTES[0]


def complete_thumbnail_prompt(visual, text, identity):
    """Generate the complete scene and its focal subject in one image."""
    import re
    hook_layout(text)
    visual = re.sub(r'\b(?:no text|no written letters|no letters|no embedded letters)\b', '', visual, flags=re.I)
    # Keep the episode-specific relationship instead of discarding later sentences.
    visual = visual.split('. Dark red and black graphic illustration')[0].strip(' ,. ')
    visual = ' '.join(visual.split()[:45])
    return (f'{visual}. Close-up, large expressive subject and one oversized clue. '
            'Deep crimson and black backdrop, bright ivory highlights, rim light, strong silhouette. '
            'Upper quarter stays uncluttered. Complete finished scene; simple shapes, minimal clutter, '
            'no writing, logos or mascot.')


def render_thumbnail(source, text, target, category='Dark Psychology', *, text_side='left'):
    """Add only the exact top headline to the complete generated artwork."""
    hook_layout(text)
    if text_side not in ('left', 'right'):
        raise ValueError('Invalid thumbnail text side')
    with Image.open(source) as original:
        image = ImageOps.fit(original.convert('RGB'), (1920,1080), method=Image.Resampling.LANCZOS)
    # Keep the generated episode clue visible while unifying the channel palette.
    red = Image.new('RGB', image.size, '#7A060B')
    image = Image.blend(image, red, .12).convert('RGBA')
    shade = Image.new('RGBA', image.size)
    sd = ImageDraw.Draw(shade)
    sd.rectangle((0,0,1919,245), fill=(0,0,0,170))
    image = Image.alpha_composite(image, shade)
    draw = ImageDraw.Draw(image)
    # Full-width headline like the supplied reference, with a strong phone-readable floor.
    words = text.upper().split()
    measure = ImageDraw.Draw(Image.new('RGB', (1,1)))
    chosen = None
    for size in range(208, 95, -4):
        font = _font(size)
        layouts = [words]
        layouts += [words[:i]+['\n']+words[i:] for i in range(1,len(words))]
        for layout in layouts:
            lines = ' '.join(layout).split(' \n ')
            widths = [measure.textbbox((0,0), line, font=font, stroke_width=5)[2] for line in lines]
            if max(widths) <= 1760 and len(lines)*(size+8) <= 245:
                chosen = (lines,size)
                break
        if chosen:
            break
    if chosen is None:
        raise ValueError('Thumbnail headline cannot fit in the upper quarter')
    lines,size = chosen
    font = _font(size)
    for i,line in enumerate(lines):
        box = draw.textbbox((0,0),line,font=font,stroke_width=5)
        x = (1920-(box[2]-box[0]))//2
        draw.text((x,25+i*(size+8)),line,font=font,
                  fill='#FFFFFF',stroke_width=8,stroke_fill='#080000')
        draw.text((x,25+i*(size+8)),line,font=font,fill='#FFFFFF',stroke_width=2,stroke_fill='#FFFFFF')
        for word_index, word in enumerate(line.split()):
            if word_index in (0, len(line.split())-1):
                prefix = ' '.join(line.split()[:word_index])
                offset = draw.textlength(prefix+' ' if prefix else '', font=font)
                draw.text((x+offset,25+i*(size+8)),word,font=font,fill='#FFFF00',stroke_width=8,stroke_fill='#080000')
                draw.text((x+offset,25+i*(size+8)),word,font=font,fill='#FFFF00',stroke_width=2,stroke_fill='#FFFF00')
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
    generate(prompt,source,seed=seed,style='dark-graphic',width=1344,height=768)
    text_side = 'left'
    target = render_thumbnail(source,story['thumbnail_text'],root/'thumbnail.jpg',text_side=text_side)
    with Image.open(target) as mobile:
        mobile.resize((320,180),Image.Resampling.LANCZOS).save(root/'thumbnail-mobile.jpg')
    (root/'thumbnail-design.json').write_text(json.dumps(dict(
        version='red-mobile-focus-v8',artwork_mode='single-generated-scene',seed=seed,prompt=prompt,text=story['thumbnail_text'],
        text_side=text_side,text_mode='composited-exact',
        generation_size=[1344,768],export_size=[1920,1080],crop='center to 16:9 (1344x756)',
        visual_review='Inspect subject, factual fit and mobile preview; CTR requires analytics'),indent=2))
    return target
