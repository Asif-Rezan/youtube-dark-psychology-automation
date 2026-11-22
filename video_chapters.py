"""YouTube chapter markers from final measured narration, never model guesses."""
import math
import re


def add_measured_chapters(story, lengths):
    scenes = story['scenes']
    if len(lengths) != len(scenes) or len(scenes) < 3:
        raise ValueError('Chapters require matching measured audio for at least three scenes')
    starts, elapsed = [], 0.0
    for index, (scene, length) in enumerate(zip(scenes, lengths)):
        if isinstance(length, bool) or not math.isfinite(length) or length < 10:
            raise ValueError('Each measured chapter must last at least ten seconds')
        seconds = math.floor(elapsed)
        minutes, second = divmod(seconds, 60)
        hours, minute = divmod(minutes, 60)
        stamp = f'{hours}:{minute:02}:{second:02}' if hours else f'{minutes:02}:{second:02}'
        label = re.sub(r'\s+', ' ', scene.get('summary', '')).strip()
        label = re.sub(r'^\d+:\d+(?::\d+)?\s*', '', label).strip()
        if len(label) > 64:
            label = label[:65].rsplit(' ', 1)[0]
        starts.append({'start_seconds': seconds, 'title': label or f'Chapter {index + 1}'})
        starts[-1]['timestamp'] = stamp
        elapsed += length
    body = re.sub(r'(?im)^\s*(?:chapters:?|\d{1,3}:\d{2}(?::\d{2})?\s+[^\n]*)\s*$',
                  '', story['description']).strip()
    body = re.sub(r'\n{3,}', '\n\n', body)
    block = 'Chapters\n' + '\n'.join(f"{c['timestamp']} {c['title']}" for c in starts)
    description = f'{body}\n\n{block}'
    if len(description) > 4500:
        raise ValueError('Description and measured chapters exceed the metadata budget')
    return dict(story, description=description, chapters=starts)
