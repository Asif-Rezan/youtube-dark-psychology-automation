"""Write original rhyme verses with pinned local Qwen; never fall back to templates."""
import hashlib
import json
import re
from pathlib import Path
from lyrics_cpu import MODEL_ID, request_story, StoryGenerationError, LYRIC_WORD_PATTERN

VERSION='qwen-kids-original-v7-episode-hook'
REFRAIN='dudi dudi dam dam dudi dudi dam'
# Legacy fixed chorus (v6 episodes). New episodes get their own hook from Qwen.
CHORUS=(REFRAIN,'clap your hands and dance with me',REFRAIN,'jump up high and spin around')
# Other channels' hooks and our old one: a new episode hook must not sound like them.
BORROWED_HOOKS=('dudi dudi','dodi dodi','duri duri','duty duty','dum dum','dam dam','baby shark','wheels on the bus','twinkle twinkle','old macdonald','johny johny')


def normalized(text):
    return ' '.join(re.findall(r'[a-z]+',text.lower()))


def chorus_line(text, chorus=CHORUS):
    return normalized(text) in {normalized(line) for line in chorus}


def verse_lines(song):
    chorus=song.get('chorus') or CHORUS
    return [normalized(s['lyric']) for s in song['scenes'] if not chorus_line(s['lyric'],chorus)]


def hook_reason(chorus, history=()):
    """A four-line call-and-response hook: line 1 = line 3, short, chantable and new."""
    lines=[normalized(line) for line in chorus]
    if len(lines)!=4 or lines[0]!=lines[2]:
        return 'hook_must_repeat_line_one_as_line_three'
    if any(not 3<=len(line.split())<=8 for line in lines):
        return 'hook_word_count'
    if lines[1]==lines[3]:
        return 'hook_action_lines_identical'
    words=lines[0].split()
    if len(set(words))>len(words)-1:
        return 'hook_needs_repeated_sound'
    if any(borrowed in ' '.join(lines) for borrowed in BORROWED_HOOKS):
        return 'borrowed_hook'
    for entry in history[-30:]:
        if normalized(entry.get('hook',''))==lines[0]:
            return 'repeated_hook'
    return None


def novelty_reason(lines, history):
    """Ignore the intentionally shared refrain, compare real verse content."""
    if len(set(lines)) != len(lines):
        return 'repeated_verse_in_episode'
    def grams(items):
        return {tuple(words[i:i+4]) for line in items for words in [line.split()] for i in range(len(words)-3)}
    current=grams(lines)
    for entry in history:
        previous=entry.get('verse_lines',[])
        if not previous:
            continue
        if set(lines)==set(previous):
            return 'duplicate_verses'
        old=grams(previous)
        if current and old and len(current & old)/min(len(current),len(old)) > .35:
            return 'similar_verses'
    return None


def request_json(schema, prompt, seed, budget=2600):
    payload={'model':MODEL_ID,'temperature':.85,
        'max_completion_tokens':budget,
        'bounded_metadata_fields':['description','title','characters','visual_world'],
        'messages':[{'role':'system','content':'You write original, gentle, joyful English nursery rhymes for ages 2-6. Return the requested JSON only. Never reuse a stock verse or a known song.'},
                    {'role':'user','content':prompt}],
        'response_format':{'type':'json_schema','json_schema':{'name':'kids_rhyme','schema':schema}}}
    for attempt in range(3):
        payload['seed']=(seed + attempt * 7919) % (2**31 - 2)
        try:
            response=request_story('chat/completions',payload)
            return json.loads(response['choices'][0]['message']['content'])
        except StoryGenerationError as error:
            if not error.retryable or attempt == 2:
                raise
            # No raw generated content or credentials in diagnostics. Completed
            # chapters and accepted verse repairs remain in the saved draft.
            print(json.dumps({'phase':'retry rhyme model request',
                'attempt':attempt+1,'error_code':error.code}),flush=True)


