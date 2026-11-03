"""Generate a review-only example through the production artwork pipeline."""
import argparse
import json
from pathlib import Path

from artwork import create_artwork
from song_images import image_plan

SONG = {
    'title': 'चाँदनी में तेरा साथ | Chandni Mein Tera Saath | Hindi Romantic Song 2026',
    'lyrics': '[Verse 1]\nपुरानी किताबों में तेरा खत मिला\nखामोश शामों को नया साथ मिला\n[Chorus]\nतेरे साथ ये चाँदनी गुनगुनाए\nहर पन्ना मुझे तेरे पास बुलाए\n',
    'prompt': 'Hindi romantic acoustic pop, intimate melodic vocal, warm guitar and piano',
    'description': 'An original Hindi romantic song about reuniting in a moonlit old bookshop.',
    'duration': 195,
    'visual_mood': 'romance',
    'thumbnail_text': 'TERE SAATH',
    'background_prompt': 'Adult South Asian couple meeting in a moonlit old bookshop, exchanging tender smiles beside wooden shelves, golden lantern light, cobalt moonlit window, colorful clothing, warm romance.',
    'thumbnail_prompt': 'Young adult South Asian couple sharing tender eye contact beside a moonlit bookshop window, separate faces, warm lantern glow, teal-gold bokeh.',
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--kind', choices=['background', 'thumbnail', 'compose'], required=True)
    parser.add_argument('--output', type=Path, default=Path('output/artwork-demo'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/'song.json').write_text(json.dumps(SONG, ensure_ascii=False, indent=2))
    if args.kind == 'compose':
        create_artwork(args.output, SONG)
    else:
        from image_cpu import generate
        plan = next(plan for plan in image_plan(SONG) if plan['kind'] == args.kind)
        generate(plan['prompt'], args.output/f'{args.kind}-source.png', seed=plan['seed'], allow_text=plan['allow_text'])
        (args.output/f'{args.kind}-plan.json').write_text(json.dumps(plan, indent=2))


if __name__ == '__main__':
    main()
