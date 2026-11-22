import os
import unittest
from unittest.mock import patch
import workflow as w
import qwen_text


@patch.dict(os.environ, {'TEXT_BACKEND': 'qwen-local', 'STORY_MODEL': qwen_text.MODEL}, clear=True)
class QwenTextTests(unittest.TestCase):
    def test_local_route_uses_reference_runtime_without_remote_fallback(self):
        payload = {'model': qwen_text.MODEL, 'messages': []}
        with patch('qwen_text.request_story', return_value={'ok': True}) as local, patch('workflow.request_groq') as groq, patch('requests.post') as post:
            self.assertEqual(w.request_text('chat/completions', payload), {'ok': True})
        local.assert_called_once_with('chat/completions', payload)
        groq.assert_not_called()
        post.assert_not_called()

    def test_local_model_failure_never_falls_back(self):
        with patch('qwen_text.request_story', side_effect=RuntimeError('local failure')), patch('workflow.request_groq') as groq:
            with self.assertRaisesRegex(RuntimeError, 'local failure'):
                w.request_text('chat/completions', {})
        groq.assert_not_called()

    def test_local_batching_has_no_api_cooldown(self):
        with patch('workflow.time.sleep') as sleep:
            w.text_batch_pause()
        sleep.assert_not_called()
