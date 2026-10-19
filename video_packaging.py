"""Source-aware YouTube packaging for historical documentaries."""
import json
import re
import time
from thumbnail_design import hook_layout

CLICKBAIT = re.compile(r'\b(?:shocking|unbelievable|exposed|proof|finally revealed|they hid|you won.t believe)\b', re.I)
VAGUE_HOOK = re.compile(r'^(?:WHAT HAPPENED|THE HIDDEN TRUTH|WHAT IS THIS|WHAT\'S INSIDE)\?$', re.I)
QUESTION_OPENERS = {'HOW', 'WHY', 'WHAT', 'WHO', 'WHERE'}


def _plain(value):
    return re.sub(r'\s+', ' ', value).strip()


def artwork_candidate(prompt, topic):
    """Use the curated composition when generated artwork misses mechanical limits.

    Never truncate a scene or append an anchor to unrelated generated content.
    The replacement still passes every visual validation below.
    """
    anchor = topic['thumbnail_anchor']
    if 25 <= len(prompt) <= 220 and anchor.casefold() in prompt.casefold():
        return prompt
    curated = _plain(topic['thumbnail_visual_story'])
    return curated if anchor.casefold() in curated.casefold() else f'{anchor}. {curated}'


def description_parts(payload, topic):
    """Repair mechanical description failures using only the curated topic facts."""
    keyword = topic['search_phrase']
    intro = _plain(payload.get('description_intro', ''))
    details = _plain(payload.get('description_details', ''))
    # Sensational claims must be rejected, even if another constraint also fails.
    if CLICKBAIT.search(intro) or CLICKBAIT.search(details):
        raise ValueError('Description contains prohibited clickbait')
    if (not 80 <= len(intro) <= 400 or keyword.casefold() not in
            re.split(r'(?<=[.!?])\s', intro, maxsplit=1)[0].casefold()):
        intro = (f'{keyword}: explore the historical evidence, surviving remains, '
                 'and questions examined in this documentary.')
    if not 80 <= len(details) <= 800:
        facts = [_plain(fact) for fact in topic.get('facts', []) if _plain(fact)]
        if not facts:
            raise ValueError('Description fallback requires curated historical facts')
        details = ' '.join(facts) + ' The documentary distinguishes the supplied evidence from uncertain interpretation.'
    if (not 80 <= len(intro) <= 400 or not 80 <= len(details) <= 800
            or CLICKBAIT.search(intro) or CLICKBAIT.search(details)):
        raise ValueError('Curated description exceeds metadata constraints')
    if not intro.endswith(('.', '?', '!')):
        intro += '.'
    return intro, details


def choose_package(story, topic, payload):
    """Use a concise, accurate title and matching thumbnail hook; retain alternatives for review."""
    keyword = topic['search_phrase']
    candidates = [payload.get(key, {}) for key in ('option_a', 'option_b', 'option_c')]
    valid = []
    rejected = []
    for name, option in zip(('option_a', 'option_b', 'option_c'), candidates):
        title = _plain(option.get('title', ''))
        text = _plain(option.get('thumbnail_text', ''))
        prompt = artwork_candidate(_plain(option.get('thumbnail_prompt', '')), topic)
        if not 35 <= len(title) <= 75 or keyword.casefold() not in title[:52].casefold():
            rejected.append(f'{name}: title must be 35-75 characters and contain the exact subject within its first 52 characters')
            continue
        if CLICKBAIT.search(title) or CLICKBAIT.search(text):
            rejected.append(f'{name}: title or thumbnail question uses prohibited clickbait')
            continue
        hook_words = text.rstrip('?').split()
        if (not text.endswith('?') or not 2 <= len(hook_words) <= 5 or len(text) > 30
                or hook_words[0].upper() not in QUESTION_OPENERS or VAGUE_HOOK.fullmatch(text)):
            rejected.append(f'{name}: thumbnail needs a specific 2-5 word question, max 30 characters, ending ?, starting HOW/WHY/WHAT/WHO/WHERE')
            continue
        try:
            hook_layout(text)
        except ValueError:
            rejected.append(f'{name}: thumbnail question cannot fit at readable size')
            continue
        if not 25 <= len(prompt) <= 220 or topic['thumbnail_anchor'].casefold() not in prompt.casefold():
            rejected.append(f'{name}: artwork prompt must be 25-220 characters and contain the exact anchor phrase')
            continue
        if any(re.search(r'\b'+re.escape(term)+r'\b', prompt, re.I)
               for term in topic.get('thumbnail_forbidden_terms', [])):
            rejected.append(f'{name}: artwork prompt contains a forbidden visual element, even if phrased as a negative instruction')
            continue
        if text.casefold() in title.casefold():
            rejected.append(f'{name}: thumbnail question repeats the title')
            continue
        if re.search(r'\b(?:wizard|magic|fantasy)\b', prompt, re.I):
            rejected.append(f'{name}: artwork prompt contains fantasy terms, even if phrased as a negative instruction')
            continue
        score = 5 if title.casefold().startswith(keyword.casefold()) else 0
        score += 2 if 45 <= len(title) <= 65 else 0
        score += 1 if '?' in title else 0
        score += 2 if len(hook_words) <= 4 else 0
        score += 1 if any(word in text.casefold() for word in topic['thumbnail_anchor'].casefold().split()) else 0
        visual_story = topic['thumbnail_visual_story'].strip().rstrip('.')
        # Put the source-backed visual story first so diffusion's token limit preserves it.
        # One concise composition, not several competing scene descriptions.
        # Keep the anchor and its unresolved visual relationship ahead of style.
        artwork_prompt = visual_story if prompt.rstrip('.') == visual_story else f'{visual_story}. {prompt}'
        artwork_prompt = ' '.join(artwork_prompt.split()[:45])
        artwork_prompt += '. Documentary photograph, natural side light, no text.'
        valid.append((score, {'title': title, 'thumbnail_text': text, 'thumbnail_prompt': artwork_prompt}))
    if not valid:
        raise ValueError('No accurate, readable YouTube title and thumbnail pair: ' + '; '.join(rejected))
    valid.sort(key=lambda pair: pair[0], reverse=True)
    best = valid[0][1]
    intro, details = description_parts(payload, topic)
    relevant_text = ' '.join([keyword, topic['category']] + topic.get('facts', []))
    relevant_stems = {word[:5] for word in re.findall(r'[a-z]{5,}', relevant_text.casefold())
                      if word not in {'history', 'ancient', 'historical', 'documentary', 'archaeology'}}
    base_tags = [keyword, topic['category'], 'history documentary']
    if 'archaeolog' in topic['category'].casefold() or 'ancient structure' in topic['category'].casefold():
        base_tags.append('archaeology')
    tags = []
    for tag in base_tags + payload.get('tags', []):
        tag = _plain(tag)
        if tag not in base_tags and not any(word[:5] in relevant_stems for word in
                                            re.findall(r'[a-z]{5,}', tag.casefold())):
            continue
        if tag and tag.casefold() not in [item.casefold() for item in tags] and len(tag) <= 40:
            tags.append(tag)
    tags = tags[:12]
    if len(','.join(tags)) > 400:
        raise ValueError('Video tags exceed YouTube metadata budget')
    description = (f'{intro}\n\n{details}\n\n'
                   'Sources and further reading:\n' + '\n'.join(topic['sources']) +
                   '\n\nVisual scenes are artistic historical reconstructions, not archival footage.')
    if len(description) > 4500:
        raise ValueError('Video description exceeds upload budget')
    story.update(best, description=description, tags=tags, search_phrase=keyword,
                 packaging_alternatives=[item[1] for item in valid[1:]])
    return story


