import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageChops
import recurring_character as character
import workflow


class RecurringCharacterTests(unittest.TestCase):
    def test_reference_asset_has_real_transparency_and_visible_blue_eye(self):
        with Image.open(character.ASSET) as image:
            self.assertEqual(image.mode, 'RGBA')
            self.assertEqual(image.getextrema()[3], (0, 255))
            self.assertGreater(sum(b > r*1.5 and b > g and a > 200
                                   for r,g,b,a in image.getdata()), 5000)

    def test_every_cpu_scene_has_identical_host_and_clear_caption_strip(self):
        with tempfile.TemporaryDirectory() as temp:
            for index in range(4):
                path = Path(temp)/f'shot-{index:03}.png'
                def generate(prompt, target):
                    self.assertIn('uncluttered for the recurring illustrated narrator', prompt)
                    Image.new('RGB',(1024,576),(110,50,50)).save(target)
                with patch.dict('os.environ', {'IMAGE_BACKEND':'cpu'}), patch('image_cpu.generate', side_effect=generate):
                    workflow.make_image('Two rivals discuss a decision', path)
                with Image.open(path) as result:
                    base = Image.new('RGB',result.size,(110,50,50))
                    delta = ImageChops.difference(result,base)
                    self.assertIsNotNone(delta.getbbox())
                    # The mascot ends above the subtitles rather than hiding them.
                    self.assertIsNone(delta.crop((0,520,1024,576)).getbbox())

    def test_missing_asset_stops_before_an_unbranded_image_can_be_used(self):
        with patch.object(character, 'ASSET', Path('/missing/reference-character.png')):
            with self.assertRaises(FileNotFoundError):
                character.composite_host(Image.new('RGB',(1024,576)))

    def test_old_scene_cache_is_regenerated_then_current_cache_is_reused(self):
        import long_video
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            plan = {'storyboard_verified':True, 'scene_composition_version':4,
                    'character_version':character.VERSION, 'character_sha256':character.asset_hash(),
                    'shots':[{'index':0,'seed':42,'prompt':'A fraying rope','duration':7}]}
            (root/'plan.json').write_text(json.dumps(plan))
            Image.new('RGB',(1024,576),'red').save(root/'shot-000.png')
            (root/'shot-000.mp4').write_bytes(b'old clip')
            def make_image(prompt,path):
                Image.new('RGB',(1024,576),'blue').save(path)
            with patch('workflow.make_image', side_effect=make_image) as generate, \
                 patch('scene_check.check_scene', return_value={'passed':True}), \
                 patch('long_video.picture_clip', side_effect=lambda image, seconds, path: path.write_bytes(b'new clip')) as clip:
                long_video.generate_shard(0,root,count=1)
                long_video.generate_shard(0,root,count=1)
            self.assertEqual(generate.call_count,1)
            self.assertEqual(clip.call_count,1)
            self.assertEqual((root/'shot-000.mp4').read_bytes(),b'new clip')
