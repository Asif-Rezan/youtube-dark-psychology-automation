"""Source-aware YouTube packaging for historical documentaries."""
import json
import re

CLICKBAIT = re.compile(r'\b(?:shocking|unbelievable|exposed|proof|finally revealed|they hid|you won.t believe)\b', re.I)


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
        if not 2 <= len(text.split()) <= 4 or len(text) > 26 or not 25 <= len(prompt) <= 260:
            continue
        if text.casefold() in title.casefold():
            continue
        if re.search(r'\b(?:wizard|magic|fantasy)\b', prompt, re.I):
            continue
        score = 5 if title.casefold().startswith(keyword.casefold()) else 0
        score += 2 if 45 <= len(title) <= 65 else 0
        score += 1 if '?' in title else 0
        score += 1 if len(text.split()) <= 3 else 0
        valid.append((score, {'title': title, 'thumbnail_text': text, 'thumbnail_prompt': prompt}))
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
Thumbnail text: 2-4 short words, maximum 26 characters, a visual hook that complements the
corresponding title without repeating a phrase from it. It must remain legible on a phone.
Thumbnail prompt: 25-260 characters, one historically appropriate focal subject on the RIGHT,
clear dark space on the LEFT for text, rich contrast, no embedded letters, labels or logos.
Do not depict disputed hypotheses as established fact. No wizard or fantasy imagery.
Description intro: 80-400 characters, put the exact subject phrase naturally in the FIRST sentence
and state what the viewer will learn. Description details: 80-800 characters, unique to this episode,
explain the key evidence and remaining uncertainty. Do not invent historical claims.
Tags: 4-8 concise specific search variants, including sensible spelling variants if useful;
no unrelated trend tags, hashtags, or keyword stuffing. Return only the requested JSON.'''
    result = ask(prompt, 2600, schema)
    return choose_package(story, topic, result)
