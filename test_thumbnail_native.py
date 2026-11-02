"""Readable typography and concise thumbnail artwork generation."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image, ImageChops
from thumbnail_design import complete_thumbnail_prompt, generate_thumbnail, art_direction


class ThumbnailTests(unittest.TestCase):
    def test_prompt_is_concise_subject_specific_and_does_not_request_letters(self):
        prompt = complete_thumbnail_prompt('An anxious adult notices strings pulling one wrist.',
                                          'WHO CONTROLS YOU?', 'episode-a')
        self.assertIn('An anxious adult', prompt)
        self.assertIn('mature psychological drama', prompt)
        self.assertNotIn('WHO CONTROLS YOU', prompt)
        self.assertLess(len(prompt.split()), 75)
        self.assertIn('uncluttered', prompt)
        self.assertEqual(art_direction('episode-a'), art_direction('episode-a'))

    def test_export_has_exact_type_mobile_preview_and_episode_seed(self):
        story = dict(thumbnail_prompt='An anxious adult notices strings pulling one wrist',
                     thumbnail_text='WHO CONTROLS YOU?')
        def generate(prompt, path, **kwargs):
            self.assertFalse(kwargs.get('allow_text', False))
            self.assertEqual(kwargs['style'], 'storybook-3d')
            Image.new('RGB', (1024,576), (100,120,140)).save(path)
        with tempfile.TemporaryDirectory() as temp, patch('image_cpu.generate', side_effect=generate) as model:
            root = Path(temp)
            target = generate_thumbnail(story, root, 'episode-a')
            first = model.call_args.kwargs['seed']
            with Image.open(target) as image:
                self.assertEqual(image.size, (1280,720))
                # White/yellow glyphs must be visible over the constant artwork.
                pixels = list(image.getdata())
                self.assertGreater(sum(r>210 and g>190 and b<140 for r,g,b in pixels), 500)
            with Image.open(root/'thumbnail-mobile.jpg') as mobile:
                self.assertEqual(mobile.size, (320,180))
            manifest = json.loads((root/'thumbnail-design.json').read_text())
            self.assertEqual(manifest['text'], 'WHO CONTROLS YOU?')
            self.assertEqual(manifest['text_mode'], 'composited-exact')
            generate_thumbnail(story, root, 'episode-b')
            self.assertNotEqual(first, model.call_args.kwargs['seed'])

    def test_diffusion_allows_letters_only_for_thumbnail_requests(self):
        import types
        import image_cpu
        from unittest.mock import Mock
        model=Mock(return_value=types.SimpleNamespace(
            nsfw_content_detected=[False],images=[Image.new('RGB',(256,256),'yellow')]))
        torch=types.SimpleNamespace(set_num_threads=lambda _:None,
            Generator=lambda **kwargs:types.SimpleNamespace(manual_seed=lambda seed:seed))
        with tempfile.TemporaryDirectory() as temp,patch.object(image_cpu,'_pipeline',model),patch.dict(
                'sys.modules',{'torch':torch,'diffusers':types.SimpleNamespace(
                    DiffusionPipeline=object,DPMSolverMultistepScheduler=object)}):
            image_cpu.generate('Bright image with WHY FOLLOW HIM?',Path(temp)/'thumb.png',allow_text=True,seed=123)
            sent=model.call_args.kwargs
            self.assertNotIn('text, letters',sent['negative_prompt'])
            self.assertIn('misspelled words',sent['negative_prompt'])
            self.assertEqual(sent['generator'],123)
            image_cpu.generate('3D storybook scene',Path(temp)/'3d.png',allow_text=True,style='storybook-3d')
            self.assertNotIn('3D render',model.call_args.kwargs['negative_prompt'])
            self.assertNotIn('CGI',model.call_args.kwargs['negative_prompt'])
            image_cpu.generate('Text-free video scene',Path(temp)/'scene.png')
            self.assertIn('text, letters',model.call_args.kwargs['negative_prompt'])
            self.assertIn('3D render',model.call_args.kwargs['negative_prompt'])
