"""Thumbnail reference routing, cache invalidation and img2img parameter checks."""
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
from PIL import Image
import image_cpu
import test_kids_rhymes
from song_images import image_plan,generate_song_images,plan_shard
from test_episode_packaging import fixture_package


class ThumbnailReferenceTests(unittest.TestCase):
    def song(self):
        fixture=test_kids_rhymes.KidsTests();fixture.setUp()
        try:return fixture.song(240)
        finally:fixture.doCleanups()

    def test_thumbnail_references_its_own_episode_scene_not_external_pool(self):
        song=self.song();song.pop('song_form');song['packaging']=fixture_package(song,anchor=18)
        plans=image_plan(song);thumbnail=plans[-1]
        self.assertEqual(thumbnail['reference_scene'],'scene-018')
        self.assertNotIn('reference_image',thumbnail)
        self.assertIn(song['scenes'][18]['prompt'],thumbnail['prompt'])
        self.assertEqual(plan_shard(thumbnail,len(plans)-1,16),18%16)
        self.assertTrue(all('reference_scene' not in p for p in plans[:-1]))
        with patch.dict(os.environ,IMAGE_VARIANT='portrait'):
            self.assertTrue(all('reference_scene' not in p for p in image_plan(song)))

    def test_sharded_thumbnail_waits_for_local_anchor_and_retries_use_cache(self):
        song=self.song();song.pop('song_form');song['packaging']=fixture_package(song,anchor=18)
        def worker(prompt,target,**kwargs):
            if 'reference_image' in kwargs:
                self.assertEqual(kwargs['reference_image'].name,'scene-018-source.png')
                self.assertTrue(kwargs['reference_image'].exists())
            Image.new('RGB',(32,18),'pink').save(target)
        with tempfile.TemporaryDirectory() as tmp,patch('image_cpu.generate',side_effect=worker) as generate:
            for shard in range(16):
                with patch.dict(os.environ,IMAGE_SHARD=str(shard),IMAGE_SHARDS='16'):
                    generate_song_images(tmp,song)
                    before=generate.call_count
                    generate_song_images(tmp,song)
                    self.assertEqual(before,generate.call_count)
            self.assertEqual(generate.call_count,len(song['scenes'])+1)
            refs=[c for c in generate.call_args_list if 'reference_image' in c.kwargs]
            self.assertEqual(len(refs),1)

    def test_changed_anchor_pixels_invalidate_only_thumbnail_cache(self):
        song=self.song()
        def worker(prompt,target,**kwargs):Image.new('RGB',(32,18),'pink').save(target)
        with tempfile.TemporaryDirectory() as tmp,patch('image_cpu.generate',side_effect=worker) as generate:
            generate_song_images(tmp,song);before=generate.call_count
            Image.new('RGB',(32,18),'blue').save(Path(tmp)/'scene-000-source.png')
            generate_song_images(tmp,song)
            self.assertEqual(generate.call_count,before+1)
            self.assertIn('reference_image',generate.call_args.kwargs)

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
