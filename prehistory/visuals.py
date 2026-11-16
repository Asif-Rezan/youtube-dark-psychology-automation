"""Procedural white-stage animation and colorful prehistoric cover artwork."""
from functools import lru_cache
import math
from pathlib import Path
from random import Random

from PIL import Image, ImageDraw, ImageFont

from .character_rig import character
from .editorial import TOPICS


SIZE = (1280,720)
FONT = Path(__file__).resolve().parents[1]/'assets/artwork/Oswald.ttf'
INK = '#292222'
PALETTES = {
    'stone': ('#375d80','#a9cee0','#be945b','#755f59'),
    'fire': ('#403351','#ee8a53','#ad794c','#785262'),
    'map': ('#628cbe','#ffd09b','#bd9b55','#74688a'),
    'food': ('#478db7','#c6e7e4','#b69d58','#657a69'),
    'art': ('#553752','#e2aa78','#b0896e','#6d5260'),
    'shelter': ('#476987','#c7e2df','#b8a777','#777997'),
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
    elif kind == 'shelter':
        shape([(-160,6),(-142,-138),(-62,-222),(46,-229),(136,-167),(171,3)],'#a58675')
        shape([(-67,4),(-64,-60),(-12,-131),(56,-123),(90,-66),(96,4)],'#413746')
        shape([(-142,-137),(-62,-222),(46,-229),(26,-178),(-68,-161)],'#c2a489')
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


def actor(draw,x,y,*,t,action,female=False,facing=1,scale=1.55):
    work = action == 'work'
    character(draw,x,y,scale=scale,female=female,facing=facing,islamic=False,
              walk_phase=t*8 if action in ('walk','carry') else None,
              basket=action=='carry',work=t*7 if work else None,point=action=='show',
              wave=t*4 if action=='react' else None,blink=t%3.9>3.75,
              expression='surprised' if action=='react' else 'curious' if work else 'calm')


@lru_cache(maxsize=12)
def stage(kind):
    image = Image.new('RGB',SIZE,'white')
    draw = ImageDraw.Draw(image)
    draw.polygon([(110,598),(420,549),(835,549),(1168,600),(867,652),(418,650)],fill='#f9f5ee')
    draw.polygon([(420,549),(835,549),(702,586),(312,608),(110,598)],fill='#fbf8f1')
    rng = Random(kind)
    for _ in range(26):
        x,y = rng.randrange(145,1150),rng.randrange(591,623)
        draw.line((x,y,x+rng.randrange(2,17),y-1),fill='#e3d7c7',width=2)
    return image


def scene(beat,t,duration,shot):
    kind,action = beat['prop'],beat['action']
    image = stage(kind).copy()
    draw = ImageDraw.Draw(image)
    actor_x = (350+min(t/max(duration,.1),1)*170 if action in ('walk','carry')
               else 504 if action=='work' else 398)
    prop_x = 603 if action=='work' else 765
    prop_y = 510 if action=='work' and kind in ('stone','food') else 598
    if prop_y < 598:
        poly(draw,[(prop_x-110,600),(prop_x-106,528),(prop_x-63,500),
                   (prop_x+74,502),(prop_x+91,597)],'#bfb4a7')
        poly(draw,[(prop_x-106,528),(prop_x-63,500),(prop_x+74,502),
                   (prop_x+42,526)],'#ded4c9')
    prop(draw,kind,prop_x,prop_y,1.25,t,action=='work')
    draw.ellipse((actor_x-94,605,actor_x+91,627),fill='#e7dfd4')
    actor(draw,actor_x,609,t=t,action=action,female=bool(shot%2),scale=1.55)
    if action in ('show','react') and shot%3==1:
        actor(draw,1010,598,t=t+.7,action='react',female=not bool(shot%2),facing=-1,scale=1.12)
    if action=='work' and t >= duration*.56:
        return image.resize(SIZE,Image.Resampling.BILINEAR,box=(175,57,1095,674))
    return image


def cover(plan,target):
    kind = TOPICS[plan['topic']][3]
    start,end,earth,peak = PALETTES[kind]
    image = Image.new('RGB',SIZE)
    draw = ImageDraw.Draw(image)
    from PIL.ImageColor import getrgb
    a,b = getrgb(start),getrgb(end)
    for y in range(422):
        draw.line((0,y,1280,y),fill=tuple(round(x+(z-x)*y/421) for x,z in zip(a,b)))
    draw.ellipse((688,196,856,364),fill='#ffc970')
    draw.polygon([(0,372),(162,302),(302,343),(461,272),(614,343),(792,285),
                  (940,326),(1104,275),(1280,324),(1280,465),(0,465)],fill=peak)
    draw.polygon([(0,374),(242,404),(525,381),(811,413),(1044,370),(1280,401),
                  (1280,720),(0,720)],fill=earth)
    rng = Random(plan['topic'])
    for _ in range(90):
        x,y=rng.randrange(1280),rng.randrange(426,720)
        size=rng.randrange(6,37)
        draw.polygon([(x,y),(x+size,y-5),(x+int(size*.7),y+3)],fill=rng.choice(('#93704e','#a88455','#b39864')))
    for ax,ay,scale in ((74,467,1.0),(1163,473,.93)):
        trunk = [(ax-8,ay),(ax-3,ay-92*scale),(ax-36,ay-126*scale),(ax-26,ay-131*scale),
                 (ax+6,ay-108*scale),(ax+46,ay-139*scale),(ax+51,ay-130*scale),(ax+20,ay-94*scale),(ax+13,ay)]
        poly(draw,trunk,'#6d513f')
        poly(draw,[(ax-122*scale,ay-112*scale),(ax-95*scale,ay-151*scale),
                   (ax-45*scale,ay-175*scale),(ax+41*scale,ay-178*scale),
                   (ax+91*scale,ay-158*scale),(ax+122*scale,ay-123*scale),
                   (ax+69*scale,ay-115*scale)],'#688052')
    for x,y in ((81,688),(125,628),(1134,678),(1199,623),(1020,715),(352,714)):
        for shift in (-13,0,14):
            draw.polygon([(x+shift,y),(x+shift*2,y-26-abs(shift)),(x+shift+7,y)],fill='#677446')
    prop(draw,kind,654,635,1.52,0,False)
    actor(draw,283,651,t=0,action='show',female=False,scale=1.57)
    actor(draw,984,640,t=.4,action='react',female=True,facing=-1,scale=1.53)
    headline = plan['hook'].upper()
    for size in range(138,45,-3):
        face=ImageFont.truetype(str(FONT),size)
        face.set_variation_by_axes([700])
        if draw.textlength(headline,font=face)<1150:
            break
    draw.text((643,32),headline,anchor='mt',font=face,fill='#211a20',stroke_width=11)
    draw.text((640,25),headline,anchor='mt',font=face,fill='#fff055',stroke_width=8,stroke_fill='#1b171a')
    image=image.resize((1920,1080),Image.Resampling.LANCZOS)
    for quality in (93,85,75):
        image.save(target,quality=quality,optimize=True)
        if target.stat().st_size<2*1024**2:
            return
    raise RuntimeError('Prehistory thumbnail exceeds 2 MiB')
