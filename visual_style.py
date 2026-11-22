"""Shared art direction for episode scenes and thumbnail artwork."""
STORYBOOK_STYLE = (
    '3D storybook illustration, sculpted expressive characters, tactile materials, '
    'miniature diorama depth, cinematic volumetric lighting, rich colors, topic-appropriate settings'
)
SCENE_STYLE = (
    'photorealistic cinematic documentary photograph, realistic material texture, '
    'topic-appropriate setting, soft motivated light, readable shadows, restrained color grade, '
    'one clear focal action, uncluttered composition, landscape, no text or watermark'
)
SCENE_NEGATIVE = 'plastic skin, waxy faces, airbrushed skin, exaggerated expression, crushed blacks, oversaturated colors, clutter'

# Keep shot grammar appropriate to the narrated subject rather than forcing portraits.
SCENE_FRAMING = {
    'person': ('medium eye-level shot', 'close-up of natural facial expression',
               'over-the-shoulder shot', 'wide contextual shot'),
    'group': ('medium two-shot, clear interpersonal distance', 'wide contextual group shot',
              'over-the-shoulder interaction', 'medium reaction shot with surrounding people'),
    'object': ('close-up showing realistic surface detail', 'medium contextual object shot',
               'low-angle object detail', 'wide environmental shot'),
}
