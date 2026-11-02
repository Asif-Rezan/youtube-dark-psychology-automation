import copy
import unittest
from youtube_metadata import public_description, upload_body, verify_upload_settings


class UploadMetadataTests(unittest.TestCase):
    def setUp(self):
        self.body = upload_body({'title': 'Dark Psychology: Recognizing Manipulation',
                                 'tags': ['dark psychology', 'manipulation']}, 'Educational description')

    def test_explicit_requested_settings(self):
        verify_upload_settings(self.body)
        self.assertEqual(self.body['snippet']['categoryId'], '27')
        self.assertEqual(self.body['snippet']['defaultAudioLanguage'], 'en')
        self.assertTrue(self.body['status']['containsSyntheticMedia'])
        self.assertIs(self.body['paidProductPlacementDetails']['hasPaidProductPlacement'], False)
        self.assertEqual(self.body['status']['privacyStatus'], 'private')
        self.assertNotIn('academicSystem', self.body['snippet'])

    def test_every_remote_setting_is_checked(self):
        for section in ('snippet', 'status', 'paidProductPlacementDetails'):
            fields = ('categoryId', 'defaultLanguage', 'defaultAudioLanguage') if section == 'snippet' else (
                'containsSyntheticMedia',) if section == 'status' else ('hasPaidProductPlacement',)
            for field in fields:
                with self.subTest(field=field):
                    remote = copy.deepcopy(self.body)
                    remote[section].pop(field)
                    with self.assertRaisesRegex(RuntimeError, field):
                        verify_upload_settings(remote)

    def test_old_source_block_is_removed_from_checkpoints(self):
        result = public_description('Learn about influence.\n\nSources and further reading:\nhttps://example.com/books/')
        self.assertEqual(result, 'Learn about influence.')

    def test_model_links_removed_without_losing_anchor_text(self):
        result = public_description('Learn [boundaries](https://example.com) and influence.\nSource: https://example.org\nRead www.example.net')
        self.assertIn('Learn boundaries and influence.', result)
        self.assertNotIn('https', result)
        self.assertNotIn('www.', result)
        self.assertNotIn('Source:', result)
