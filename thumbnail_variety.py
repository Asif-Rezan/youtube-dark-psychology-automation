"""Durable thumbnail rotation, topic composition and bounded duplicate rejection."""
import hashlib
import json
import re
from pathlib import Path
import numpy as np
from PIL import Image

VERSION='thumbnail-variety-v1'
HISTORY_KEY='thumbnail-history.json'
LAYOUTS=(
    'Close-up: one clothed toddler left, one baby bunny right, one flower between them.',
    'Two baby animals foreground, one giant flower, two clothed toddlers small in the background.',
    'Low angle: one clothed toddler and one baby bunny along a diagonal adventure path.',
    'Overhead view: three cute friends forming a semicircle around one giant toy.',
    'One clothed toddler right, pointing at a giant colorful prop left, one puppy companion.',
)
PALETTES=('turquoise and sunny yellow','lavender and peach','coral and sky blue','mint and warm pink','golden orange and soft blue')


def topic_for(song):
    text=(song.get('title','')+' '+song.get('story_summary','')).lower()
    for terms,topic in [(('rain','puddle','splash'),'rain puddles, a little umbrella and sparkling water'),
                        (('flower','garden','plant','daisy'),'bright flowers, watering can and a tiny garden'),
                        (('rainbow','color'),'a bold rainbow arch and colorful stepping stones'),
                        (('sleep','moon','night'),'a crescent moon, soft stars and a cozy bedtime cloud'),
                        (('dance','party','music'),'colorful musical notes, a small toy drum and a dance floor'),
                        (('sea','ocean','beach'),'seashells, a sandcastle and gentle seaside waves')]:
        if any(re.search(r'\b'+re.escape(term)+r'(?:s|es|ing|y)?\b',text) for term in terms):
            return topic
    return 'a joyful friendship adventure with a colorful toy'


def next_design(song,run_id,history):
    existing=next((row for row in history if row['run']==run_id),None)
    if existing and existing.get('design'):
        return existing['design']
    def oldest(field,count):
        last={i:-1 for i in range(count)}
        for index,row in enumerate(history):
            value=row.get('actual_'+field,row.get('design',{}).get(field))
            if value in last:last[value]=index
        return min(last,key=lambda i:(last[i],i))
    return dict(version=VERSION,run=run_id,reference_index=oldest('reference_index',5),
                layout_index=oldest('layout_index',len(LAYOUTS)),palette_index=oldest('palette_index',len(PALETTES)),
                topic=topic_for(song),prior_signatures=[row['signature'] for row in history if 'signature' in row][-10:])


def seed_existing(history,published,store):
    """Import accessible old thumbnails so similarity checks cover existing uploads too."""
    import io
    import re
    import requests
    import tempfile
    for entry in published[-10:]:
        run_id=entry.get('run')
        video_id=entry.get('video_id','')
        if not run_id or any(row['run']==run_id for row in history):continue
        row=dict(run=run_id,legacy=True)
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'previous.jpg'
            file_id=store.find(f'runs/{run_id}/thumbnail.jpg')
            if file_id:
                store.download(file_id,target)
            elif re.fullmatch(r'[a-zA-Z0-9_-]{11}',video_id):
                for quality in ('maxresdefault','hqdefault'):
                    try:
                        response=requests.get(f'https://i.ytimg.com/vi/{video_id}/{quality}.jpg',timeout=15)
                        if response.status_code!=200:continue
                        image=Image.open(io.BytesIO(response.content))
                        if image.width<320:continue
                        image.convert('RGB').save(target)
                        break
                    except (requests.RequestException,OSError):continue
            if target.exists():row['signature']=fingerprint(target)
        history.append(row)
    return history


def reserve_design(song,run_id,store,published=None):
    # Generation workflows share the existing dudi-dam-tv-publish concurrency lock.
    history=store.load(HISTORY_KEY,[])
    before=json.dumps(history,sort_keys=True)
    if published:seed_existing(history,published,store)
    design=next_design(song,run_id,history)
    if song.get('thumbnail_design') and song['thumbnail_design']!=design:
        raise ValueError('Saved thumbnail design conflicts with its durable run reservation')
    row=next((row for row in history if row['run']==run_id),None)
    if row is None:
        history.append(dict(run=run_id,design=design))
    else:
        row['design']=design
    if before!=json.dumps(history,sort_keys=True):
        store.save(HISTORY_KEY,history)
    song['thumbnail_design']=design
    return design


