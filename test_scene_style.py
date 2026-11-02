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
        self.assertTrue(prompt.startswith(SCENE_STYLE))
        self.assertIn('opens a sealed envelope', prompt)
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
        self.assertTrue(prompt.startswith(SCENE_STYLE))
        self.assertIn('forked path', prompt)
        client.text_to_image.return_value.save.assert_called_once_with('scene.png')
