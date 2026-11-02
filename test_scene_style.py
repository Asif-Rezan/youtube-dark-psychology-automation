"""Verify video art direction reaches both supported image backends."""
import sys
import types
import unittest
from unittest.mock import Mock, patch
import workflow
from visual_style import SCENE_STYLE


class SceneStyleTests(unittest.TestCase):
    def test_cpu_scene_requests_realism_and_keeps_scene_action_without_typography(self):
        with patch.dict('os.environ', {'IMAGE_BACKEND': 'cpu'}), patch('image_cpu.generate') as generate:
            workflow.make_image('A cautious person opens a sealed envelope', 'scene.png')
        prompt = generate.call_args.args[0]
        self.assertIn(SCENE_STYLE, prompt)
        self.assertTrue(prompt.startswith('A cautious person opens a sealed envelope'))
        self.assertEqual(generate.call_args.kwargs, {})
        self.assertIn('photorealistic', prompt)
        self.assertNotIn('3D storybook', prompt)
        self.assertIn('no text', prompt)

    def test_long_video_style_is_not_duplicated(self):
        import long_video
        self.assertEqual(long_video.HISTORY_STYLE, SCENE_STYLE)
        with patch.dict('os.environ', {'IMAGE_BACKEND': 'cpu'}), patch('image_cpu.generate') as generate:
            workflow.make_image(SCENE_STYLE + '. A tense conversation', 'scene.png')
        self.assertEqual(generate.call_args.args[0].count('documentary photograph'), 1)

    def test_hosted_backend_receives_realistic_scene_style(self):
        client = Mock()
        module = types.SimpleNamespace(InferenceClient=Mock(return_value=client))
        with patch.dict('os.environ', {'IMAGE_BACKEND': 'hf', 'HF_TOKEN': 'test', 'IMAGE_MODEL': 'test'}), patch.dict(sys.modules, {'huggingface_hub': module}):
            workflow.make_image('A figure pauses at a forked path', 'scene.png')
        prompt = client.text_to_image.call_args.kwargs['prompt']
        self.assertIn(SCENE_STYLE, prompt)
        self.assertIn('forked path', prompt)
        client.text_to_image.return_value.save.assert_called_once_with('scene.png')

    def test_person_group_and_object_shots_get_appropriate_framing_and_continuity(self):
        import json
        import tempfile
        from pathlib import Path
        from long_video import refine_visual_plan
        actions = ['Maya quietly closes her notebook after the tense conversation',
                   'Two colleagues exchange cautious glances across an office table',
                   'A sealed envelope lies on a wooden desk']
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/'story.json').write_text(json.dumps(dict(
                protagonist_name='Maya', character_description='Maya, short black hair, blue coat')))
            (root/'plan.json').write_text(json.dumps({'shots': [
                {'index': i, 'visual_action': action} for i, action in enumerate(actions)]}))
            shots = refine_visual_plan(root)['shots']
        self.assertEqual([s['focus'] for s in shots], ['person', 'group', 'object'])
        for action, shot in zip(actions, shots):
            self.assertTrue(shot['prompt'].startswith(action))
            self.assertNotIn('modern clothing', shot['negative_prompt'])
        self.assertIn('short black hair, blue coat', shots[0]['prompt'])
        self.assertIn('Natural skin texture', shots[0]['prompt'])
        self.assertNotIn('Character reference:', shots[1]['prompt'])
        self.assertNotIn('Natural skin texture', shots[2]['prompt'])
        self.assertNotIn('facial expression', shots[2]['prompt'])

    def test_scene_quality_exclusions_preserve_shot_settings_and_do_not_leak(self):
        import os
        with patch.dict(os.environ, {'IMAGE_BACKEND': 'cpu', 'IMAGE_NEGATIVE_PROMPT': 'solo portrait'}):
            def generate(*args, **kwargs):
                self.assertIn('plastic skin', os.environ['IMAGE_NEGATIVE_PROMPT'])
                self.assertIn('solo portrait', os.environ['IMAGE_NEGATIVE_PROMPT'])
            with patch('image_cpu.generate', side_effect=generate):
                workflow.make_image('A group discusses a difficult decision', 'scene.png')
            self.assertEqual(os.environ['IMAGE_NEGATIVE_PROMPT'], 'solo portrait')
            with patch('image_cpu.generate', side_effect=RuntimeError('render failed')):
                with self.assertRaises(RuntimeError):
                    workflow.make_image('An office conversation', 'scene.png')
            self.assertEqual(os.environ['IMAGE_NEGATIVE_PROMPT'], 'solo portrait')
