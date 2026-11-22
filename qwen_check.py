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
    parser.add_argument('--packaging-only', action='store_true')
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
    import workflow as w
    schema = {'type': 'object', 'properties': {'narration': w.narration_text_schema(74, 104)},
              'required': ['narration'], 'additionalProperties': False}
    result = w.request_text('chat/completions', {
        'model': 'Qwen/Qwen3-4B-Instruct-2507',
        'messages': [{'role': 'user', 'content': 'Write about 84 words of historical documentary narration. '
            'Explain that ventilation shafts supplied air to underground chambers in Cappadocia. '
            'Distinguish visible architectural evidence from uncertainty about its use. '
            'Use plain English, ASCII punctuation and single spaces; finish with a complete sentence.'}],
        'response_format': {'type': 'json_schema', 'json_schema': {'schema': schema}},
        'max_completion_tokens': 512, 'temperature': .7})
    count = len(json.loads(result['choices'][0]['message']['content'])['narration'].split())
    assert 74 <= count <= 104
    print(json.dumps({'check': 'Decoder-constrained chapter length', 'passed': True, 'words': count}), flush=True)
    if args.packaging_only:
        import datetime
        from video_packaging import request_package
        topics = json.loads(Path('history_topics.json').read_text())
        topic = topics[datetime.date(2026, 10, 25).toordinal() % len(topics)]
        story = {'title': topic['title_angle'], 'scenes': [
            {'summary': fact} for fact in topic['facts']]}
        def ask(prompt, limit, schema):
            result = w.request_text('chat/completions', {
                'model': 'Qwen/Qwen3-4B-Instruct-2507',
                'messages': [{'role': 'user', 'content': prompt}],
                'response_format': {'type': 'json_schema', 'json_schema': {'schema': schema}},
                'max_completion_tokens': limit, 'temperature': .7})
            return json.loads(result['choices'][0]['message']['content'])
        request_package(story, topic, ask, pause=lambda _: None)
        print(json.dumps({'check': 'Qwen documentary packaging', 'passed': True}), flush=True)
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
