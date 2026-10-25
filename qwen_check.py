"""Check the real local model with the production eight-shot JSON schema."""
import json
import tempfile
from pathlib import Path
from long_video import storyboard


def main():
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


if __name__ == '__main__':
    main()
