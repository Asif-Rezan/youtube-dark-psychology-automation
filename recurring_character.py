"""Reference-locked illustrated host shared by thumbnail and every scene."""
import hashlib
from pathlib import Path
from PIL import Image, ImageFilter

ASSET = Path(__file__).resolve().parent / 'assets/brand/hooded-eye.png'
VERSION = 'hooded-eye-title-poses-v2'
POSES = ('shushing', 'thinking', 'stop', 'pointing', 'confident')
IDENTITY = 'indigo hood, white bandaged face and hands, one blue eye'


def pose_for_text(text):
    import re
    words = set(re.findall(r'[a-z]+', text.casefold()))
    for pose, terms in (
        ('stop', {'boundary','boundaries','stop','refuse','toxic','pressure','coercion'}),
        ('shushing', {'silence','silent','secret','secrets','quiet','restraint'}),
        ('confident', {'confidence','confident','independence','independent','mastery','alone','respect','win','power'}),
        ('pointing', {'warning','sign','signs','spot','recognize','notice','manipulation','control','controls'}),
        ('thinking', {'why','think','thinking','understand','nature','mind','decision','question'})):
        if words & terms:
            return pose
    return 'thinking'


def pose_asset(pose):
    if pose not in POSES:
        raise ValueError('Unknown recurring character pose')
    return ASSET if pose == 'shushing' else ASSET.with_name(f'hooded-eye-{pose}.png')


def asset_hash():
    digest = hashlib.sha256(VERSION.encode())
    for pose in POSES:
        digest.update(pose.encode())
        digest.update(pose_asset(pose).read_bytes())
    return digest.hexdigest()


def scene_side(identity):
    return 'left' if hashlib.sha256(str(identity).encode()).digest()[0] % 2 else 'right'


def composite_host(image, *, thumbnail=False, side='right', pose='shushing'):
    """Place the same real RGBA asset, never ask diffusion to recreate its identity."""
    image = image.convert('RGBA')
    width, height = image.size
    with Image.open(pose_asset(pose)) as source:
        if source.mode != 'RGBA' or source.getextrema()[3][0] == 255:
            raise ValueError('Recurring character requires a transparent RGBA asset')
        host = source.crop(source.getbbox())
    scale = min(width*(.62 if thumbnail else .38)/host.width,
                height*(.74 if thumbnail else .60)/host.height)
    host_width, host_height = round(host.width*scale), round(host.height*scale)
    host = host.resize((host_width, host_height), Image.Resampling.LANCZOS)
    x = (width - host_width)//2 if thumbnail else (
        round(width*.035) if side == 'left' else width-host_width-round(width*.035))
    y = round(height*.25) if thumbnail else round(height*.25)
    shadow = Image.new('RGBA', image.size)
    shadow.paste((0,0,0,190), (x,y,x+host_width,y+host_height), host.getchannel('A'))
    image = Image.alpha_composite(image, shadow.filter(ImageFilter.GaussianBlur(max(2, width//100))))
    image.alpha_composite(host, (x,y))
    return image


def finish_scene(path, identity, context=''):
    path = Path(path)
    with Image.open(path) as image:
        result = composite_host(image, side=scene_side(identity), pose=pose_for_text(context))
    result.convert('RGB').save(path)
