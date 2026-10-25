import json
import os
import unittest
from unittest.mock import Mock, patch
import workflow as w
import qwen_text


@patch.dict(os.environ, {'TEXT_BACKEND': 'qwen-local'}, clear=True)
class QwenTextTests(unittest.TestCase):
    def test_local_route_preserves_schema_and_never_calls_groq(self):
        payload = {'model': 'old', 'messages': [{'role': 'user', 'content': 'Write JSON'}],
                   'response_format': {'type': 'json_schema', 'json_schema': {'schema': {'type': 'object'}}},
                   'max_completion_tokens': 100, 'reasoning_effort': 'low'}
        response = Mock(ok=True, json=Mock(return_value={'choices': [
            {'finish_reason': 'stop', 'message': {'content': '{"ok":true}'}}]}))
        with patch('requests.post', return_value=response) as post, patch('workflow.request_groq') as groq:
            w.request_text('chat/completions', payload)
        groq.assert_not_called()
        args = post.call_args
        self.assertEqual(args.args[0], 'http://127.0.0.1:8080/v1/chat/completions')
        self.assertEqual(args.kwargs['json']['model'], 'Qwen/Qwen3.5-9B')
        self.assertEqual(args.kwargs['json']['response_format'], payload['response_format'])
        self.assertFalse(args.kwargs['json']['chat_template_kwargs']['enable_thinking'])
        self.assertNotIn('reasoning_effort', args.kwargs['json'])
        self.assertEqual(args.kwargs['json']['max_tokens'], 100)

    def test_remote_url_rejected(self):
        with patch.dict(os.environ, {'QWEN_BASE_URL': 'https://example.com/v1'}), patch('requests.post') as post:
            with self.assertRaisesRegex(RuntimeError, 'loopback'):
                qwen_text.request({})
        post.assert_not_called()

    def test_invalid_json_and_truncation_fail_without_provider_fallback(self):
        for finish, content in [('length', '{"ok":true}'), ('stop', 'bad'), ('stop', '[]')]:
            response = Mock(ok=True, json=Mock(return_value={'choices': [
                {'finish_reason': finish, 'message': {'content': content}}]}))
            with patch('requests.post', return_value=response), patch('workflow.request_groq') as groq:
                with self.assertRaisesRegex(RuntimeError, 'incomplete JSON'):
                    w.request_text('chat/completions', {})
                groq.assert_not_called()

    def test_local_batching_has_no_api_cooldown(self):
        with patch('workflow.time.sleep') as sleep:
            w.text_batch_pause()
        sleep.assert_not_called()
