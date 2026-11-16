"""Procedural white-stage animation and colorful prehistoric cover artwork."""
from functools import lru_cache
import hashlib
import math
from pathlib import Path
from random import Random

from PIL import Image, ImageDraw, ImageFont, ImageFilter
from PIL.ImageColor import getrgb

from .character_rig import character
from .editorial import TOPICS


SIZE = (1280,720)
FONT = Path(__file__).resolve().parents[1]/'assets/artwork/Oswald.ttf'
INK = '#292222'
PALETTES = {
    # Sky, horizon, ground, distant silhouettes, and local terrain accents.
    'stone': (('#238ad0','#a6e1fc','#d58a45','#675084','#f2bd69'),
              ('#164c9a','#59c4ed','#b25f38','#384b76','#f3ad5e')),
    'fire': (('#101f53','#405697','#1f594d','#232748','#4b875d'),
             ('#39205d','#b14b75','#59466c','#412b6b','#88678b')),
    'map': (('#733e94','#ff823e','#d59d43','#4c528c','#ecb769'),
            ('#1670bd','#71d7e3','#749542','#304e83','#a5cf54')),
    'food': (('#177fae','#a6ebec','#659d2f','#376d6b','#98d745'),
             ('#1975bf','#85d4ef','#38925c','#2d5d73','#69c474')),
    'art': (('#2e234e','#a44b67','#a96b54','#592f62','#e29172'),
            ('#503348','#e78043','#a97a50','#564766','#ecab69')),
    'shelter': (('#263874','#8bb9e4','#5f819f','#4a527e','#9fc8dc'),
                ('#32294e','#66799d','#63776d','#364e68','#9cb28f')),
}

# Cast, scale and prop positions vary with the story rather than mirroring every cover.
STAGING = {
    'stone': (280,1.78,'work',835,1.46,'react',609,616,1.78),
    'fire': (360,1.47,'carry',980,1.45,'react',690,603,2.05),
    'map': (282,1.6,'show',942,1.4,'react',680,570,1.92),
    'food': (306,1.61,'carry',939,1.61,'show',632,644,1.75),
    'art': (235,1.57,'show',1050,1.20,'react',669,637,1.86),
    'shelter': (265,1.53,'carry',1006,1.44,'react',664,638,1.48),
}


def poly(draw, points, fill):
    draw.polygon(points,fill=fill,outline=INK,width=2)


def prop(draw, kind, x,y,scale,t,active):
    def shape(points,fill):
        poly(draw,[(round(x+px*scale),round(y+py*scale)) for px,py in points],fill)

    if kind == 'fire':
        shape([(-72,-5),(65,-4),(48,12),(-48,12)],'#84614d')
        for i in range(3):
            sway = 8*math.sin(t*6+i)
            dx = (i-1)*30
            shape([(dx-25,-9),(dx-32,-40),(dx-10,-67),(dx+sway,-111+i*19),
                   (dx+15,-69),(dx+30,-42),(dx+21,-12)],('#f28a36','#ffbf44','#ec6837')[i])
        shape([(-21,-10),(-10,-37),(7,-58),(15,-26),(29,-10)],'#ffed95')
        for i in range(7):
            travel = (t*(.75+i*.04)+i*.152)%1
            px,py=x+math.sin(t*4+i)*27*scale,y-(38+travel*113)*scale
            r=max(1,(1-travel)*3*scale)
            draw.ellipse((px-r,py-r,px+r,py+r),fill='#d66837')
    elif kind == 'shelter':
        shape([(-160,6),(-142,-138),(-62,-222),(46,-229),(136,-167),(171,3)],'#a58675')
        shape([(-67,4),(-64,-60),(-12,-131),(56,-123),(90,-66),(96,4)],'#413746')
        shape([(-142,-137),(-62,-222),(46,-229),(26,-178),(-68,-161)],'#c2a489')
        shape([(46,-229),(136,-167),(171,3),(114,3),(104,-117),(26,-178)],'#775d56')
        shape([(-159,6),(-137,-57),(-101,-75),(-85,-39),(-86,7)],'#b39783')
    elif kind == 'map':
        shape([(-45,-208),(29,-194),(65,-172),(81,-121),(122,-111),(85,-74),(62,-40),
               (45,1),(18,20),(-10,-17),(-24,-69),(-69,-83),(-109,-104),(-108,-153),(-83,-193)],'#cbb579')
        for dx,dy in [(-26,-171),(28,-109),(53,-79)]:
            px,py=x+dx*scale,y+dy*scale
            radius=scale*(5+math.sin(t*4))
            draw.ellipse((px-radius,py-radius,px+radius,py+radius),fill='#bd5744')
    elif kind == 'art':
        shape([(-112,8),(-120,-155),(-66,-214),(76,-207),(111,-149),(115,9)],'#d8b397')
        for i in range(4):
            px,py=x+(i*37-54)*scale,y-(63+(i%2)*34)*scale
            draw.line([(px,py),(px+15*scale,py-24*scale),(px+30*scale,py)],
                      fill='#923f37',width=round(7*scale),joint='curve')
    elif kind == 'food':
        shape([(-84,-20),(72,-20),(54,7),(-62,7)],'#b08159')
        for i in range(7):
            dx=(i-3)*19
            shape([(dx-12,-20),(dx-13,-40),(dx,-49-i%3*9),(dx+13,-36),(dx+10,-20)],
                  ('#955044','#b87453','#697f5b')[i%3])
    else:
        shape([(-86,7),(-102,-31),(-62,-79),(32,-75),(77,-48),(69,6)],'#8f8b87')
        shape([(-102,-31),(-62,-79),(32,-75),(20,-47),(-30,-24)],'#c5b4a4')
        for i in range(3):
            dx=(i-1)*36
            wobble = math.sin(t*6+i)*12 if active else 0
            shape([(dx-7,-15+wobble),(dx-24,-47+wobble),(dx+10,-35+wobble),(dx+16,-13+wobble)],'#e6d5b9')


