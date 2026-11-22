"""Reference-locked illustrated host shared by thumbnail and every scene."""
import hashlib
from pathlib import Path
from PIL import Image, ImageFilter

ASSET = Path(__file__).resolve().parent / 'assets/brand/hooded-eye.png'
VERSION = 'hooded-eye-reference-v1'
IDENTITY = 'indigo hood, white bandaged face and hand, one blue eye, shushing gesture'


def asset_hash():
    return hashlib.sha256(ASSET.read_bytes()).hexdigest()


def scene_side(identity):
    return 'left' if hashlib.sha256(str(identity).encode()).digest()[0] % 2 else 'right'


def composite_host(image, *, thumbnail=False, side='right'):
    """Place the same real RGBA asset, never ask diffusion to recreate its identity."""
    image = image.convert('RGBA')
    width, height = image.size
    with Image.open(ASSET) as source:
        if source.mode != 'RGBA' or source.getextrema()[3][0] == 255:
            raise ValueError('Recurring character requires a transparent RGBA asset')
        host = source.crop(source.getbbox())
    host_height = round(height * (.67 if thumbnail else .60))
    host_width = round(host.width * host_height / host.height)
    host = host.resize((host_width, host_height), Image.Resampling.LANCZOS)
    x = (width - host_width)//2 if thumbnail else (
        round(width*.035) if side == 'left' else width-host_width-round(width*.035))
    y = round(height*.23) if thumbnail else round(height*.25)
    shadow = Image.new('RGBA', image.size)
    shadow.paste((0,0,0,190), (x,y,x+host_width,y+host_height), host.getchannel('A'))
    image = Image.alpha_composite(image, shadow.filter(ImageFilter.GaussianBlur(max(2, width//100))))
    image.alpha_composite(host, (x,y))
    return image


def finish_scene(path, identity):
    path = Path(path)
    with Image.open(path) as image:
        result = composite_host(image, side=scene_side(identity))
    result.convert('RGB').save(path)