def write_rhyme(day, identity, seconds, history, draft_path=None, verse_count=None):
    path=Path(draft_path) if draft_path else None
    state=json.loads(path.read_text()) if path and path.exists() else {}
    if state and (state.get('writer_version'),state.get('run_id'),state.get('duration')) != (VERSION,identity,seconds):
        raise ValueError('Saved draft uses another identity or writer; start a fresh run ID')
    def save():
        if path:
            path.parent.mkdir(parents=True,exist_ok=True)
            temp=path.with_suffix('.tmp')
            temp.write_text(json.dumps(state,ensure_ascii=False,indent=2))
            temp.replace(path)
    base=int(hashlib.sha256(identity.encode()).hexdigest()[:8],16)%(2**31-10000)
    if verse_count is not None and not 4<=verse_count<=60:
        raise ValueError('verse_count must be 4-60 lines')
    chapters=(verse_count+11)//12 if verse_count else (seconds+119)//120
    def chapter_lines(chapter):
        if verse_count:
            return min(12,verse_count-chapter*12)
        return min(12,(seconds-chapter*120+9)//10)
    recent=[{'title':h.get('title',''),'story':h.get('story_summary',''),'visual_identity':h.get('visual_identity',{})} for h in history[-12:]]
    outline_schema={'type':'object','additionalProperties':False,'required':['title','story_summary','description','chapters','characters','visual_world'],
        'properties':{'characters':{'type':'string','minLength':20,'maxLength':320},
        'visual_world':{'type':'string','minLength':20,'maxLength':240},
        'title':{'type':'string','minLength':8,'maxLength':65},
        'story_summary':{'type':'string','minLength':40,'maxLength':400},
        'description':{'type':'string','minLength':80,'maxLength':650},
        'chapters':{'type':'array','minItems':chapters,'maxItems':chapters,'items':{'type':'string','minLength':20,'maxLength':180}},
        'chorus':{'type':'array','minItems':4,'maxItems':4,'items':{'type':'string','minLength':10,'maxLength':60,'pattern':LYRIC_WORD_PATTERN}}}}
    outline_schema['required'].append('chorus')
    hooks=[h.get('hook','') for h in history[-30:] if h.get('hook')]
    # If a complete candidate is too similar, rewrite it with another seed.
    for attempt in range(state.get('attempt',0),3):
        if not state.get('outline'):
            state=dict(writer_version=VERSION,run_id=identity,duration=seconds,attempt=attempt,sections=[])
            save()  # Preserve identity and retry state even if the first response fails.
            state['outline']=request_json(outline_schema,
                f'Create a NEW {seconds//60}-minute nursery rhyme episode for Dudi Dam TV on {day}. '
                f'Creative identity {identity}; variation {attempt}. Invent a distinct adventure and choose a NEW cast led by one or two adorable baby animals with rounded soft bodies, expressive eyes, appealing pastel colors and distinct cute features. Add two cute human toddlers aged 2-4 in colorful clothes as equally visible playmates. Every scene must include both human babies and animals together, never only an animal. Preserve the soft, whimsical animal-story atmosphere. Vary animal species and the child appearance and clothing between episodes. '
                f'Write {chapters} connected chapter ideas with a beginning, discoveries and a happy ending. '
                'Keep characters under 320 characters and visual_world under 240 characters, including spaces. '
                'characters must describe one or two cute baby animal protagonists plus two cute human toddler playmates, with names, species, pastel colors, distinctive animal features and the toddlers clothing, kept consistent throughout this episode. '
                'visual_world must describe a natural dreamy outdoor setting: a flower meadow, blossom garden, forest, stream or soft cloud landscape, with lush plants, gentle natural light and a pastel palette. Never use a plain studio backdrop, stage or empty white room. Vary the cast and natural world from recent episodes. '
                'Teach gentle movement, kindness, colors or nature through concrete playful actions. '
                'English title must name the actual new adventure, not a run ID. Write a concise 2-3 sentence description, 40-65 words and under 600 characters, describing this particular story. '
                'Avoid scary situations, danger, commercial brands, adult themes, requests to subscribe and copying existing songs. '
                'chorus is this episode\'s OWN catchy dance hook, sung four times as often as any verse, so toddlers chant it after one listen. '
                'Exactly 4 lines of 3-8 words: line 1 is a playful repeated nonsense or animal sound phrase that fits this cast and story '
                '(examples of the pattern only, never copy them: "boing boing boing boing bouncy bee", "splishy splashy splishy splash"), '
                'line 2 a simple dance action, line 3 identical to line 1, line 4 a different dance action. '
                'Bouncy trochaic rhythm with strong beats, easy to clap to. Never reuse another song\'s hook or these recent hooks: '+json.dumps(hooks)+'. '
                'Do not repeat these recent titles or story premises: '+json.dumps(recent),base+attempt*100)
            for fix in range(3):
                reason=hook_reason(state['outline']['chorus'],history)
                if not reason:
                    break
                print(json.dumps({'phase':'repair episode hook','attempt':fix+1,'reason':reason}),flush=True)
                state['outline']['chorus']=request_json(
                    {'type':'object','additionalProperties':False,'required':['chorus'],'properties':{'chorus':outline_schema['properties']['chorus']}},
                    'Rewrite only the 4-line dance chorus for this kids episode: '+json.dumps(state['outline'])+
                    f'. Problem to fix: {reason}. Rules: 3-8 words per line; line 1 a fun repeated sound phrase (some word repeated) '
                    'matching the cast; line 2 a dance action; line 3 exactly equal to line 1; line 4 a different dance action. '
                    'No existing song hooks and none of: '+json.dumps(hooks+list(BORROWED_HOOKS)),
                    base+attempt*100+fix+1)['chorus']
            else:
                raise StoryGenerationError('Qwen episode hook repair exhausted',code='lyrics_hook_validation',retryable=True,
                    details={'reason':reason})
            save()
        outline=state['outline']
        prior=[row['lyric'] for section in state['sections'] for row in section]
        for chapter in range(len(state['sections']),chapters):
            count=chapter_lines(chapter)
            schema={'type':'object','additionalProperties':False,'required':['verses'],'properties':{
                'verses':{'type':'array','minItems':count,'maxItems':count,'items':{
                    'type':'object','additionalProperties':False,'required':['lyric','visual'],
                    'properties':{'lyric':{'type':'string','minLength':10,'maxLength':100,'pattern':LYRIC_WORD_PATTERN},
                                  'visual':{'type':'string','minLength':15,'maxLength':180}}}}}}
            # Keep useful model output; only ask again for rejected/missing lines.
            pending=state.get('pending',{})
            rows=list(pending.get('rows',[])) if pending.get('chapter')==chapter else []
            feedback=pending.get('feedback',[]) if pending.get('chapter')==chapter else []
            rejected=pending.get('rejected',[]) if pending.get('chapter')==chapter else []
            repair_round=pending.get('repair_round',0) if pending.get('chapter')==chapter else 0
            for retry in range(6):
                remaining=count-len(rows)
                if not remaining:
                    break
                schema['properties']['verses']['minItems']=remaining
                schema['properties']['verses']['maxItems']=remaining
                block=request_json(schema,
                    f'Write exactly {remaining} NEW short English sung lines for chapter {chapter+1}/{chapters} of this original episode: '
                    +json.dumps(outline)+'. Current chapter: '+outline['chapters'][chapter]+'. '
                    'Each line occupies five seconds: aim for 4-8 simple singable words, NEVER more than 12. Use single spaces and plain English words without apostrophes or hyphens. Count words before returning JSON. '
                    'The arranger groups your lines into four-line verses, each followed by a dance chorus: '
                    +json.dumps(outline['chorus'])+'. Do not put any chorus line in your output; the arranger inserts it. '
                    'Make every four consecutive lines a small complete verse that rhymes or repeats a fun sound. '
                    'Every verse line must be different. Develop this chapter rather than repeating earlier verses. '
                    'For each line, visual describes the same action and setting, featuring the episode characters with their exact appearance from the outline. Describe BOTH human toddlers and cute baby animals at the beginning of every visual. Keep both babies and animals equally prominent with separate full bodies, hands and feet visible, playing or dancing together. Never describe a solo animal composition. Alternate playful dancing, waving and little steps with concrete animal-led discoveries; do not make every scene jump. Name the visible subjects, action, relevant props and setting explicitly. Describe one small event: noticing something, reacting, approaching it and sharing a happy response. Avoid static posing. Use varied dance poses and playful actions rather than repeating one pose. Match the lyric literally where possible, and vary locations as the chapter develops. '
                    'It is a text-free cartoon picture prompt, with no camera instructions or lettering. '
                    'Previous lines to avoid repeating: '+json.dumps(prior+[row['lyric'] for row in rows])+
                    '. Fix these rejected-line constraints: '+json.dumps(feedback)+
                    '. Rewrite only these rejected candidates when supplied, preserving their action and visual meaning: '+json.dumps(rejected)+
                    f'. Rewrite attempt {retry}.',
                    (base+attempt*10000+chapter*1000+repair_round+retry+1) % (2**31-1))
                seen={normalized(line) for line in prior+[row['lyric'] for row in rows]}
                feedback=[]
                rejected=[]
                for index,row in enumerate(block['verses']):
                    line=normalized(row['lyric'])
                    words=len(line.split())
                    reason=('word_count' if not 4<=words<=12 else
                            'reserved_refrain' if chorus_line(line,outline['chorus']) else
                            'duplicate_line' if line in seen else None)
                    if reason:
                        rejected.append({'lyric':row['lyric'],'visual':row['visual']})
                        feedback.append({'line':index+1,'reason':reason,'word_count':words,
                                         'minimum_words':4,'maximum_words':12})
                    elif len(rows)<count:
                        rows.append(row)
                        seen.add(line)
                state['pending']={'chapter':chapter,'rows':rows,'feedback':feedback,'rejected':rejected,
                                  'repair_round':repair_round+retry+1}
                save()
                if len(rows)==count:
                    break
                print(json.dumps({'phase':'repair verse lines','chapter':chapter+1,
                    'attempt':retry+1,'accepted_lines':len(rows),'required_lines':count,
                    'rejections':feedback}),flush=True)
            else:
                raise StoryGenerationError('Qwen verse repair exhausted; resume this run to keep accepted lines',
                    code='lyrics_verse_validation',retryable=True,
                    details={'chapter':chapter+1,'accepted_lines':len(rows),'required_lines':count,
                             'attempts':6,'rejections':feedback})
            state.pop('pending',None)
            state['sections'].append(rows)
            prior.extend(row['lyric'] for row in rows)
            save()
            print(json.dumps({'phase':'original AI verses written','chapter':chapter+1,'chapters':chapters,'verse_lines':len(prior)}),flush=True)
        reason=novelty_reason([normalized(line) for line in prior],history)
        characters = normalized(outline.get('characters', ''))
        if characters and any(characters == normalized(h.get('visual_identity', {}).get('characters', ''))
                              for h in history[-12:]):
            reason = 'repeated_episode_cast'
        if not reason and not any(h.get('title')==outline['title'] for h in history):
            state['novelty_checked']=True
            save()
            return state
        print(json.dumps({'phase':'rewrite non-original lyrics','reason':reason or 'duplicate_title','attempt':attempt+1}),flush=True)
        state=dict(writer_version=VERSION,run_id=identity,duration=seconds,attempt=attempt+1,sections=[])
        save()
    raise StoryGenerationError('Original rhyme validation failed; template fallback is disabled')