def prompt_for(song,design,attempt=0):
    layout=LAYOUTS[(design['layout_index']+attempt)%len(LAYOUTS)]
    palette=PALETTES[(design['palette_index']+attempt)%len(PALETTES)]
    return ('Cute 3D storybook nursery cartoon. '+layout+' '+design['topic']+'. '+
            palette+' colors. Happy expressive faces, colorful rompers, soft light, clear silhouettes. '
            'No text or logos.')



def fingerprint(path):
    with Image.open(path) as source:
        image=source.convert('RGB')
        small=np.asarray(image.resize((9,8)).convert('L'),dtype=np.int16)
        bits=(small[:,1:]>small[:,:-1]).flatten()
        dhash=sum(int(bit)<<i for i,bit in enumerate(bits))
        colors=np.asarray(image.resize((4,4)),dtype=np.uint8).flatten().tolist()
    return dict(dhash=f'{dhash:016x}',colors=colors)


def similar(signature,previous):
    for other in previous:
        distance=(int(signature['dhash'],16)^int(other['dhash'],16)).bit_count()
        color_distance=float(np.abs(np.array(signature['colors'],dtype=float)-np.array(other['colors'],dtype=float)).mean())
        if distance<=8 and color_distance<=18:
            return True
    return False


def reference_colors(path):
    """Use a reference's colors without copying its people or composition."""
    import colorsys
    with Image.open(path) as image:
        small=image.convert('RGB').resize((64,64)).quantize(colors=8)
        palette=small.getpalette()
        names=[]
        for _,index in sorted(small.getcolors(),reverse=True):
            r,g,b=palette[index*3:index*3+3]
            hue,saturation,value=colorsys.rgb_to_hsv(r/255,g/255,b/255)
            if saturation<.3 or value<.3:continue
            name=('coral','orange','yellow','green','turquoise','blue','purple','pink')[int(hue*8)%8]
            if name not in names:names.append(name)
            if len(names)==2:break
    return ' and '.join(names)


def generate_distinct(target,plan,song,generate,options):
    design=song['thumbnail_design']
    options=dict(options)
    if plan.get('conditioning')=='palette-style-only':
        # Do not feed the old character layout into img2img. Use its palette as a style cue.
        reference=options.pop('reference_image',None)
        options.pop('strength',None)
        if reference:
            palette=reference_colors(reference)
        else:
            palette=''
    else:
        palette=''
    for attempt in range(3):
        prompt=prompt_for(song,design,attempt)
        if palette:prompt += ' Accent colors: '+palette+'.'
        seed=plan['seed']+attempt*104729
        generate(prompt,target,seed=seed,allow_text=False,width=plan['width'],height=plan['height'],steps=plan['steps'],**options)
        signature=fingerprint(target)
        if not similar(signature,design.get('prior_signatures',[])):
            receipt=dict(version=VERSION,run=design['run'],design=design,attempt=attempt,
                         prompt=prompt,seed=seed,signature=signature,source_sha256=hashlib.sha256(Path(target).read_bytes()).hexdigest())
            Path(target).parent.joinpath('thumbnail-design.json').write_text(json.dumps(receipt,indent=2))
            return
    Path(target).unlink(missing_ok=True)
    raise RuntimeError('Thumbnail too similar to recent thumbnails after three compositions; refusing repeated artwork')


def record_thumbnail(store,root,run_id):
    receipt=Path(root)/'thumbnail-design.json'
    if not receipt.exists():return  # Legacy episodes retain their existing publication flow.
    data=json.loads(receipt.read_text())
    history=store.load(HISTORY_KEY,[])
    row=next((row for row in history if row['run']==run_id),None)
    if row is None:
        row=dict(run=run_id,design=data['design']);history.append(row)
    row['signature']=data['signature']
    row['source_sha256']=data['source_sha256']
    row['actual_layout_index']=(data['design']['layout_index']+data['attempt'])%len(LAYOUTS)
    row['actual_palette_index']=(data['design']['palette_index']+data['attempt'])%len(PALETTES)
    store.save(HISTORY_KEY,history)