def actor(draw,x,y,*,t,action,female=False,facing=1,scale=1.55,variant=0):
    work = action in ('work','gather','share')
    character(draw,x,y,scale=scale,female=female,facing=facing,islamic=False,
              walk_phase=t*8 if action in ('walk','carry') else None,
              basket=action=='carry',work=t*(3.4 if action=='share' else 7) if work else None,point=action=='show',
              wave=t*(2.7 if action=='watch' else 4) if action in ('react','show','watch') else None,
              blink=t%3.9>3.75,breathing=1.8*math.sin(t*2.2),
              expression='surprised' if action=='react' else 'curious' if work else 'calm',variant=variant)


def lit_terrain(draw,kind,environment):
    """Layer earth facets and vegetation with depth and a common light direction."""
    _,_,earth,_,_ = PALETTES[kind][0]
    base = getrgb(earth)
    rng = Random(f'{kind}:{environment}')
    for _ in range(35):
        y = rng.randrange(574,652)
        depth = (y-553)/105
        spread = 535-abs(y-602)*3
        x = rng.uniform(640-spread,640+spread)
        width = rng.uniform(8,27)*depth
        shade = rng.choice((.24,.33,.44))
        color = tuple(round(c*shade+255*(1-shade)) for c in base)
        draw.polygon([(x-width,y),(x+width*.65,y-4*depth),(x+width,y-1),
                      (x+width*.45,y+4*depth)],fill=color)
    grass = environment in ('food','fire','map')
    for x,y,scale in ((164,621,.85),(244,649,1.13),(1050,634,1.14),
                      (1127,595,.65),(940,576,.46),(349,573,.48)):
        draw.ellipse((x-20*scale,y-3*scale,x+27*scale,y+8*scale),fill='#c8bfad')
        if grass:
            for angle in (-1.2,-.6,-.1,.5,.87):
                tipx,tipy=x+angle*25*scale,y-(30-abs(angle)*9)*scale
                fill = ('#7b9656' if angle>.1 else '#55764f')
                draw.polygon([(x+angle*8*scale,y),(tipx,tipy),
                              (x+(angle*8+5)*scale,y+1)],fill=fill)
        else:
            crest = y-16*scale
            draw.polygon([(x-25*scale,y),(x-16*scale,crest),(x+8*scale,crest-3*scale),
                          (x+23*scale,y-3*scale),(x+16*scale,y+4*scale)],fill='#9a8c80')
            draw.polygon([(x-25*scale,y),(x-16*scale,crest),(x+8*scale,crest-3*scale),
                          (x+4*scale,y-4*scale)],fill='#cdbba5')


@lru_cache(maxsize=8)
def cast_shadow(scale):
    shadow = Image.new('RGBA',(300,78))
    draw = ImageDraw.Draw(shadow)
    draw.ellipse((24,18,270,57),fill=(66,48,37,55))
    draw.ellipse((45,22,120,50),fill=(52,37,29,68))
    shadow = shadow.filter(ImageFilter.GaussianBlur(8))
    return shadow.resize((round(300*scale),round(78*scale)),Image.Resampling.BILINEAR)


