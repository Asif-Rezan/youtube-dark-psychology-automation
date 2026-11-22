"""Reference-style illustrated thumbnails with a title-specific mascot pose."""
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
    """Generate only the episode backdrop; exact host and lettering are composited."""
    import re
    hook_layout(text)
    visual = re.sub(r'\b(?:no text|no written letters|no letters|no embedded letters)\b', '', visual, flags=re.I)
    visual = visual.split('. ')[0].strip(' ,. ')
    return (f'Dark psychology graphic illustration. {visual}. '
            'Deep crimson and black grunge background, dramatic shadow, bold outlines, '
            'one large symbolic clue beside a clear center. Upper quarter uncluttered. '
            'No writing, no hooded mascot; the reference mascot is added separately.')


def render_thumbnail(source, text, target, category='Dark Psychology', *, text_side='left', pose=None):
    """Heavy top headline and title-specific mascot; no footer or niche label."""
    from recurring_character import composite_host, pose_for_text
    hook_layout(text)
    if text_side not in ('left', 'right'):
        raise ValueError('Invalid thumbnail text side')
    with Image.open(source) as original:
        image = ImageOps.fit(original.convert('RGB'), (1920,1080), method=Image.Resampling.LANCZOS)
    # Keep the generated episode clue visible while unifying the channel palette.
    red = Image.new('RGB', image.size, '#7A060B')
    image = Image.blend(image, red, .34).convert('RGBA')
    shade = Image.new('RGBA', image.size)
    sd = ImageDraw.Draw(shade)
    sd.rectangle((0,0,1919,245), fill=(0,0,0,170))
    image = Image.alpha_composite(image, shade)
    image = composite_host(image, thumbnail=True, pose=pose or pose_for_text(text))
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
        raise ValueError('Thumbnail headline cannot fit above the character')
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
    # Curved yellow pointer highlights the recurring host, not an invented scene detail.
    draw.arc((380,250,770,600),95,210,fill='#FFFF00',width=17)
    draw.line([(560,573),(620,590),(593,530)],fill='#FFFF00',width=17,joint='curve')
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
    from recurring_character import VERSION, asset_hash, pose_for_text
    text_side = 'left'
    pose = story.get('thumbnail_pose') or pose_for_text(story['title']+' '+story['thumbnail_text'])
    target = render_thumbnail(source,story['thumbnail_text'],root/'thumbnail.jpg',text_side=text_side,pose=pose)
    with Image.open(target) as mobile:
        mobile.resize((320,180),Image.Resampling.LANCZOS).save(root/'thumbnail-mobile.jpg')
    (root/'thumbnail-design.json').write_text(json.dumps(dict(
        version='hooded-eye-top-headline-v6',character_pose=pose,character_version=VERSION,character_sha256=asset_hash(),seed=seed,prompt=prompt,text=story['thumbnail_text'],
        text_side=text_side,text_mode='composited-exact',
        generation_size=[1344,768],export_size=[1920,1080],crop='center to 16:9 (1344x756)',
        visual_review='Inspect subject, factual fit and mobile preview; CTR requires analytics'),indent=2))
    return target
