"""Plan evidence-led prehistoric explainers with the project's existing Qwen runtime."""
import hashlib
import json
import re

from lyrics_cpu import StoryGenerationError, request_story


TOPICS = {
    'stone-tools': ('Early Stone Tools', 'https://humanorigins.si.edu/evidence/behavior/stone-tools',
        'Early toolkits included hammerstones, cores and sharp flakes. Acheulean handaxes appeared later. '
        'Toolmakers cannot always be assigned to a particular species.', 'stone', 'WHAT DID IT CUT?'),
    'hearths': ('Life Around the First Hearths', 'https://humanorigins.si.edu/evidence/behavior/hearths-shelters',
        'Controlled fire offered light, warmth and cooking. Charred evidence can be difficult to interpret. '
        'A hearth is also a place where people may have gathered.', 'fire', 'AFTER DARK?'),
    'origins': ('The African Origins of Homo Sapiens', 'https://humanorigins.si.edu/evidence/human-fossils/species/homo-sapiens',
        'Homo sapiens evolved in Africa about 300,000 years ago. Fossils and artifacts preserve different evidence. '
        'Avoid a single birthplace or simple one-cause account.', 'map', 'WHY THERE?'),
    'food': ('How Early Humans Found Food', 'https://humanorigins.si.edu/human-characteristics/tools-food',
        'Food came from varied plants and animals; stone tools leave evidence of processing, and controlled fire changed cooking possibilities. '
        'Availability varied with season and place.', 'food', 'WHAT WAS DINNER?'),
    'symbols': ('Why Early Humans Made Symbols', 'https://humanorigins.si.edu/evidence/behavior',
        'Material evidence includes ornaments, marks and art. A surviving mark can be studied even when its exact meaning is unknown. '
        'Distinguish ornaments from cave paintings.', 'art', 'WHAT DID IT MEAN?'),
    'shelter': ('How Early Humans Found Shelter', 'https://humanorigins.si.edu/evidence/behavior/hearths-shelters',
        'Natural shelters and built structures were both used. Preservation of organic materials is uneven. '
        'Distinguish archaeological observations from modern reconstructions.', 'shelter', 'WHERE DID THEY SLEEP?'),
}
ACTIONS = ('show','walk','carry','work','react','gather','share','watch')
SETTINGS = ('workshop','camp','grassland','cave','journey')
PROPS = ('stone','fire','map','food','art','shelter')
CHAPTER_COUNT = 20
BEAT_WORDS = (27, 56)
CHAPTER_MIN_WORDS = 108
STR = {'type':'string'}


def object_schema(**fields):
    return {'type':'object','properties':fields,'required':list(fields),'additionalProperties':False}


def array(items,n):
    return {'type':'array','items':items,'minItems':n,'maxItems':n}


def choice(values):
    return {'type':'string','enum':list(values)}


CAST_MEMBER = object_schema(
    sex=choice(('male','female')), action=choice(ACTIONS),
    position=choice(('left','center','right')),
)
BEAT = object_schema(
    narration=STR, prop=choice(PROPS), setting=choice(SETTINGS),
    secondary_prop=choice((*PROPS,'none')),
    framing=choice(('wide','medium','detail')),
    cast={'type':'array','items':CAST_MEMBER,'minItems':1,'maxItems':3},
)
CHAPTER = object_schema(label=STR,beats=array(BEAT,3))


def ask(message,schema,seed):
    response = request_story('chat/completions',{
        'messages':[{'role':'user','content':message}],
        'response_format':{'type':'json_schema','json_schema':{'schema':schema}},
        'seed':seed,'max_completion_tokens':4300,
    })
    return json.loads(response['choices'][0]['message']['content'])