def warm_light(draw,x,y,t):
    for radius,color in ((109,'#f1d7ac'),(79,'#edc48f'),(52,'#e7ae72')):
        flicker = math.sin(t*5)*3
        draw.ellipse((x-radius-flicker,y-radius*.22,x+radius+flicker,y+radius*.20),fill=color)


def terrain_detail(draw,kind):
    """Frame each narrated object with its own low-poly setting."""
    _,_,earth,peak,accent = PALETTES[kind][0]
    def tint(color, weight):
        return tuple(round(c*weight+255*(1-weight)) for c in getrgb(color))

    ridge,face,light = tint(peak,.38),tint(earth,.36),tint(accent,.38)
    if kind in ('stone','shelter','art'):
        for x,y,scale in ((93,607,1.34),(1076,587,1.58)):
            draw.polygon([(x-126*scale,y),(x-95*scale,y-120*scale),
                          (x-11*scale,y-219*scale),(x+80*scale,y-163*scale),
                          (x+150*scale,y+12*scale)],fill=ridge)
            draw.polygon([(x-95*scale,y-120*scale),(x-11*scale,y-219*scale),
                          (x+80*scale,y-163*scale),(x+20*scale,y-134*scale),
                          (x-12*scale,y+8*scale),(x-126*scale,y)],fill=face)
            draw.polygon([(x-11*scale,y-219*scale),(x+10*scale,y-154*scale),
                          (x-41*scale,y-132*scale),(x-95*scale,y-120*scale)],fill=light)
    else:
        for x,y,scale in ((132,598,1.30),(1120,587,1.43)):
            trunk = tint('#654131',.53)
            green = tint('#54854d',.55)
            draw.polygon([(x-7,y),(x-10,y-142*scale),(x-54*scale,y-192*scale),
                          (x-40*scale,y-192*scale),(x+4,y-162*scale),
                          (x+54*scale,y-195*scale),(x+60*scale,y-181*scale),
                          (x+11,y-132*scale),(x+12,y)],fill=trunk)
            draw.polygon([(x-125*scale,y-171*scale),(x-82*scale,y-229*scale),
                          (x-13*scale,y-245*scale),(x+75*scale,y-226*scale),
                          (x+124*scale,y-185*scale),(x+72*scale,y-164*scale),
                          (x-50*scale,y-167*scale)],fill=green)
            draw.polygon([(x-125*scale,y-171*scale),(x-82*scale,y-229*scale),
                          (x-13*scale,y-245*scale),(x+7*scale,y-194*scale)],fill=light)
    if kind == 'map':
        for x,y in ((143,166),(955,113)):
            draw.polygon([(x,y+23),(x+23,y+6),(x+62,y),(x+105,y+18),(x+127,y+24)],fill=light)
    if kind == 'fire':
        for x,y in ((462,524),(897,513),(917,541)):
            draw.polygon([(x-19,y),(x-14,y-14),(x+12,y-20),(x+24,y-6),(x+18,y+3)],fill=ridge)


@lru_cache(maxsize=12)
def stage(kind,setting=None):
    image = Image.new('RGB',SIZE,'white')
    draw = ImageDraw.Draw(image)
    environment = {'workshop':'stone','camp':'fire','grassland':'food',
                   'cave':'art','journey':'map'}.get(setting,kind)
    terrain_detail(draw,environment)
    _,_,earth,_,accent = PALETTES[kind][0]
    soil,light = getrgb(earth),getrgb(accent)
    tint = tuple(round(c*.26+255*.74) for c in soil)
    fill = tuple(round(c*.40+255*.60) for c in light)
    draw.polygon([(70,609),(349,544),(826,541),(1200,594),(1017,664),(434,675),(183,654)],fill=tint)
    draw.polygon([(70,609),(349,544),(826,541),(714,573),(307,626),(183,654)],fill=fill)
    draw.polygon([(826,541),(1200,594),(1017,664),(912,623),(714,573)],fill=fill)
    rng = Random(kind)
    for _ in range(35):
        x,y = rng.randrange(177,1110),rng.randrange(587,633)
        draw.line((x,y,x+rng.randrange(2,17),y-1),fill=tint,width=2)
    lit_terrain(draw,kind,environment)
    return image


