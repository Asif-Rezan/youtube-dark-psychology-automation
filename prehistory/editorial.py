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
ACTIONS = ('show','walk','carry','work','react')
PROPS = ('stone','fire','map','food','art','shelter')
STR = {'type':'string'}


def object_schema(**fields):
    return {'type':'object','properties':fields,'required':list(fields),'additionalProperties':False}


def array(items,n):
    return {'type':'array','items':items,'minItems':n,'maxItems':n}


BEAT = object_schema(narration=STR,action={'type':'string','enum':list(ACTIONS)},
                     prop={'type':'string','enum':list(PROPS)})
CHAPTER = object_schema(label=STR,beats=array(BEAT,3))


def ask(message,schema,seed):
    response = request_story('chat/completions',{
        'messages':[{'role':'user','content':message}],
        'response_format':{'type':'json_schema','json_schema':{'schema':schema}},
        'seed':seed,'max_completion_tokens':2900,
    })
    return json.loads(response['choices'][0]['message']['content'])


def generate(run_id,history):
    used = [row.get('prehistory_topic') for row in history]
    last_seen = {item:i for i,item in enumerate(used) if item in TOPICS}
    oldest = sorted(TOPICS,key=lambda key:last_seen.get(key,-1))[:3]
    topic_names = {key:TOPICS[key][0] for key in oldest}
    idea_schema = object_schema(topic={'type':'string','enum':oldest},title=STR,hook=STR,
                                description=STR,tags=array(STR,6),angle=STR)
    seed = int.from_bytes(hashlib.sha256(run_id.encode()).digest()[:4],'big') % 1_900_000_000
    titles = {row.get('title','').casefold() for row in history}
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
    topic = idea['topic']
    subject,source,facts,prop,fallback = TOPICS[topic]
    hook = ' '.join(idea['hook'].upper().split())
    if not (2 <= len(hook.split()) <= 5 and re.fullmatch(r'[A-Z0-9 ]{3,25}\?',hook)
            and hook.casefold().rstrip('?') not in title.casefold()):
        hook = fallback
    chapters = []
    for block in range(2):
        feedback = ''
        for attempt in range(4):
            batch = ask(
                f'Write chapters {block*4+1}–{block*4+4} of a short documentary titled {title!r}. '
                f'Angle: {idea["angle"]}. Use only this evidence: {facts}. Earlier chapter labels: '
                f'{[chapter["label"] for chapter in chapters]}. Each chapter has three consecutive visual beats '
                'with 17–34 spoken English words per beat. Labels should be distinct, 2–6 words. '
                'Start the episode in a concrete scene with a question before the first beat ends. '
                'In the second half give a surprising clue and answer the question in the last beat. '
                'Use only these motion labels: show, walk, carry, work, react. The action and prop must fit '
                'the spoken beat; show is an explanatory gesture. Characters are anonymous reconstructions. '
                f'Prefer the episode prop {prop}, but switch where the subject requires it. '
                'Avoid invented dates, quotes, certainty, gore, greetings, or a request to subscribe. '+feedback,
                object_schema(chapters=array(CHAPTER,4)),seed+50+block*20+attempt*3)['chapters']
            labels = {chapter['label'].casefold() for chapter in chapters}
            if valid_chapters(batch,labels) and (block or '?' in batch[0]['beats'][0]['narration']):
                chapters.extend(batch)
                break
            feedback = 'Return unique short labels, exact beat counts and lengths, and a question in the first beat.'
        else:
            raise StoryGenerationError('Prehistory story missed chapter or opening requirements',code='prehistory_story',
                                       details={'starting_chapter':block*4+1})
    tags = []
    for value in (subject,*idea['tags'],'human evolution','prehistory documentary','Stone Age'):
        value = ' '.join(value.split())
        if 2 <= len(value) <= 45 and value.casefold() not in {tag.casefold() for tag in tags} and not re.search('[<>]',value):
            tags.append(value)
    description = ' '.join(idea['description'].replace('<','').replace('>','').split())[:360].strip()
    return {'genre':'prehistory','topic':topic,'title':title,'hook':hook,'description':description,
            'tags':tags,'chapters':chapters,'source':source,'subject':subject}


def valid_chapters(chapters,used=None):
    labels = set(used or ())
    for chapter in chapters:
        label = ' '.join(chapter['label'].split())
        if not 2 <= len(label.split()) <= 6 or len(label)>64 or label.casefold() in labels or re.search('[<>]',label):
            return False
        labels.add(label.casefold())
        for beat in chapter['beats']:
            if not 17 <= len(beat['narration'].split()) <= 34 or re.search('[<>]',beat['narration']):
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