def generate(run_id,history,checkpoint=None,save_checkpoint=None):
    used = [row.get('prehistory_topic') for row in history]
    last_seen = {item:i for i,item in enumerate(used) if item in TOPICS}
    oldest = sorted(TOPICS,key=lambda key:last_seen.get(key,-1))[:3]
    topic_names = {key:TOPICS[key][0] for key in oldest}
    idea_schema = object_schema(topic={'type':'string','enum':oldest},title=STR,hook=STR,
                                description=STR,tags=array(STR,6),angle=STR)
    seed = int.from_bytes(hashlib.sha256(run_id.encode()).digest()[:4],'big') % 1_900_000_000
    titles = {row.get('title','').casefold() for row in history}
    checkpoint = checkpoint or {}
    save_checkpoint = save_checkpoint or (lambda value: None)
    if 'idea' in checkpoint:
        idea = checkpoint['idea']
        title = idea['title']
    else:
        for attempt in range(4):
            idea = ask(f'Choose one prehistoric human topic from {topic_names}. Write an original English YouTube '
                       'documentary idea. The title is an inviting specific question of 30–75 characters. '
                       'The thumbnail hook is a different question, 2–5 uppercase words, max 26 characters. '
                       'Write a short description teasing the discovery, and exactly six relevant search tags. '
                       f'Avoid these previous titles: {[row.get("title","") for row in history[-20:]]}.',idea_schema,seed+attempt*5)
            title = ' '.join(idea['title'].split())
            if (30 <= len(title) <= 75 and title.endswith('?') and title.casefold() not in titles
                    and not re.search('[<>]',title)):
                break
        else:
            raise StoryGenerationError('No original prehistory title after four attempts',code='prehistory_idea')
        idea = {**idea,'title':title}
        save_checkpoint({'idea':idea,'chapters':[]})
    topic = idea['topic']
    subject,source,facts,prop,fallback = TOPICS[topic]
    hook = ' '.join(idea['hook'].upper().split())
    if not (2 <= len(hook.split()) <= 5 and re.fullmatch(r'[A-Z0-9 ]{3,25}\?',hook)
            and hook.casefold().rstrip('?') not in title.casefold()):
        hook = fallback
    chapters = list(checkpoint.get('chapters',[]))
    phases = ('opening question and concrete evidence', 'how the behavior worked',
              'what it changed in everyday life', 'limits and alternative interpretations',
              'payoff and return to the opening evidence')
    for block,phase in enumerate(phases):
        if len(chapters) >= (block+1)*4:
            continue
        first = len(chapters)+1
        numbers = list(range(first,(block+1)*4+1))
        labels = {chapter['label'].casefold() for chapter in chapters}
        accepted = {}
        feedback = ''
        problems = {}
        for attempt in range(9):
            pending = [number for number in numbers if number not in accepted]
            if attempt:
                pending = pending[:2]
            try:
                batch = ask(
                    f'Write only chapters {pending}, in that exact order, of a {CHAPTER_COUNT}-chapter '
                    f'documentary titled {title!r}. This section covers {phase}. Angle: {idea["angle"]}. '
                    f'Use only this evidence: {facts}. Already-used chapter labels: {sorted(labels)}. '
                    'Each chapter has three visual beats. Aim for 41–44 spoken English words in each beat '
                    'and at least 110 words in each chapter. Count individual words, not characters. '
                    'Use distinct 2–6-word labels. Chapter 1 opens on a concrete clue followed by a question. '
                    'Chapter 20 answers it. Each chapter should advance the story with a new observation, '
                    'comparison or evidence limit. Distinguish reconstruction from fact. '
                    'Choose the setting, objects and framing. Give 1–3 characters distinct positions and '
                    'a relevant action. Use watch only alongside somebody doing an action. '
                    f'Prefer {prop} where it fits. Avoid invented facts, gore, greetings and calls to subscribe. '
                    +feedback,object_schema(chapters=array(CHAPTER,len(pending))),seed+50+block*90+attempt*12
                )['chapters']
            except StoryGenerationError as error:
                if not error.retryable or attempt==8:
                    raise
                print(json.dumps({'check':'prehistory structural retry','chapters':pending,
                                  'attempt':attempt+1,'code':error.code}),flush=True)
                feedback = 'Return the exact number of complete chapters in the schema.'
                continue
            problems = {number:issues for number,issues in problems.items() if number not in pending}
            for number,chapter in zip(pending,batch):
                chapter = dict(chapter,label=' '.join(chapter['label'].split()))
                beats = chapter['beats']
                if number==1 and '?' not in beats[0]['narration']:
                    beats[0]['narration'] = f"{title} {beats[0]['narration']}"
                issues = chapter_issues(chapter,labels)
                if issues:
                    problems[number] = issues
                else:
                    accepted[number] = chapter
                    labels.add(chapter['label'].casefold())
            # Save the accepted chronological prefix even if another chapter needs repair.
            while len(chapters)+1 in accepted:
                chapters.append(accepted.pop(len(chapters)+1))
            save_checkpoint({'idea':idea,'chapters':chapters})
            numbers = [number for number in numbers if number > len(chapters)]
            if not numbers:
                break
            print(json.dumps({'check':'prehistory chapter repair','attempt':attempt+1,
                              'issues':problems,'next_chapter':len(chapters)+1}),flush=True)
            feedback = f'Repair only the requested chapters. Validation issues by chapter: {problems}.'
        else:
            raise StoryGenerationError('Prehistory chapter validation exhausted its retries',code='prehistory_story',
                                       details={'pending_chapters':numbers,'last_issues':problems})
    tags = []
    for value in (subject,*idea['tags'],'human evolution','prehistory documentary','Stone Age'):
        value = ' '.join(value.split())
        if 2 <= len(value) <= 45 and value.casefold() not in {tag.casefold() for tag in tags} and not re.search('[<>]',value):
            tags.append(value)
    description = ' '.join(idea['description'].replace('<','').replace('>','').split())[:360].strip()
    return {'genre':'prehistory','topic':topic,'title':title,'hook':hook,'description':description,
            'tags':tags,'chapters':chapters,'source':source,'subject':subject}