def stone_contact(draw,x,y,t):
    swing = math.sin(t*7)
    y += round(30*swing)
    poly(draw,[(x-20,y+5),(x-14,y-18),(x+9,y-27),(x+25,y-14),
               (x+21,y+8),(x+2,y+17)],'#82736a')
    if swing > .55:
        for i in range(4):
            dx,dy = 16+i*13,-5-(i%3)*16
            draw.polygon([(x+dx,y+dy),(x+dx+10,y+dy-7),(x+dx+4,y+dy+5)],fill='#e89b41')


@lru_cache(maxsize=32)
def caption_font(size):
    return ImageFont.truetype(str(FONT),size)


def scene(beat,t,duration,shot,chapter_label=None):
    kind = beat['prop']
    cast = beat.get('cast') or [{'sex':'female' if (shot//3)%2 else 'male',
                                'action':beat.get('action','show'),'position':'left'}]
    image = stage(kind,beat.get('setting')).copy()
    draw = ImageDraw.Draw(image)
    _,_,_,_,accent = PALETTES[kind][0]
    progress = min(t/max(duration,.1),1)
    workers = {'work','gather','share'}
    presenter = next((member for member in cast if member['action'] != 'watch'),cast[0])
    lead = next((member for member in cast if member['action'] in workers),presenter)
    anchors = {'left':340,'center':610,'right':980}
    lead_x = anchors[lead['position']]
    direction = -1 if lead['position']=='right' else 1
    active = lead['action'] in workers
    prop_x = lead_x+direction*108 if active else 735 if direction==1 else 580
    prop_y = 510 if active and kind in ('stone','food') else 592
    if beat.get('secondary_prop','none') not in ('none',kind):
        secondary = beat['secondary_prop']
        secondary_x = 1065 if prop_x < 740 else 175
        if secondary=='fire':
            warm_light(draw,secondary_x,583,t)
        prop(draw,secondary,secondary_x,575,.83,t,False)
    if kind in ('fire','map','art','shelter'):
        color = tuple(round(c*.30+255*.70) for c in getrgb(accent))
        draw.ellipse((prop_x-190,155,prop_x+190,570),fill=color)
    if prop_y < 592:
        poly(draw,[(prop_x-110,600),(prop_x-106,528),(prop_x-63,500),
                   (prop_x+74,502),(prop_x+91,597)],'#bfb4a7')
        poly(draw,[(prop_x-106,528),(prop_x-63,500),(prop_x+74,502),
                   (prop_x+42,526)],'#ded4c9')
    if kind=='fire':
        warm_light(draw,prop_x,prop_y,t)
    prop(draw,kind,prop_x,prop_y,1.28 if len(cast)>1 else 1.43,t,active)
    for index,member in enumerate(cast):
        action = member['action']
        x = anchors[member['position']]
        facing = 1 if x<prop_x else -1
        if action in ('walk','carry'):
            x += facing*(progress-.45)*(140 if len(cast)>1 else 290)
        elif action in workers and member is not lead:
            # Bring collaborators toward the shared object without crossing roles.
            x += facing*min(125,abs(prop_x-x)*.40)
        y = 610+index*4
        scale = 1.48 if len(cast)>1 else 1.71
        shadow = cast_shadow(.59 if len(cast)>1 else .69)
        image.paste(shadow,(round(x-shadow.width*.28),round(y-shadow.height*.45)),shadow)
        actor(draw,x,y,t=t+index*.29,action=action,female=member['sex']=='female',facing=facing,scale=scale,variant=index)
        if kind=='stone' and action=='work' and member is lead:
            stone_contact(draw,x+facing*79,y-190,t)
    framing = beat.get('framing','detail' if active else 'medium')
    if framing=='detail' and progress>=.53 and active and kind in ('stone','food'):
        left = min(790,max(0,prop_x-244))
        image = image.resize(SIZE,Image.Resampling.BILINEAR,box=(left,340,left+488,615))
    elif framing!='wide' and progress>=.38 and len(cast)==1:
        left = min(350,max(0,lead_x-290))
        image = image.resize(SIZE,Image.Resampling.BILINEAR,box=(left,66,left+920,667))
    if chapter_label and .25 <= t < min(2.3,duration):
        draw = ImageDraw.Draw(image)
        text = chapter_label.upper()
        for size in range(38,23,-2):
            face = caption_font(size)
            width = draw.textlength(text,font=face)
            if width<=550:
                break
        draw.rounded_rectangle((37,24,round(75+width),85),radius=14,fill='#28303c',outline=accent,width=3)
        draw.text((56,54),text,anchor='lm',font=face,fill='#fff6db')
    return image


def cover(plan,target):
    kind = TOPICS[plan['topic']][3]
    digest = hashlib.sha256(plan.get('title',plan['hook']).encode()).digest()
    start,end,earth,peak,accent = PALETTES[kind][digest[0]%2]
    image = Image.new('RGB',SIZE)
    draw = ImageDraw.Draw(image)
    a,b = getrgb(start),getrgb(end)
    for y in range(445):
        draw.line((0,y,1280,y),fill=tuple(round(x+(z-x)*y/444) for x,z in zip(a,b)))
    rng = Random(digest)
    if kind in ('fire','shelter'):
        for _ in range(42):
            x,y = rng.randrange(1280),rng.randrange(167,377)
            draw.ellipse((x,y,x+3,y+3),fill='#deeeff')
        draw.ellipse((1010,155,1122,265),fill='#ffefbe')
    elif kind == 'map':
        draw.ellipse((925,225,1069,369),fill='#ffe665')
    else:
        for x,y in ((82,199),(410,215),(969,187)):
            poly(draw,[(x,y+23),(x+16,y+8),(x+49,y+9),(x+71,y-2),
                       (x+114,y+8),(x+144,y+25),(x+103,y+33),(x+23,y+32)],'#ecf8ff')
    ridgeline = [(x,rng.randrange(284,354)) for x in range(0,1281,160)]
    poly(draw,[*ridgeline,(1280,463),(0,463)],peak)
    ground = [(0,401),(240,388),(550,420),(820,389),(1280,405),(1280,720),(0,720)]
    poly(draw,ground,earth)
    draw.polygon([(0,490),(288,422),(639,441),(820,497),(1280,475),(1280,556),
                  (779,573),(453,523),(0,579)],fill=accent)
    if kind == 'art':
        poly(draw,[(0,157),(258,162),(220,222),(130,335),(97,594),(0,720)],'#4c2941')
        poly(draw,[(1280,143),(1050,163),(1140,294),(1180,557),(1280,720)],'#4c2941')
    elif kind in ('food','map'):
        for x,y in ((77,475),(1190,443)):
            poly(draw,[(x-10,y),(x-3,y-88),(x-52,y-119),(x+7,y-100),
                       (x+58,y-119),(x+14,y-80),(x+10,y)],'#704627')
            poly(draw,[(x-123,y-116),(x-91,y-156),(x-31,y-167),(x+56,y-163),
                       (x+113,y-142),(x+125,y-116),(x+60,y-105)],'#347842')
    elif kind == 'fire':
        for radius,color in ((250,'#9a533f'),(185,'#c36e3f'),(112,'#e79540')):
            draw.ellipse((690-radius,596-radius*.37,690+radius,596+radius*.37),fill=color)
    for _ in range(56):
        x,y = rng.randrange(1280),rng.randrange(509,720)
        size = rng.randrange(5,31)
        draw.polygon([(x,y),(x+size,y-5),(x+int(size*.7),y+3)],fill=accent)
    x,left_scale,left_pose,right,right_scale,right_pose,px,py,prop_scale = STAGING[kind]
    prop(draw,kind,px,py,prop_scale,0,False)
    actor(draw,x,652,t=.35,action=left_pose,female=False,scale=left_scale)
    actor(draw,right,642,t=.4,action=right_pose,female=True,facing=-1,scale=right_scale)
    save_cover(image,plan['hook'],kind,target)


def save_cover(image,hook,kind,target):
    if image.size != SIZE:
        image = image.resize(SIZE,Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(image)
    headline = hook.upper()
    for size in range(138,45,-3):
        face=ImageFont.truetype(str(FONT),size)
        face.set_variation_by_axes([700])
        if draw.textlength(headline,font=face)<1150:
            break
    text_color = '#fff9e8' if kind == 'shelter' else '#ffed33'
    draw.text((645,34),headline,anchor='mt',font=face,fill='#11111b',stroke_width=12)
    draw.text((640,25),headline,anchor='mt',font=face,fill=text_color,stroke_width=8,stroke_fill='#130f17')
    image=image.resize((1920,1080),Image.Resampling.LANCZOS)
    for quality in (93,85,75):
        image.save(target,quality=quality,optimize=True)
        if target.stat().st_size<2*1024**2:
            return
    raise RuntimeError('Prehistory thumbnail exceeds 2 MiB')
