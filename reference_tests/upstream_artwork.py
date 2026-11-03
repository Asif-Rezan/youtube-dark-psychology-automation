from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageChops
from artwork import brighten_scene, create_artwork, poster_finish, poster_thumbnail
from demo_artwork import SONG


class PosterArtworkTests(unittest.TestCase):
    def test_poster_finish_is_reproducible_and_preserves_color(self):
        source = Image.new('RGB', (320, 180), '#8d5340')
        first = poster_finish(source)
        second = poster_finish(source)
        self.assertIsNone(ImageChops.difference(first, second).getbbox())
        red, green, blue = first.split()
        self.assertIsNotNone(ImageChops.difference(red, green).getbbox())
        self.assertIsNotNone(ImageChops.difference(red, blue).getbbox())

    def test_full_artwork_keeps_export_sizes_and_color(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for kind in ('background', 'thumbnail'):
                Image.new('RGB', (1024, 576), '#5678a0').save(root/f'{kind}-source.png')
            create_artwork(root, SONG)
            for name, size in (('cover.png', (1920, 1080)), ('thumbnail.jpg', (1280, 720))):
                with Image.open(root/name) as output:
                    self.assertEqual(output.size, size)
                    red, green, blue = output.convert('RGB').split()
                    self.assertIsNotNone(ImageChops.difference(red, green).getbbox())
                    self.assertIsNotNone(ImageChops.difference(red, blue).getbbox())

    def test_translucent_title_shadow_preserves_full_frame_photo(self):
        source = Image.new('RGB', (1280, 720), 'white')
        output = poster_thumbnail(source, SONG, 'romance')
        self.assertGreater(output.getpixel((400, 400))[0], 230)
        self.assertGreater(output.getpixel((1000, 650))[0], 130)
        self.assertGreater(output.getpixel((100, 50))[0], 230)
        self.assertGreater(output.getpixel((100, 650))[0], 230)

    def test_full_frame_keeps_both_source_regions_visible(self):
        source = Image.new('RGB', (1024, 576), '#ffffff')
        source.paste(Image.new('RGB', (512, 576), '#888888'), (512, 0))
        output = poster_thumbnail(source, SONG, 'romance')
        self.assertGreater(output.getpixel((100, 400))[0], 230)
        self.assertTrue(35 < output.getpixel((1100, 650))[0] < 180)

    def test_thumbnail_has_no_year_genre_badge_or_channel_label(self):
        from unittest.mock import patch
        with patch('artwork.ImageDraw.ImageDraw.text', autospec=True) as text:
            poster_thumbnail(Image.new('RGB', (1280, 720), 'gray'), SONG, 'romance')
        drawn = ' '.join(call.args[2] for call in text.call_args_list)
        self.assertNotIn('2026', drawn)
        self.assertNotIn('Romantic Song', drawn)
        self.assertNotIn('HEART', drawn)

    def test_dark_midtones_are_lifted_without_clipping_endpoints(self):
        source = Image.new('RGB', (100, 100), (45, 45, 45))
        output = brighten_scene(source)
        self.assertGreater(output.getpixel((50, 50))[0], 80)
        self.assertEqual(brighten_scene(Image.new('RGB', (10, 10), 'black')).getpixel((5, 5)), (0, 0, 0))
        self.assertEqual(brighten_scene(Image.new('RGB', (10, 10), 'white')).getpixel((5, 5)), (255, 255, 255))

    def test_exposure_lift_preserves_colored_skin_and_scenery(self):
        output = brighten_scene(Image.new('RGB', (100, 100), (80, 40, 20)))
        red, green, blue = output.getpixel((50, 50))
        self.assertGreater(red, green)
        self.assertGreater(green, blue)
        self.assertGreater(green, 40)

    def test_complete_generated_poster_is_exported_without_overlays(self):
        from unittest.mock import patch
        source = Image.new('RGB', (1280, 720), '#e17a35')
        with patch('artwork.ImageDraw.ImageDraw.text', autospec=True) as draw_text:
            output = poster_thumbnail(source, SONG, 'romance')
        draw_text.assert_not_called()
        self.assertIsNone(ImageChops.difference(source, output).getbbox())
