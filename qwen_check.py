"""Check the real local model with the production eight-shot JSON schema."""
import argparse
import json
import time
import tempfile
from pathlib import Path
from long_video import storyboard


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--full-story', action='store_true')
    args = parser.parse_args()
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='qwen-check-') as directory:
        root = Path(directory)
        narration = 'Builders carved ventilation shafts through volcanic rock in Cappadocia to bring air underground.'
        story = {'category': 'Cappadocia underground cities',
                 'verified_facts': ['Ventilation shafts brought air into underground chambers.'],
                 'scenes': [{'narration': narration}]}
        (root/'story.json').write_text(json.dumps(story))
        (root/'plan.json').write_text(json.dumps({'shots': [
            {'index': i, 'chapter': 0, 'narration': narration} for i in range(8)]}))
        result = storyboard(root)
        assert result['storyboard_verified'] and len(result['shots']) == 8
        print(json.dumps({'check': 'Local Qwen storyboard', 'passed': True, 'shots': 8}))
    if args.full_story:
        import workflow as w
        from long_video import validate_engagement
        story = w.make_story('2026-10-25', [])
        validate_engagement(story)
        print(json.dumps({'check': 'Local Qwen complete story', 'passed': True,
                          'chapters': len(story['scenes']),
                          'words': sum(len(scene['narration'].split()) for scene in story['scenes']),
                          'elapsed_seconds': round(time.monotonic() - started)}), flush=True)



if __name__ == '__main__':
    main()
