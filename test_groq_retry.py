import copy
import os
import unittest
from unittest.mock import Mock, patch
import requests
import workflow as w

@patch.dict(os.environ, {'GROQ_API_KEY': 'primary-test', 'GROQ_API_KEY_FALLBACK': 'backup-test', 'GEMINI_API_KEY': 'gemini-test'}, clear=True)
class ProviderFallbackTests(unittest.TestCase):
    def response(self, status=200, content='{"ok":true}', finish='stop'):
        return Mock(ok=status == 200, status_code=status, headers={}, json=Mock(return_value={
            'choices': [{'finish_reason': finish, 'message': {'content': content}}]}))

    def setUp(self):
        patcher = patch.object(w, '_text_provider', 'groq')
        patcher.start()
        self.addCleanup(patcher.stop)
        sleeper = patch.object(w.time, 'sleep')
        self.sleep = sleeper.start()
        self.addCleanup(sleeper.stop)
        self.payload = {'model': 'test', 'messages': [], 'max_completion_tokens': 100}

    def test_success_uses_only_primary(self):
        with patch('requests.post', return_value=self.response()) as post:
            w.request_groq('chat/completions', self.payload)
        self.assertEqual(post.call_count, 1)
        self.sleep.assert_not_called()

    def test_each_failure_retries_then_uses_backup_before_gemini(self):
        for failure in (self.response(400), self.response(401), self.response(429), self.response(503), requests.Timeout(), self.response(content='bad'), self.response(finish='length')):
            with self.subTest(failure=failure), patch('requests.post', side_effect=[failure]*3+[self.response()]) as post:
                original = copy.deepcopy(self.payload)
                w.request_groq('chat/completions', self.payload)
                self.assertEqual(post.call_count, 4)
                self.assertEqual([c.kwargs['headers']['Authorization'] for c in post.call_args_list], ['Bearer primary-test']*3+['Bearer backup-test'])
                self.assertTrue(all('api.groq.com' in c.args[0] for c in post.call_args_list))
                self.assertEqual(self.payload, original)

    def test_both_keys_fail_then_gemini_and_remember_success(self):
        with patch('requests.post', side_effect=[self.response(503)]*6+[self.response(),self.response()]) as post:
            w.request_groq('chat/completions', self.payload)
            w.request_groq('chat/completions', self.payload)
        self.assertEqual(post.call_count, 8)
        self.assertIn('generativelanguage.googleapis.com', post.call_args_list[6].args[0])

    def test_failed_gemini_does_not_pin_provider(self):
        with patch('requests.post', return_value=self.response(503)) as post:
            with self.assertRaisesRegex(RuntimeError, 'after 4 attempt'):
                w.request_groq('chat/completions', self.payload)
        self.assertEqual(post.call_count, 10)
        self.assertEqual(w._text_provider, 'groq')

    def test_backup_alone_and_duplicate_keys(self):
        for primary in ('', 'backup-test'):
            with patch.dict(os.environ, {'GROQ_API_KEY': primary}), patch('requests.post', side_effect=[self.response(400)]*3+[self.response()]) as post:
                w.request_groq('chat/completions', self.payload)
                self.assertEqual(post.call_count, 4)
            w._text_provider = 'groq'

    def test_audio_does_not_use_gemini(self):
        with patch('requests.post', return_value=self.response(503)) as post:
            with self.assertRaisesRegex(RuntimeError, 'does not support audio'):
                w.request_groq('audio/speech', {}, binary=True)
        self.assertEqual(post.call_count, 6)
