import copy
import unittest

from video_chapters import add_measured_chapters


class MeasuredChapterTests(unittest.TestCase):
    def setUp(self):
        self.story = {'description': 'Dark Psychology: recognize pressure and set boundaries.',
                      'scenes': [{'summary': text} for text in (
                          'Recognizing the pattern', 'Why pressure works', 'Setting a boundary')]}

    def test_uses_cumulative_final_audio_not_estimated_equal_sections(self):
        original = copy.deepcopy(self.story)
        result = add_measured_chapters(self.story, [35.8, 49.7, 28.2])
        self.assertEqual([c['start_seconds'] for c in result['chapters']], [0, 35, 85])
        self.assertIn('00:00 Recognizing the pattern', result['description'])
        self.assertIn('01:25 Setting a boundary', result['description'])
        self.assertEqual(self.story, original)

    def test_retry_replaces_old_markers_and_is_idempotent(self):
        first = add_measured_chapters(self.story, [35.8, 49.7, 28.2])
        self.assertEqual(add_measured_chapters(first, [35.8, 49.7, 28.2]), first)
        updated = add_measured_chapters(first, [40, 50, 30])
        self.assertEqual(updated['description'].count('Chapters'), 1)
        self.assertNotIn('01:25', updated['description'])
        self.assertIn('01:30 Setting a boundary', updated['description'])

    def test_invalid_timings_stop_instead_of_publishing_fake_chapters(self):
        for lengths in ([30, 30], [30, 9.9, 30], [30, float('nan'), 30],
                        [30, float('inf'), 30], [30, True, 30]):
            with self.subTest(lengths=lengths), self.assertRaises(ValueError):
                add_measured_chapters(self.story, lengths)

    def test_labels_cannot_inject_lines_and_upload_preserves_chapters(self):
        from youtube_metadata import public_description, upload_body
        self.story['scenes'][1]['summary'] = 'Pressure\n99:59 Fake marker'
        result = add_measured_chapters(self.story, [30, 30, 30])
        description = public_description(result['description'])
        body = upload_body(dict(result, title='Dark Psychology', tags=['dark psychology']), description)
        self.assertEqual(body['snippet']['description'], result['description'])
        self.assertNotIn('\n99:59', description)

    def test_hour_long_timestamps_and_metadata_budget(self):
        result = add_measured_chapters(self.story, [3600, 30, 30])
        self.assertIn('1:00:00 Why pressure works', result['description'])
        self.story['description'] = 'x' * 4490
        with self.assertRaisesRegex(ValueError, 'budget'):
            add_measured_chapters(self.story, [30, 30, 30])
