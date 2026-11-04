import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image
import kids_rhymes as kids
from pipeline import validate_song, validate_duration
from song_images import image_plan, generate_song_images

class KidsTests(unittest.TestCase):
    def setUp(self):
        def written(day,identity,seconds,history,draft_path=None):
            return dict(writer_version='qwen-kids-original-v1',outline=dict(title='Duck and Bunny Find a Rainbow',
                characters='A lavender baby elephant and a tiny teal turtle.',
                visual_world='A peach seaside garden with shell paths.',
                description='A new playful story about two kind animal friends discovering a garden rainbow.',
                story_summary='Duck and bunny follow a bright rainbow through the garden.'),
                sections=[[dict(lyric=f'Friendly ducks discover garden number {i}',visual=f'Duckling and bunny exploring flower patch {i}')
                           for i in range((seconds+9)//10)]])
        model=patch('kids_rhymes.write_rhyme',side_effect=written)
        model.start()
        self.addCleanup(model.stop)

    def song(self, seconds=600):
        with patch.dict(os.environ, VIDEO_DURATION_SECONDS=str(seconds)):
            return kids.make_song('2026-10-28', [], generation_id='test')

    def test_lyric_scene_leads_prompt_and_episode_cast_is_preserved(self):
        song = self.song(480)
        prompt = song['scenes'][0]['prompt']
        self.assertTrue(prompt.startswith('Cute colorful 3D storybook cartoon. Two cute human toddlers'))
        self.assertIn('baby elephant and baby turtle', prompt)
        self.assertLess(prompt.index('human toddlers'), prompt.index('baby elephant'))
        self.assertIn('Duckling and bunny exploring flower patch 0',prompt)
        self.assertIn(song['visual_identity']['characters'], prompt)
        self.assertIn(song['visual_identity']['world'], prompt)
        self.assertIn('Cute colorful 3D storybook cartoon', prompt)
        self.assertNotIn('Same fluffy yellow duckling and white bunny', prompt)
        changed = copy.deepcopy(song)
        changed['scenes'][0]['prompt'] = prompt.replace('lavender baby elephant', 'pink baby dragon')
        self.assertNotEqual(image_plan(song)[0], image_plan(changed)[0])

    def test_duration_and_storyboard(self):
        for seconds in (480,600,720):
            song = validate_song(self.song(seconds))
            self.assertEqual(len(song['scenes']),seconds//5)
            self.assertEqual(song['vocal_gender'],'female')
            validate_duration(seconds)
            self.assertEqual(song['bpm'],120)
            self.assertIn('120 BPM',song['prompt'])
            self.assertIn('Continuous lively instrumental backing',song['prompt'])
        for seconds in (479,721):
            with self.assertRaises(ValueError):
                self.song(seconds)
            with self.assertRaises(ValueError):
                validate_duration(seconds)
            self.assertEqual(song['bpm'],120)
            self.assertIn('120 BPM',song['prompt'])
            self.assertIn('Continuous lively instrumental backing',song['prompt'])

    def test_mismatched_storyboard_rejected(self):
        song = self.song()
        song['scenes'][3]['start'] += 1
        with self.assertRaises(ValueError):
            validate_song(song)
        song=self.song()
        song['lyrics'] += '\nextra'
        with self.assertRaises(ValueError):
            validate_song(song)

    def test_unique_scene_seeds_and_complete_shards(self):
        plans=image_plan(self.song(720))
        self.assertEqual(len(plans),145)
        self.assertEqual(len({p['seed'] for p in plans}),145)
        self.assertEqual(len({p['kind'] for p in plans}),145)
        def fake_generate(prompt,target,**kwargs):
            Image.new('RGB',(32,18),'yellow').save(target)
        with tempfile.TemporaryDirectory() as tmp, patch('image_cpu.generate',side_effect=fake_generate) as generate:
            for shard in range(16):
                with patch.dict(os.environ, IMAGE_SHARD=str(shard),IMAGE_SHARDS='16'):
                    generate_song_images(tmp,self.song(720))
                    generate_song_images(tmp,self.song(720))
            self.assertEqual(generate.call_count,145)
            self.assertEqual(len(list(Path(tmp).glob('*-source.png'))),145)

    def test_four_portrait_shards_cover_only_short_scenes_and_resume(self):
        song=self.song(600)
        with patch.dict(os.environ, IMAGE_VARIANT='portrait', CPU_IMAGE_WIDTH='576',
                        CPU_IMAGE_HEIGHT='1024', IMAGE_SHARDS='4', CLIP_START='0', CLIP_SECONDS='40'):
            plans=image_plan(song)
            self.assertEqual(len(plans),8)
            self.assertTrue(all((p['width'],p['height'])==(576,1024) for p in plans))
            self.assertTrue(all('wide landscape' not in p['prompt'] for p in plans))
            def fake_generate(prompt,target,**kwargs):
                self.assertEqual((kwargs['width'],kwargs['height']),(576,1024))
                Image.new('RGB',(72,128),'pink').save(target)
            with tempfile.TemporaryDirectory() as tmp, patch('image_cpu.generate',side_effect=fake_generate) as generate:
                for shard in range(4):
                    with patch.dict(os.environ,IMAGE_SHARD=str(shard)):
                        self.assertEqual(len(generate_song_images(tmp,song)),2)
                        generate_song_images(tmp,song)
                self.assertEqual(generate.call_count,8)
                self.assertEqual(len(list((Path(tmp)/'portrait').glob('scene-*-source.png'))),8)
                self.assertFalse(list(Path(tmp).glob('scene-*-source.png')))
            with patch.dict(os.environ,CLIP_START='20',CLIP_SECONDS='20'):
                self.assertEqual([p['kind'] for p in image_plan(song)],
                                 ['scene-004','scene-005','scene-006','scene-007'])

    def test_render_rejects_missing_scene_before_ffmpeg(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); song=self.song(480)
            (root/'song.json').write_text(json.dumps(song))
            (root/'song.wav').write_bytes(b'fixture')
            Image.new('RGB',(32,18),'pink').save(root/'thumbnail-source.png')
            with patch('pipeline.duration',return_value=480), patch('motion_video.run_ffmpeg') as run:
                with self.assertRaises(FileNotFoundError):
                    kids.render_video(root)
                run.assert_not_called()

    def test_every_refrain_shows_dancing_toddlers_with_their_animal(self):
        from scene_actions import plan_scene,motion_prompt
        song=self.song(480)
        for index,scene in enumerate(song['scenes']):
            self.assertIn('Two cute human toddlers',scene['prompt'][:100])
            self.assertIn('baby elephant',scene['prompt'][:200])
            self.assertTrue(scene['prompt'].startswith('Cute colorful 3D storybook cartoon. Two cute human toddlers'))
            self.assertIn('Cute colorful 3D storybook cartoon',scene['prompt'])
            if index%2:
                prefix=' '.join(scene['prompt'].split()[:65])
                self.assertIn('All dance together', prefix)
                self.assertIn('human toddlers', prefix)
                self.assertIn('baby elephant', prefix)
                self.assertEqual(scene['story_action']['action'],'dance')
                self.assertEqual(plan_scene(motion_prompt(scene))['action'],'dance')
                self.assertNotEqual(scene['prompt'],song['scenes'][index-1]['prompt'])
        plan=image_plan(song)[0]
        self.assertEqual((plan['model'],plan['width'],plan['height'],plan['steps']),
                         ('segmind/SSD-1B',1024,576,16))

if __name__ == '__main__':
    unittest.main()
