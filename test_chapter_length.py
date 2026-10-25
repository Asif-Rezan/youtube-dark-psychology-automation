import json
import unittest
from unittest.mock import Mock, patch
import workflow as w


def words(count):
    return ' '.join(['evidence'] * count)


class ChapterLengthTests(unittest.TestCase):
    def test_valid_batch_does_not_call_model(self):
        ask = Mock()
        self.assertEqual(w.fit_chapter_words([words(84)], ['chapter_01'], 84, ask, 'facts'), [words(84)])
        ask.assert_not_called()

    def test_only_outliers_are_rewritten_and_valid_neighbor_is_preserved(self):
        def ask(prompt, limit, schema):
            keys = schema['properties']['narrations']['required']
            self.assertEqual(keys, ['chapter_02'])
            self.assertIn('facts', prompt)
            return {'narrations': {'chapter_02': words(84)}}
        original = [words(83), words(141)]
        result = w.fit_chapter_words(original, ['chapter_01', 'chapter_02'], 84, ask, 'facts')
        self.assertEqual(result[0], original[0])
        self.assertEqual(len(result[1].split()), 84)
        self.assertEqual(len(original[1].split()), 141)

    def test_short_chapters_are_repaired_too(self):
        ask = Mock(return_value={'narrations': {'chapter_01': words(80)}})
        result = w.fit_chapter_words([words(30)], ['chapter_01'], 84, ask, 'facts')
        self.assertEqual(len(result[0].split()), 80)

    def test_uncooperative_model_is_bounded_and_never_truncated(self):
        ask = Mock(return_value={'narrations': {'chapter_01': words(140)}})
        with self.assertRaisesRegex(ValueError, 'three bounded rewrites'):
            w.fit_chapter_words([words(140)], ['chapter_01'], 84, ask, 'facts')
        self.assertEqual(ask.call_count, 3)

    def test_actual_failed_run_chapters_are_accepted_without_more_rewrites(self):
        counts = [96, 107, 105, 102, 114]
        parts = [words(count) for count in counts]
        ask = Mock()
        result = w.fit_chapter_words(parts, [f'chapter_{i:02}' for i in range(1, 6)], 84, ask, 'facts')
        self.assertEqual(result, parts)
        ask.assert_not_called()

    def test_accepted_maximum_stays_under_global_word_cap_with_cta(self):
        from test_duration_control import story_fixture
        story = story_fixture()
        for scene in story['scenes']:
            scene['narration'] = words(120)
        story['scenes'][-1]['narration'] += (' Which historical question should we investigate next? '
            'Leave a comment, like this video, and subscribe for more history documentaries.')
        w.validate_story(story)
        self.assertLess(sum(len(scene['narration'].split()) for scene in story['scenes']), 2600)

    def test_decoder_pattern_enforces_word_bounds_and_complete_sentence(self):
        import re
        pattern = w.narration_text_schema(74, 104)['pattern']
        for count in (73, 74, 84, 104, 105):
            text = 'Evidence ' * (count - 1) + 'survived.'
            self.assertEqual(bool(re.fullmatch(pattern, text)), 74 <= count <= 104)
        self.assertIsNone(re.fullmatch(pattern, 'Evidence ' * 83 + 'survived'))

    def test_wrong_keys_are_rejected(self):
        ask = Mock(return_value={'narrations': {'wrong': words(84)}})
        with self.assertRaisesRegex(ValueError, 'exactly the requested'):
            w.fit_chapter_words([words(140)], ['chapter_01'], 84, ask, 'facts')

    def test_full_generation_recovers_from_2800_word_model_output(self):
        repairs = []
        def response(endpoint, payload):
            props = payload['response_format']['json_schema']['schema']['properties']
            if 'scenes' in props:
                value = {'title': 'Ancient Underground Cities', 'description': 'Evidence from ancient cities.',
                         'tags': ['history'], 'thumbnail_text': 'HIDDEN CITIES',
                         'thumbnail_prompt': 'Ancient stone chambers',
                         'character_description': '', 'protagonist_name': '',
                         'scenes': {key: {'summary': 'Examine surviving evidence.',
                                         'image_prompt': 'Ancient stone chambers',
                                         'image_prompts': ['Ancient stone chambers']*4}
                                    for key in props['scenes']['required']}}
            else:
                keys = props['narrations']['required']
                repairing = payload['messages'][0]['content'].startswith('Rewrite ONLY')
                if repairing:
                    repairs.append(keys)
                value = {'narrations': {key: words(84 if repairing else 140) for key in keys}}
            return {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(value)}}]}
        with patch('workflow.request_text', side_effect=response), patch('workflow.time.sleep'), patch('video_packaging.request_package'):
            story = w.make_story('2026-10-25', [])
        total = sum(len(scene['narration'].split()) for scene in story['scenes'])
        self.assertTrue(1650 <= total <= 1810, total)
        self.assertEqual(len(story['scenes']), 20)
        self.assertEqual(len(repairs), 4)
        self.assertTrue(story['scenes'][-1]['narration'].endswith('subscribe for more history documentaries.'))
        w.validate_story(story)
