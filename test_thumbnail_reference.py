"""Thumbnail reference routing, cache invalidation and img2img parameter checks."""
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
from PIL import Image
import image_cpu
from song_images import thumbnail_reference
import test_kids_rhymes
from song_images import image_plan, generate_song_images


class ThumbnailReferenceTests(unittest.TestCase):
    def song(self):
        fixture=test_kids_rhymes.KidsTests()
        fixture.setUp()
        try:
            return fixture.song(480)
        finally:
            fixture.doCleanups()

    def test_only_thumbnail_uses_reference_and_strength_changes_only_its_cache(self):
        song=self.song()
        with patch.dict(os.environ,THUMBNAIL_DENOISE_STRENGTH='0.50'):
            first=image_plan(song)
        with patch.dict(os.environ,THUMBNAIL_DENOISE_STRENGTH='0.6'):
            second=image_plan(song)
        self.assertEqual(first[:-1],second[:-1])
        self.assertNotEqual(first[-1],second[-1])
        self.assertTrue(all('reference_image' not in p for p in first[:-1]))
        self.assertEqual(first[-1]['kind'],'thumbnail')
        self.assertIn('3D storybook',first[-1]['prompt'][:80])

    def test_pool_selection_is_stable_for_retry_and_varies_across_generations(self):
        from song_images import THUMBNAIL_REFERENCES
        expected = {str(p.relative_to(Path(__file__).resolve().parent)) for p in THUMBNAIL_REFERENCES}
        selected = set()
        with patch.dict(os.environ, clear=True):
            for index in range(100):
                with patch.dict(os.environ, SONG_RUN_ID=f'kids-{index}'):
                    first = thumbnail_reference('same-song')
                    self.assertEqual(first, thumbnail_reference('same-song'))
                    self.assertEqual(first['strength'], .50)
                    selected.add(first['reference_image'])
            self.assertEqual(selected, expected)
            self.assertEqual(len(expected), 5)

    def test_changed_reference_content_changes_cache_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'reference.png'
            with patch.dict(os.environ,THUMBNAIL_REFERENCE_IMAGE=str(path)):
                Image.new('RGB',(32,18),'red').save(path)
                first=thumbnail_reference()
                Image.new('RGB',(32,18),'blue').save(path)
                self.assertNotEqual(first['reference_sha256'],thumbnail_reference()['reference_sha256'])

    def test_invalid_or_missing_reference_fails_explicitly(self):
        for value in ('0','-1','1.1','nan'):
            with patch.dict(os.environ,THUMBNAIL_DENOISE_STRENGTH=value):
                with self.assertRaises(ValueError):
                    thumbnail_reference()
        with patch.dict(os.environ,THUMBNAIL_REFERENCE_IMAGE='/missing/thumbnail-reference.png'):
            with self.assertRaises(FileNotFoundError):
                thumbnail_reference()

    def test_generator_routes_reference_without_changing_scene_calls(self):
        song=self.song()
        def worker(prompt,target,**kwargs):
            Image.new('RGB',(32,18),'pink').save(target)
        with tempfile.TemporaryDirectory() as tmp,patch('image_cpu.generate',side_effect=worker) as generate:
            generate_song_images(tmp,song)
            calls=generate.call_args_list
            self.assertTrue(all('reference_image' not in call.kwargs for call in calls[:-1]))
            self.assertTrue(calls[-1].kwargs['reference_image'].exists())
            self.assertEqual(calls[-1].kwargs['strength'],.50)
            generate_song_images(tmp,song)
            self.assertEqual(generate.call_count,len(calls))

    def test_img2img_shares_weights_resizes_reference_and_checks_safety(self):
        torch=types.SimpleNamespace(set_num_threads=Mock(),Generator=Mock())
        base=Mock()
        worker=Mock(side_effect=[
            types.SimpleNamespace(nsfw_content_detected=[True],images=[Image.new('RGB',(256,256))]),
            types.SimpleNamespace(nsfw_content_detected=[False],images=[Image.new('RGB',(256,256),'green')])])
        auto=types.SimpleNamespace(from_pipe=Mock(return_value=worker))
        diffusers=types.SimpleNamespace(DiffusionPipeline=Mock(),DPMSolverMultistepScheduler=Mock(),AutoPipelineForImage2Image=auto)
        with tempfile.TemporaryDirectory() as tmp,patch.object(image_cpu,'_pipeline',base),patch.dict('sys.modules',torch=torch,diffusers=diffusers):
            reference=Path(tmp)/'reference.png';Image.new('RGB',(128,72)).save(reference)
            target=Path(tmp)/'result.png'
            image_cpu.generate('3D storybook kids',target,seed=3,width=256,height=256,steps=20,reference_image=reference,strength=.50)
            auto.from_pipe.assert_called_once_with(base)
            self.assertEqual(worker.call_count,2)
            for call in worker.call_args_list:
                self.assertEqual(call.kwargs['strength'],.50)
                self.assertEqual(call.kwargs['image'].size,(256,256))
            self.assertTrue(target.exists())

    def test_strength_without_reference_is_rejected(self):
        with self.assertRaises(ValueError):
            image_cpu.generate('test','unused.png',seed=1,strength=.50)
