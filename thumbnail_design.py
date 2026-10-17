"""Readable 16:9 historical documentary thumbnail layout."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps


def _font(size):
    for path in ('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
                 '/System/Library/Fonts/Supplemental/Arial Bold.ttf'):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def render_thumbnail(source, text, target, category='History'):
    words = text.upper().split()
    if not 2 <= len(words) <= 5 or len(text) > 30 or not text.endswith('?'):
        raise ValueError('Thumbnail hook must be a short historical question')
    with Image.open(source) as original:
        image = ImageOps.fit(original.convert('RGB'), (1280, 720), method=Image.Resampling.LANCZOS)
    # Darken only the text side; preserve the main historical subject on the right.
    overlay = Image.new('RGBA', image.size, (0, 0, 0, 0))
    stripe = ImageDraw.Draw(overlay)
    for x in range(0, 820, 4):
        opacity = round(225 * max(0, 1 - (x / 820) ** 1.9))
        stripe.rectangle((x, 0, x+3, 720), fill=(4, 13, 20, opacity))
    image = Image.alpha_composite(image.convert('RGBA'), overlay)
    draw = ImageDraw.Draw(image)
    cream, gold = (250, 247, 235, 255), (255, 195, 87, 255)
    category_lower = category.casefold()
    if 'egypt' in category_lower:
        label = 'ANCIENT EGYPT'
    elif 'islamic' in category_lower or 'famous people' in category_lower:
        label = 'ISLAMIC HISTORY'
    elif 'civilization' in category_lower:
        label = 'ANCIENT WORLD'
    else:
        label = 'ARCHAEOLOGY'
    label_font = _font(23)
    label_width = draw.textbbox((0, 0), label, font=label_font)[2]
    draw.rounded_rectangle((60, 72, 95+label_width, 124), radius=9, fill=(230, 161, 55, 255))
    draw.text((78, 83), label, font=label_font, fill=(13, 24, 29, 255))
    # Short hooks use one or two lines with a fixed left edge and ample mobile-safe margins.
    lines = [' '.join(words)]
    if len(words) >= 3:
        split = (len(words)+1)//2
        lines = [' '.join(words[:split]), ' '.join(words[split:])]
    width = 540
    size = 110
    while size >= 56:
        font = _font(size)
        if all(draw.textbbox((0, 0), line, font=font, stroke_width=2)[2] <= width for line in lines):
            break
        size -= 4
    if size < 56:
        raise ValueError('Thumbnail hook cannot fit at readable size')
    y = 298 if len(lines) == 1 else 240
    for index, line in enumerate(lines):
        draw.text((61, y + index*(size+18)), line, font=font,
                  fill=cream if index == 0 else gold, stroke_width=3,
                  stroke_fill=(4, 13, 20, 255))
    draw.rectangle((64, 652, 390, 660), fill=gold)
    output = Path(target)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.convert('RGB').save(output, quality=89, optimize=True)
    if output.stat().st_size >= 2*1024*1024:
        image.convert('RGB').save(output, quality=78, optimize=True)
    if output.stat().st_size >= 2*1024*1024:
        raise RuntimeError('Thumbnail exceeds YouTube size limit')
    return output
