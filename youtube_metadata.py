"""Consistent upload settings and URL-free public descriptions."""
import re

UPLOAD_PARTS = 'snippet,status,paidProductPlacementDetails'
UPLOAD_SETTINGS = {
    'categoryId': '24', 'defaultLanguage': 'en', 'defaultAudioLanguage': 'en',
    'containsSyntheticMedia': True, 'hasPaidProductPlacement': False,
}


def public_description(text):
    # Remove citation blocks from older checkpoints, retaining ordinary prose.
    text = re.split(r'(?im)^Sources and further reading:\s*$', text)[0]
    text = re.sub(r'(?im)^\s*Source:\s*.*$', '', text)
    text = re.sub(r'\[([^\]]+)\]\((?:https?://|www\.)[^)]+\)', r'\1', text)
    text = re.sub(r'(?:https?://|www\.)\S+', '', text, flags=re.I)
    return re.sub(r'\n{3,}', '\n\n', text).strip()


def upload_body(story, description):
    return {
        'snippet': {'title': story['title'], 'description': description,
                    'tags': story['tags'], 'categoryId': '24',
                    'defaultLanguage': 'en', 'defaultAudioLanguage': 'en'},
        'status': {'privacyStatus': 'private', 'selfDeclaredMadeForKids': False,
                   'containsSyntheticMedia': True},
        'paidProductPlacementDetails': {'hasPaidProductPlacement': False},
    }


def verify_upload_settings(video):
    for section, expected in (
        ('snippet', {k: UPLOAD_SETTINGS[k] for k in
                     ('categoryId', 'defaultLanguage', 'defaultAudioLanguage')}),
        ('status', {'containsSyntheticMedia': True}),
        ('paidProductPlacementDetails', {'hasPaidProductPlacement': False}),
    ):
        actual = video.get(section, {})
        for field, value in expected.items():
            if actual.get(field) != value:
                raise RuntimeError(f'YouTube upload setting mismatch: {field}')
