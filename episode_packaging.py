"""Original story-grounded public metadata from the existing local Qwen model."""
import hashlib
import json
from jsonschema import Draft202012Validator, ValidationError

VERSION = 'episode-seo-packaging-v2-opening-thumbnail'
# Titles that imitate other channels' songs attract viewers who expect that song.
LOOKALIKE_TITLES = ('dodi dodi','duri duri','duty duty','dum dum')


def metadata_schema():
    return {'type':'object','additionalProperties':False,'required':['title','description','tags'],
        'properties':{'title':{'type':'string','minLength':10,'maxLength':100},
                      'description':{'type':'string','minLength':80,'maxLength':1800},
                      'tags':{'type':'array','minItems':5,'maxItems':15,'uniqueItems':True,
                              'items':{'type':'string','minLength':2,'maxLength':40}}}}


def candidate_scenes(song):
    count=len(song['scenes'])
    indexes=set(range(min(8,count)))
    if count>8:
        indexes.update(8+i*(count-9)//15 for i in range(16))
    return [song['scenes'][i] for i in sorted(indexes)]


def thumbnail_scenes(song):
    # Verse-chorus episodes open on the thumbnail scene, so the first frames match the click.
    if song.get('song_form'):
        return [0]
    return [s['index'] for s in candidate_scenes(song)]


def chapter_text(song):
    """Real YouTube chapters from the storyboard sections (each at least 20 seconds)."""
    rows,verse=[],0
    scenes=song.get('scenes',[])
    for i,scene in enumerate(scenes):
        section=scene.get('section')
        if not section or (i and scenes[i-1].get('section')==section):
            continue
        if section=='verse':
            verse+=1
            words=' '.join(scene['lyric'].split()[:6]).rstrip('.!?')
            rows.append(f"{scene['start']//60}:{scene['start']%60:02d} Verse {verse}: {words[:1].upper()+words[1:]}")
        elif not rows:
            hook=song.get('hook') or 'Dudi Dudi Dam Dam'
            rows.append('0:00 '+hook[:1].upper()+hook[1:].rstrip('.!?')+' dance chorus')
    return '\n'.join(rows) if len(rows)>=3 else ''


def add_chapters(package, song):
    chapters=chapter_text(song)
    video=package.get('video')
    if not chapters or not isinstance(video,dict) or not isinstance(video.get('description'),str):
        return package
    if chapters in video['description']:
        return package
    room=1800-len(chapters)-2
    body=video['description'][:room].rstrip()
    video['description']=body+'\n\n'+chapters
    return package


def schema(song):
    return {'type':'object','additionalProperties':False,
        'required':['title_candidates','video','shorts','thumbnail'],
        'properties':{
            'title_candidates':{'type':'array','minItems':3,'maxItems':3,'uniqueItems':True,
                                'items':{'type':'string','minLength':10,'maxLength':100}},
            'video':metadata_schema(),'shorts':metadata_schema(),
            'thumbnail':{'type':'object','additionalProperties':False,'required':['scene_index','focus'],
                         'properties':{'scene_index':{'type':'integer','enum':thumbnail_scenes(song)},
                                       'focus':{'type':'string','minLength':15,'maxLength':180}}}}}


def source_identity(song):
    return hashlib.sha256(json.dumps({k:song.get(k) for k in
        ('title','description','lyrics','story_summary','visual_identity','scenes','duration')},
        sort_keys=True).encode()).hexdigest()


def validate_package(package, song):
    content={k:package[k] for k in ('title_candidates','video','shorts','thumbnail')}
    Draft202012Validator(schema(song)).validate(content)
    if package.get('version') != VERSION or package.get('source_sha256') != source_identity(song):
        raise ValueError('Episode packaging source/version mismatch')
    if content['video']['title'] not in content['title_candidates']:
        raise ValueError('Selected title must be one of the episode candidates')
    for kind in ('video','shorts'):
        tags=content[kind]['tags']
        if len({tag.strip().casefold() for tag in tags})!=len(tags) or sum(len(t)+2 for t in tags)>450:
            raise ValueError('Episode tags must be unique and fit the upload budget')
    return package


TAG_BUDGET = 450


def lookalike(title):
    return isinstance(title,str) and any(word in title.casefold() for word in LOOKALIKE_TITLES)


def repair_package(package, recent=()):
    """Fix deterministic slips locally instead of re-asking the model.

    Only reorders or drops model-written values; never invents public text.
    """
    for kind in ('video','shorts'):
        meta=package.get(kind)
        if not isinstance(meta,dict) or not isinstance(meta.get('tags'),list):
            continue
        seen,tags,used=set(),[],0
        for tag in meta['tags']:
            if not isinstance(tag,str):
                continue
            tag=' '.join(tag.split())
            key=tag.casefold()
            if not tag or key in seen or used+len(tag)+2>TAG_BUDGET:
                continue
            seen.add(key);tags.append(tag);used+=len(tag)+2
        meta['tags']=tags
    candidates=package.get('title_candidates')
    video=package.get('video')
    if isinstance(candidates,list) and isinstance(video,dict):
        title=video.get('title')
        if title not in candidates or title in recent or lookalike(title):
            fresh=[c for c in candidates if isinstance(c,str) and c not in recent and not lookalike(c)]
            if fresh:
                video['title']=fresh[0]
    return package


def packaging_issue(error):
    """Safe diagnostic: locally authored messages, or schema location only."""
    if isinstance(error,ValidationError):
        return {'constraint':error.validator,'path':[str(p) for p in error.absolute_path]}
    if isinstance(error,KeyError):
        return {'constraint':'missing_field'}
    return {'constraint':'semantic','reason':str(error)}


def generate_package(song, history=(), seed_offset=0):
    from rhyme_writer import request_json
    from lyrics_cpu import StoryGenerationError
    identity=source_identity(song)
    facts={k:song.get(k) for k in ('title','description','story_summary','visual_identity','duration')}
    from rhyme_writer import chorus_line, CHORUS
    chorus=song.get('chorus') or list(CHORUS)
    facts['verse_lyrics']=[s['lyric'] for s in song['scenes'] if not chorus_line(s['lyric'],chorus)]
    facts['chorus']=chorus
    facts['scenes']=[dict(index=s['index'],lyric=s['lyric'],action=s.get('visual_action',s['prompt'])[:180]) for s in candidate_scenes(song)]
    prompt=(
        'Create an original truthful YouTube title/thumbnail package for this English kids nursery rhyme. '
        'Use only the supplied lyrics, cast, setting and actions. No invented animals, lessons, events, '
        'educational guarantees, views, popularity, trend/search-volume claims or celebrity/cartoon brands. '
        'The sung chorus hook is this episode\'s own and may appear in the title. Public metadata must differ between episodes. '
        'SEO title rules: write three distinct title candidates of 45-70 characters. Start with the main '
        'search phrase parents type, built from the real animal and action, e.g. "Baby Bunny Dance Song for Kids". '
        'Then a pipe and a broad phrase such as Nursery Rhymes, Kids Songs or Toddler Dance, optionally '
        '"| Dudi Dam TV" at the end. Never use other channels\' song names or sound-alikes such as '
        'Dodi Dodi, Duri Duri, Duty Duty or Dum Dum. No ALL CAPS, emoji spam or clickbait. Choose the '
        'strongest honest title-thumbnail pair for video.title, exactly one of title_candidates. '
        'SEO description rules: the first 150 characters repeat the main search phrase naturally and say '
        'what children see and do; then 2-4 short sentences summarizing the real story, cast and dance moves, '
        'a line that music and illustrations are AI-made, and finally exactly three relevant hashtags such as '
        '#KidsSongs #NurseryRhymes and one animal hashtag. Do not write timestamps; real chapters are added. '
        'No unrelated song names, subscription requests, keyword lists or spam. '
        'Generate 8-15 distinct tags: the main search phrase, animal plus song/dance variants, toddler and '
        'nursery rhyme terms, and Dudi Dam TV; each at most 40 characters, combined under 450 characters. '
        'For shorts, write a separate title, description and tags based ONLY on scenes 0-7 (first 40 seconds), '
        'not later events. A short may use #Shorts once. '
        'For thumbnail, use scene_index 0 when it is the only allowed value: the video opens on that exact '
        'dance scene, so the thumbnail must show the same cast, setting, lighting and colors. '
        'Write a compact focus describing the existing characters/emotion and real prop/action to emphasize; '
        'do not introduce a new cast, outfit, environment or disconnected disco-party scene. '
        'Aim for readable large faces, clear silhouettes, one focal interaction, color contrast and simple '
        'composition at mobile size. Keep the same soft cute 3D storybook style and dreamy natural scene, '
        'no text, logos or split panels. Do not claim a numerical CTR score. '
        'Avoid these recent public titles: '+json.dumps([h.get('public_title',h.get('title','')) for h in history[-20:]])+
        '\nActual episode: '+json.dumps(facts,ensure_ascii=False))
    recent={h.get('public_title',h.get('title','')) for h in history}
    # Stage-level retries pass a new offset so they don't replay identical seeds.
    base=(int(identity[:8],16)+seed_offset*104729) % (2**31-10000)
    for attempt in range(3):
        result=request_json(schema(song),prompt,base+attempt,budget=2800)
        result.update(version=VERSION,source_sha256=identity)
        try:
            repair_package(result,recent)
            validate_package(result,song)
            if result['video']['title'] in recent:
                raise ValueError('Public title repeats an earlier episode')
            for kind in ('video','shorts'):
                if lookalike(result[kind]['title']):
                    raise ValueError('Title imitates another channel song name; use this episode story')
            add_chapters(result,song)
            return result
        except (ValueError,KeyError,ValidationError) as error:
            print(json.dumps({'check':'episode packaging retry','attempt':attempt+1,
                **packaging_issue(error)}),flush=True)
            prompt += '\nRepair the package: '+str(error)
    raise StoryGenerationError('Episode packaging validation exhausted; saved lyrics retained',
                               code='episode_packaging',retryable=True)


def public_metadata(song, kind='video'):
    """New episodes use their saved package; old unpublished artifacts use their story."""
    if kind not in ('video','shorts'):
        raise ValueError('Unknown upload format')
    if song.get('public_metadata_version') == VERSION:
        return {key:song[key] for key in ('title','description','tags')}
    package=song.get('packaging')
    if package:
        validate_package(package,song)
        return dict(package[kind],tags=list(package[kind]['tags']))
    # Recovery compatibility: never revert an old prepared song to shared fixed text.
    from kids_rhymes import metadata_tags, upload_description
    return dict(title=song['title'],description=upload_description(song),tags=metadata_tags(song))
