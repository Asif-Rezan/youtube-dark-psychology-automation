import tempfile
import unittest
from pathlib import Path
from PIL import Image
from video_packaging import choose_package
from thumbnail_design import render_thumbnail


class PackagingTests(unittest.TestCase):
    def setUp(self):
        self.topic = {'search_phrase': 'Great Pyramid of Giza', 'category': 'Ancient Egypt',
                      'sources': ['https://whc.unesco.org/en/list/86/']}
        self.story = {'title': 'Draft', 'scenes': [{'summary': 'Limestone blocks remain'}]}
        self.payload = {
            'option_a': {'title': 'Great Pyramid of Giza: What the Stonework Tells Us',
                         'thumbnail_text': 'STONE CLUES',
                         'thumbnail_prompt': 'Ancient Egyptian pyramid stonework on the right, natural desert light and open dark space on the left, no written letters.'},
            'option_b': {'title': 'The Shocking Great Pyramid of Giza Secret Exposed',
                         'thumbnail_text': 'SECRET EXPOSED',
                         'thumbnail_prompt': 'Pyramid stonework fills the right side in natural light, with empty dark space on the left, no text.'},
            'option_c': {'title': 'Great Pyramid of Giza and the Questions Its Stones Raise',
                         'thumbnail_text': 'ANCIENT EVIDENCE',
                         'thumbnail_prompt': 'Limestone blocks and the Great Pyramid appear at right, dark open desert foreground at left, no letters.'},
            'description_intro': 'The Great Pyramid of Giza still raises questions about ancient Egyptian building. This documentary examines its surviving stonework.',
            'description_details': 'We follow the visible remains, the larger Memphis necropolis and the limits of the surviving evidence. Where the record is uncertain, the narration says so.',
            'tags': ['Giza pyramid', 'Egyptian pyramids', 'unrelated trending topic']}

    def test_metadata_frontloads_subject_and_rejects_clickbait(self):
        result = choose_package(self.story, self.topic, self.payload)
        self.assertTrue(result['title'].startswith('Great Pyramid of Giza'))
        self.assertNotIn('Shocking', result['title'])
        self.assertIn('Great Pyramid of Giza', result['description'].splitlines()[0])
        self.assertIn(self.topic['sources'][0], result['description'])
        self.assertEqual(result['tags'][0], self.topic['search_phrase'])
        self.assertLessEqual(len(result['tags']), 12)
        self.assertNotIn('unrelated trending topic', result['tags'])

    def test_rejects_unrelated_title_and_bad_opening(self):
        self.payload['option_a']['title'] = 'A Hidden Secret Nobody Wants You to Discover Today'
        self.payload['option_c']['title'] = 'An Unrelated Story About Ancient Sites and Objects'
        with self.assertRaisesRegex(ValueError, 'No accurate'):
            choose_package(self.story, self.topic, self.payload)

    def test_thumbnail_is_wide_readable_and_small_enough(self):
        with tempfile.TemporaryDirectory() as temp:
            source, target = Path(temp)/'source.png', Path(temp)/'thumbnail.jpg'
            Image.new('RGB', (1024, 576), (194, 138, 69)).save(source)
            render_thumbnail(source, 'STONE CLUES', target)
            with Image.open(target) as image:
                self.assertEqual(image.size, (1280, 720))
                self.assertLess(sum(image.getpixel((80, 590))), sum(image.getpixel((1200, 590))))
            self.assertLess(target.stat().st_size, 2*1024*1024)


if __name__ == '__main__':
    unittest.main()
