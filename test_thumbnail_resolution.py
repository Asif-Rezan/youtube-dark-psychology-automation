import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from PIL import Image
from thumbnail_export import export_thumbnail,MAX_BYTES
import test_kids_rhymes
from song_images import image_plan


class ThumbnailResolutionTests(unittest.TestCase):
    def song(self):
        fixture=test_kids_rhymes.KidsTests()
        fixture.setUp()
        try:
            return fixture.song(480)
        finally:
            fixture.doCleanups()

    def test_thumbnail_has_native_hd_independent_from_scene_dimensions(self):
        with patch.dict(os.environ,CPU_IMAGE_WIDTH='1024',CPU_IMAGE_HEIGHT='576',CPU_IMAGE_STEPS='20'):
            plans=image_plan(self.song())
            self.assertTrue(all((p['width'],p['height'])==(1024,576) for p in plans[:-1]))
            self.assertEqual((plans[-1]['width'],plans[-1]['height']),(1344,768))
            first=plans[:-1]
            with patch.dict(os.environ,THUMBNAIL_IMAGE_WIDTH='1280',THUMBNAIL_IMAGE_HEIGHT='720'):
                other=image_plan(self.song())
                self.assertEqual(first,other[:-1])
                self.assertNotEqual(plans[-1],other[-1])

    def test_bad_thumbnail_dimensions_fail_before_model_generation(self):
        with patch.dict(os.environ,THUMBNAIL_IMAGE_WIDTH='1920',THUMBNAIL_IMAGE_HEIGHT='1080'):
            with self.assertRaises(ValueError):
                image_plan(self.song())
        with patch.dict(os.environ,THUMBNAIL_IMAGE_WIDTH='1024',THUMBNAIL_IMAGE_HEIGHT='1024'):
            with self.assertRaises(ValueError):
                image_plan(self.song())

    def test_full_hd_export_meets_byte_budget_even_for_noisy_artwork(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            data=np.random.default_rng(10).integers(0,256,(1080,1920,3),dtype=np.uint8)
            Image.fromarray(data).save(root/'source.png')
            metadata=export_thumbnail(root/'source.png',root/'thumbnail.jpg')
            with Image.open(root/'thumbnail.jpg') as image:
                self.assertEqual(image.size,(1920,1080))
                self.assertEqual(image.format,'JPEG')
            self.assertLessEqual((root/'thumbnail.jpg').stat().st_size,MAX_BYTES)
            self.assertLess(metadata['quality'],95)


    def test_native_thumbnail_loses_only_six_pixels_from_top_and_bottom(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            data=np.zeros((768,1344,3),dtype=np.uint8)
            data[:]=[0,0,255]
            data[:6]=[255,0,0]
            data[-6:]=[255,0,0]
            Image.fromarray(data).save(root/'native.png')
            export_thumbnail(root/'native.png',root/'thumbnail.jpg')
            with Image.open(root/'thumbnail.jpg') as image:
                self.assertEqual(image.size,(1920,1080))
                for y in (0,1079):
                    r,g,b=image.getpixel((960,y))
                    self.assertGreater(b,r+100)
