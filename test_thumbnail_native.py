"""Native thumbnail text is requested from the model, never painted afterward."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from thumbnail_design import complete_thumbnail_prompt, generate_thumbnail


class NativeThumbnailTests(unittest.TestCase):
    def test_prompt_requests_exact_headline_brightness_and_varied_art_direction(self):
        prompts=[complete_thumbnail_prompt('A chess king on the right with dark space on the left, no text.',
                 'WHY FOLLOW HIM?',f'episode-{i}') for i in range(12)]
        self.assertGreaterEqual(len(set(prompts)),6)
        for prompt in prompts:
            self.assertIn('"WHY FOLLOW HIM?"',prompt)
            self.assertIn('saturated clean colors',prompt)
            self.assertIn('unresolved visual question',prompt)
            self.assertNotIn('no text',prompt)
            self.assertNotIn('dark space on the left',prompt)
            self.assertIn('no invented evidence',prompt)

    def test_every_episode_has_a_distinct_storybook_subject_even_after_fallback(self):
        from video_packaging import artwork_candidate
        topics=json.loads(Path('history_topics.json').read_text())
        prompts=[]
        for topic in topics:
            visual=artwork_candidate('Too short',topic)
            self.assertIn(topic['thumbnail_anchor'],visual)
            prompt=complete_thumbnail_prompt(visual,'WHY FOLLOW HIM?',topic['id'])
            self.assertTrue(prompt.startswith('3D storybook illustration'))
            self.assertLess(prompt.index(topic['thumbnail_anchor']),300)
            self.assertNotIn('photography',prompt)
            self.assertNotIn('chess',prompt.lower())
            prompts.append(prompt)
        self.assertEqual(len(set(prompts)),len(topics))

    def test_generator_gets_native_text_flag_and_episode_seed_then_export_preserves_art(self):
        story=dict(thumbnail_prompt='A chess king facing smaller pieces',thumbnail_text='WHY FOLLOW HIM?')
        def generate(prompt,path,**kwargs):
            self.assertTrue(kwargs['allow_text'])
            self.assertEqual(kwargs['style'], 'storybook-3d')
            Image.new('RGB',(1024,576),(220,170,80)).save(path)
        with tempfile.TemporaryDirectory() as temp,patch('image_cpu.generate',side_effect=generate) as model:
            root=Path(temp)
            target=generate_thumbnail(story,root,'episode-a')
            first=model.call_args.kwargs['seed']
            with Image.open(target) as image:
                self.assertEqual(image.size,(1280,720))
                # No added typography, badges, gradients or dimming.
                self.assertLess(max(abs(a-b) for a,b in zip(image.getpixel((100,100)),(220,170,80))),4)
            manifest=json.loads((root/'thumbnail-design.json').read_text())
            self.assertEqual(manifest['text_mode'],'model-generated')
            generate_thumbnail(story,root,'episode-b')
            self.assertNotEqual(first,model.call_args.kwargs['seed'])

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
