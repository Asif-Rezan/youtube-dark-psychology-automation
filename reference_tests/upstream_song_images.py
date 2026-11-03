import datetime as dt
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch, Mock
from PIL import Image

import image_cpu
from song_images import image_plan, generate_song_images, scene_detail, VISUAL_STYLE
from pipeline import metadata_tags, song_profile, SONG_PROFILES

SONG = dict(title='नई सुबह', lyrics='नई सुबह में फिर से जीना है', prompt='Hopeful Hindi folk pop',
            visual_mood='healing', tags=['Hindi Folk Song', 'hindi folk song', 'नई सुबह'])


class SongImageTests(unittest.TestCase):
    def test_distinct_purpose_and_song_seeds(self):
        first = image_plan(SONG)
        second = image_plan(dict(SONG, lyrics='तेरे साथ चलना है'))
        self.assertNotEqual(first[0]['seed'], first[1]['seed'])
        self.assertNotEqual(first[0]['seed'], second[0]['seed'])
        self.assertNotEqual(first[0]['prompt'], first[1]['prompt'])
        self.assertEqual(first, image_plan(SONG))
        self.assertTrue(all(item['revision'] == image_cpu.REVISION for item in first))

    def test_framing_survives_long_scene_prompts_and_purposes_stay_distinct(self):
        long_scene = 'Adult South Asian couple sharing a quiet reunion under a courtyard lamp ' + 'long scenery description ' * 60
        plans = image_plan(dict(SONG, visual_mood='romance', background_prompt=long_scene, thumbnail_prompt=long_scene))
        self.assertTrue(plans[0]['prompt'].startswith('Cinematic photograph. Beautiful adult South Asian couple'))
        self.assertIn('Wide environmental scene', plans[0]['prompt'])
        self.assertIn('Close chest-up two-shot', plans[1]['prompt'])
        self.assertIn('both faces distinct and fully visible', plans[1]['prompt'])
        for plan in plans:
            self.assertLessEqual(len(plan['prompt'].split()), 65)
            self.assertIn('courtyard lamp', plan['prompt'])
            self.assertIn('fully clothed', plan['prompt'])
            self.assertNotIn('Hopeful Hindi folk pop', plan['prompt'])

    def test_thumbnail_and_background_are_text_free_for_any_hook(self):
        for hook in ('NAI SUBAH', 'TERE SAATH 2026', 'तेरे साथ'):
            for plan in image_plan(dict(SONG, thumbnail_text=hook)):
                self.assertFalse(plan['allow_text'])
                self.assertIn('no text', plan['prompt'])
                self.assertNotIn(hook, plan['prompt'])
                self.assertNotIn('Title "', plan['prompt'])
                self.assertIn('typography', plan['negative_prompt'])
                self.assertEqual(plan['visual_style'], VISUAL_STYLE)
                self.assertEqual(plan['guidance_scale'], image_cpu.GUIDANCE_SCALE)

    def test_moods_use_young_adult_story_relevant_subjects(self):
        for mood in ('romance', 'heartbreak', 'healing'):
            plans = image_plan(dict(SONG, visual_mood=mood))
            for plan in plans:
                self.assertIn('25-35', plan['prompt'])
            if mood == 'healing':
                self.assertIn('woman', plans[1]['prompt'])
                self.assertIn('hopeful', plans[1]['prompt'])
            else:
                self.assertIn('couple', plans[1]['prompt'])
                self.assertIn('both faces distinct', plans[1]['prompt'])
        self.assertIn('turned apart', image_plan(dict(SONG, visual_mood='heartbreak'))[1]['prompt'])

    def test_legacy_poster_and_old_man_instructions_do_not_return(self):
        scene = ('An elderly man beside a rainy bookshop window. '
                 'Title TERE SAATH with yellow lettering and red brushwork. '
                 'Poster face on the left side.')
        for plan in image_plan(dict(SONG, visual_mood='romance', background_prompt=scene, thumbnail_prompt=scene)):
            self.assertNotIn('elderly', plan['prompt'])
            self.assertNotIn('Title', plan['prompt'])
            self.assertNotIn('lettering', plan['prompt'])
            self.assertIn('rainy bookshop window', plan['prompt'])
        self.assertIn('old bookshop', scene_detail('Adult couple reuniting in an old bookshop', '', 'romance'))

    def test_checkpoint_reuses_only_matching_song_and_prompt(self):
        def generate(prompt, target, seed, allow_text=False):
            Image.new('RGB', (256, 256), 'navy').save(target)
        with tempfile.TemporaryDirectory() as temp, patch('image_cpu.generate', side_effect=generate) as worker:
            root = Path(temp)
            generate_song_images(root, SONG)
            self.assertEqual(worker.call_count, 2)
            generate_song_images(root, SONG)
            self.assertEqual(worker.call_count, 2)
            generate_song_images(root, dict(SONG, thumbnail_prompt='New scene of a hopeful adult watching the sunrise'))
            self.assertEqual(worker.call_count, 3)
            generate_song_images(root, dict(SONG, lyrics='एक नया गीत'))
            self.assertEqual(worker.call_count, 5)

    def test_old_lettered_poster_cache_is_regenerated(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            previous = {plan['kind']: {**plan, 'visual_style': 'old-poster', 'allow_text': True}
                        for plan in image_plan(SONG)}
            for kind in previous:
                Image.new('RGB', (256, 256), 'navy').save(root/f'{kind}-source.png')
            (root/'image-manifest.json').write_text(json.dumps(previous))
            def generate(prompt, target, seed, allow_text=False):
                self.assertFalse(allow_text)
                Image.new('RGB', (256, 256), 'teal').save(target)
            with patch('image_cpu.generate', side_effect=generate) as worker:
                generate_song_images(root, SONG)
            self.assertEqual(worker.call_count, 2)

    def test_partial_failure_keeps_first_image_for_retry(self):
        def generate(prompt, target, seed, allow_text=False):
            if 'thumbnail' in str(target):
                raise RuntimeError('interrupted')
            Image.new('RGB', (256, 256), 'navy').save(target)
        with tempfile.TemporaryDirectory() as temp, patch('image_cpu.generate', side_effect=generate):
            with self.assertRaises(RuntimeError):
                generate_song_images(Path(temp), SONG)
            manifest = json.loads((Path(temp)/'image-manifest.json').read_text())
            self.assertIn('background', manifest)
            self.assertNotIn('thumbnail', manifest)

    def test_safety_rejected_output_is_never_saved(self):
        worker = Mock(return_value=types.SimpleNamespace(nsfw_content_detected=[True], images=[Image.new('RGB', (256, 256))]))
        torch = types.SimpleNamespace(set_num_threads=Mock(), Generator=Mock())
        diffusers = types.SimpleNamespace(DiffusionPipeline=Mock(), DPMSolverMultistepScheduler=Mock())
        with tempfile.TemporaryDirectory() as temp, patch.object(image_cpu, '_pipeline', worker), patch.dict('sys.modules', {'torch': torch, 'diffusers': diffusers}):
            path = Path(temp)/'scene.png'
            with self.assertRaises(image_cpu.ImageSafetyBlocked):
                image_cpu.generate('Adult couple walking in a park', path, seed=123)
            self.assertEqual(worker.call_count, 10)
            self.assertFalse(path.exists())

    def test_diffusion_always_suppresses_text_and_preserves_safety(self):
        worker = Mock(return_value=types.SimpleNamespace(nsfw_content_detected=[False], images=[Image.new('RGB', (256, 256))]))
        torch = types.SimpleNamespace(set_num_threads=Mock(), Generator=Mock())
        diffusers = types.SimpleNamespace(DiffusionPipeline=Mock(), DPMSolverMultistepScheduler=Mock())
        with tempfile.TemporaryDirectory() as temp, patch.object(image_cpu, '_pipeline', worker), patch.dict('sys.modules', {'torch': torch, 'diffusers': diffusers}):
            image_cpu.generate('A beautiful adult couple in a bookshop', Path(temp)/'clean.png', seed=3)
            negative = worker.call_args.kwargs['negative_prompt']
            for term in ('text', 'letters', 'typography', 'watermark', 'elderly', 'fused faces'):
                self.assertIn(term, negative)
            calls = worker.call_count
            with self.assertRaisesRegex(ValueError, 'text-free'):
                image_cpu.generate('Old poster title', Path(temp)/'bad.png', seed=3, allow_text=True)
            self.assertEqual(worker.call_count, calls)

    def test_metadata_tags_are_unique_and_fit_upload_limit(self):
        tags = metadata_tags(SONG)
        self.assertEqual(len([t for t in tags if t.lower() == 'hindi folk song']), 1)
        tags = metadata_tags(dict(SONG, tags=['a'*38 + str(i) for i in range(30)]))
        self.assertLessEqual(sum(len(t) + (2 if ' ' in t else 0) + 1 for t in tags), 480)

    def test_daily_rotation_covers_all_song_styles_without_history_access(self):
        start = dt.date(2026, 10, 26)
        profiles = [song_profile((start + dt.timedelta(days=i)).isoformat()) for i in range(8)]
        self.assertEqual(set(profiles), set(SONG_PROFILES))


if __name__ == '__main__':
    unittest.main()