def chapter_issues(chapter,labels):
    issues = []
    label = chapter['label']
    if not 2 <= len(label.split()) <= 6 or len(label)>64 or re.search('[<>]',label):
        issues.append('label must be 2–6 words, at most 64 characters')
    elif label.casefold() in labels:
        issues.append('duplicate chapter label')
    counts = [len(beat['narration'].split()) for beat in chapter['beats']]
    if any(not BEAT_WORDS[0] <= count <= BEAT_WORDS[1] for count in counts) or sum(counts)<CHAPTER_MIN_WORDS:
        issues.append(f'beat word counts {counts}; need {BEAT_WORDS[0]}–{BEAT_WORDS[1]} each and at least {CHAPTER_MIN_WORDS} total')
    for number,beat in enumerate(chapter['beats'],1):
        if re.search('[<>]',beat['narration']):
            issues.append(f'beat {number} contains angle brackets')
        cast = beat.get('cast')
        if cast and (len({member['position'] for member in cast}) != len(cast)
                     or all(member['action']=='watch' for member in cast)):
            issues.append(f'beat {number} needs distinct positions and an active character')
    return issues


def valid_chapters(chapters,used=None,*,word_bounds=(17,34)):
    labels = set(used or ())
    for chapter in chapters:
        label = ' '.join(chapter['label'].split())
        if not 2 <= len(label.split()) <= 6 or len(label)>64 or label.casefold() in labels or re.search('[<>]',label):
            return False
        labels.add(label.casefold())
        for beat in chapter['beats']:
            if not word_bounds[0] <= len(beat['narration'].split()) <= word_bounds[1] or re.search('[<>]',beat['narration']):
                return False
            if 'cast' in beat:
                positions = {member['position'] for member in beat['cast']}
                if len(positions) != len(beat['cast']) or all(member['action']=='watch' for member in beat['cast']):
                    return False
    return True


def metadata(plan,starts):
    if len(starts) != len(plan['chapters']) or len(starts)<3 or starts[0]!=0:
        raise ValueError('Missing measured chapter timestamps')
    seconds = [int(start) for start in starts]
    if any(b-a<10 for a,b in zip(seconds,seconds[1:])):
        raise ValueError('YouTube chapters must be ten seconds apart')
    chapters = '\n'.join(f'{t//60:02}:{t%60:02} {chapter["label"]}'
                         for t,chapter in zip(seconds,plan['chapters']))
    description = (f"{plan['description']}\n\nChapters\n{chapters}\n\n"
                   "Scenes are illustrative reconstructions.\n\n"
                   f"Source\nSmithsonian Human Origins Program — {plan['source']}\n\n"
                   "#Prehistory #HumanEvolution #StoneAge")
    return {key:plan[key] for key in ('genre','title','tags')} | {'description':description}