def request_package(story, topic, ask, pause=None):
    pause = pause or time.sleep
    text = {'type': 'string'}
    option = {'type': 'object', 'properties': {k: text for k in
              ('title', 'thumbnail_text', 'thumbnail_prompt')},
              'required': ['title', 'thumbnail_text', 'thumbnail_prompt'], 'additionalProperties': False}
    schema = {'type': 'object', 'properties': {
        'option_a': option, 'option_b': option, 'option_c': option,
        'description_intro': text, 'description_details': text,
        'tags': {'type': 'array', 'items': text}},
        'required': ['option_a', 'option_b', 'option_c', 'description_intro', 'description_details', 'tags'],
        'additionalProperties': False}
    outline = [scene.get('summary', '') for scene in story['scenes']]
    prompt = f'''Create YouTube packaging for an English historical documentary.
Search subject phrase: {topic['search_phrase']}
Category: {topic['category']}
Verified facts: {json.dumps(topic['facts'])}
Episode outline: {json.dumps(outline)}
Existing title: {story['title']}
Return three DISTINCT title-thumbnail pairs (option_a, option_b, option_c).
Each title: 35-75 characters, put the exact search subject phrase in the first 52 characters,
accurately promise a specific question or evidence in this episode, use normal capitalization.
Avoid generic "mystery revealed" wording, sensational certainty, unsupported claims and clickbait.
Thumbnail text: a SPECIFIC unresolved question with a curiosity gap, 2-5 short words,
maximum 30 characters, ending in ?. Start with HOW, WHY, WHAT, WHO or WHERE.
The question must be answerable or honestly investigated in this episode. Avoid vague
questions such as WHAT HAPPENED? or false suggestions of hidden chambers or cover-ups.
Complement the title without repeating its phrasing. It must be legible on a phone.
Thumbnail's documented visual anchor: {topic['thumbnail_anchor']}.
The image must tell this source-backed visual story: {topic['thumbnail_visual_story']}.
Do not mention or depict these elements in thumbnail artwork: {json.dumps(topic.get('thumbnail_forbidden_terms', []))}.
Omit forbidden words entirely, including negative phrases such as "no pyramid"; the renderer handles exclusions.
Thumbnail prompt: 25-220 characters, include the exact visual-anchor phrase, and add
a specific scene composition that builds on the visual story. Make the historical scale,
entrance, path or object relationship the source of curiosity even with no words visible.
Place the intriguing detail on the RIGHT and leave dark space on the LEFT for the question.
Use dramatic but plausible light and depth. No embedded letters, labels, arrows, logos,
fictional discoveries or fantasy imagery.
Description intro: 80-400 characters, put the exact subject phrase naturally in the FIRST sentence
and state what the viewer will learn. Description details: 80-800 characters, unique to this episode,
explain the key evidence and remaining uncertainty. Do not invent historical claims.
Tags: 4-8 concise specific search variants, including sensible spelling variants if useful;
no unrelated trend tags, hashtags, or keyword stuffing. Return only the requested JSON.'''
    feedback = ''
    for attempt in range(3):
        if attempt:
            pause(60)  # Respect the free provider's request/token budget.
        result = ask(prompt + feedback, 2600, schema)
        try:
            return choose_package(story, topic, result)
        except ValueError as error:
            print(json.dumps({'check': 'Documentary packaging', 'attempt': attempt+1,
                              'passed': False, 'reason': str(error)}), flush=True)
            if attempt == 2:
                raise
            feedback = ('\nYour previous response failed validation: ' + str(error) +
                        '\nPrevious metadata: ' + json.dumps(result) +
                        '\nCorrect these issues. Return the complete requested JSON; '
                        'keep every historical claim within the supplied evidence.')
