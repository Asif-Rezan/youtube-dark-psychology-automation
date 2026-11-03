import unittest
from pipeline import upload_description, metadata_tags, normalize_lyrics


class PublicPackagingTests(unittest.TestCase):
    def test_public_description_keeps_story_and_removes_internal_and_invented_credits(self):
        song = dict(visual_mood='heartbreak', description=(
            'तेरे बिना is a Hindi sad song about a quiet goodbye.\n'
            'Listen to this new Hindi song 2026 on a rainy evening.\n'
            'Created with ACE-Step 1.5 and Qwen3-4B.\n'
            'Original AI music created by Aarav Sound Lab.\n'
            '#old #extra #tags #four #five'))
        result = upload_description(song)
        self.assertIn('Hindi sad song', result)
        self.assertIn('new Hindi song 2026', result)
        self.assertIn('Original Hindi music by Heart and Mind.', result)
        self.assertNotIn('ACE-Step', result)
        self.assertNotIn('Qwen', result)
        self.assertNotIn('Aarav', result)
        self.assertEqual(result.count('#'), 3)
        self.assertIn('#HindiSadSong', result)

    def test_model_names_do_not_become_upload_tags(self):
        result = metadata_tags(dict(tags=['Hindi Romantic Song', 'Qwen3-4B', 'ACE-Step 1.5']))
        self.assertIn('Hindi Romantic Song', result)
        self.assertNotIn('Qwen3-4B', result)
        self.assertNotIn('ACE-Step 1.5', result)

    def test_layout_normalization_preserves_hindi_lyrics(self):
        text = r'[Verse 1]\\nतेरे बिना\\nमेरा दिल'
        self.assertEqual(normalize_lyrics(text), '[Verse 1]\nतेरे बिना\nमेरा दिल')


if __name__ == '__main__':
    unittest.main()
