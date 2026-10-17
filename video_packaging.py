"""Source-aware YouTube packaging for historical documentaries."""
import json
import re

CLICKBAIT = re.compile(r'\b(?:shocking|unbelievable|exposed|proof|finally revealed|they hid|you won.t believe)\b', re.I)
VAGUE_HOOK = re.compile(r'^(?:WHAT HAPPENED|THE HIDDEN TRUTH|WHAT IS THIS|WHAT\'S INSIDE)\?$', re.I)
QUESTION_OPENERS = {'HOW', 'WHY', 'WHAT', 'WHO', 'WHERE'}


def _plain(value):
    return re.sub(r'\s+', ' ', value).strip()


def choose_package(story, topic, payload):
    """Use a concise, accurate title and matching thumbnail hook; retain alternatives for review."""
    keyword = topic['search_phrase']
    candidates = [payload.get(key, {}) for key in ('option_a', 'option_b', 'option_c')]
    valid = []
    for option in candidates:
        title = _plain(option.get('title', ''))
        text = _plain(option.get('thumbnail_text', ''))
        prompt = _plain(option.get('thumbnail_prompt', ''))
        if not 35 <= len(title) <= 75 or keyword.casefold() not in title[:52].casefold():
            continue
        if CLICKBAIT.search(title) or CLICKBAIT.search(text):
            continue
        hook_words = text.rstrip('?').split()
        if (not text.endswith('?') or not 2 <= len(hook_words) <= 5 or len(text) > 30
                or hook_words[0].upper() not in QUESTION_OPENERS or VAGUE_HOOK.fullmatch(text)):
            continue
        if not 25 <= len(prompt) <= 220 or topic['thumbnail_anchor'].casefold() not in prompt.casefold():
            continue
        if any(re.search(r'\b'+re.escape(term)+r'\b', prompt, re.I)
               for term in topic.get('thumbnail_forbidden_terms', [])):
            continue
        if text.casefold() in title.casefold():
            continue
        if re.search(r'\b(?:wizard|magic|fantasy)\b', prompt, re.I):
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
        artwork_prompt = f'{visual_story}. {prompt}'
        artwork_prompt = ' '.join(artwork_prompt.split()[:45])
        artwork_prompt += '. Documentary photograph, natural side light, no text.'
        valid.append((score, {'title': title, 'thumbnail_text': text, 'thumbnail_prompt': artwork_prompt}))
    if not valid:
        raise ValueError('No accurate, readable YouTube title and thumbnail pair')
    valid.sort(key=lambda pair: pair[0], reverse=True)
    best = valid[0][1]
    intro = _plain(payload.get('description_intro', ''))
    if not 80 <= len(intro) <= 400 or keyword.casefold() not in re.split(r'(?<=[.!?])\s', intro, maxsplit=1)[0].casefold() or CLICKBAIT.search(intro):
        raise ValueError('Description opening must name the historical subject accurately')
    if not intro.endswith(('.', '?', '!')):
        intro += '.'
    details = _plain(payload.get('description_details', ''))
    if not 80 <= len(details) <= 800 or CLICKBAIT.search(details):
        raise ValueError('Description must explain the evidence and viewer payoff')
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


def request_package(story, topic, ask):
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
    result = ask(prompt, 2600, schema)
    return choose_package(story, topic, result)
