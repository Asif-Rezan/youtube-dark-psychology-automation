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
        sleeper = patch.object(w.time, 'sleep')
        self.sleep = sleeper.start()
        self.addCleanup(sleeper.stop)
        self.payload = {'model': 'test', 'messages': [], 'max_completion_tokens': 100}

    def test_success_uses_only_primary(self):
        with patch('requests.post', return_value=self.response()) as post:
            w.request_groq('chat/completions', self.payload)
        self.assertEqual(post.call_count, 1)
        self.sleep.assert_not_called()

    def test_each_failure_retries_then_uses_backup(self):
        for failure in (self.response(400), self.response(401), self.response(429), self.response(503), requests.Timeout(), self.response(content='bad'), self.response(finish='length')):
            with self.subTest(failure=failure), patch('requests.post', side_effect=[failure]*3+[self.response()]) as post:
                original = copy.deepcopy(self.payload)
                w.request_groq('chat/completions', self.payload)
                self.assertEqual(post.call_count, 4)
                self.assertEqual([c.kwargs['headers']['Authorization'] for c in post.call_args_list], ['Bearer primary-test']*3+['Bearer backup-test'])
                self.assertTrue(all('api.groq.com' in c.args[0] for c in post.call_args_list))
                self.assertEqual(self.payload, original)

    def test_both_keys_fail_without_calling_gemini(self):
        with patch('requests.post', return_value=self.response(503)) as post:
            with self.assertRaisesRegex(RuntimeError, 'after all configured keys'):
                w.request_groq('chat/completions', self.payload)
        self.assertEqual(post.call_count, 6)
        self.assertTrue(all('api.groq.com' in c.args[0] for c in post.call_args_list))

    def test_backup_alone_and_duplicate_keys(self):
        for primary in ('', 'backup-test'):
            with patch.dict(os.environ, {'GROQ_API_KEY': primary}), patch('requests.post', side_effect=[self.response(400)]*3+[self.response()]) as post:
                with self.assertRaisesRegex(RuntimeError, 'after all configured keys'):
                    w.request_groq('chat/completions', self.payload)
                self.assertEqual(post.call_count, 3)

    def test_audio_does_not_use_gemini(self):
        with patch('requests.post', return_value=self.response(503)) as post:
            with self.assertRaisesRegex(RuntimeError, 'Groq audio request failed'):
                w.request_groq('audio/speech', {}, binary=True)
        self.assertEqual(post.call_count, 6)

    def test_rate_limit_respects_retry_after(self):
        limited = self.response(429)
        limited.headers = {'retry-after': '75.5'}
        with patch('requests.post', side_effect=[limited, self.response()]):
            w.request_groq('chat/completions', self.payload)
        self.sleep.assert_called_once_with(76)

    def test_long_cooldown_switches_to_backup_without_short_retry(self):
        limited = self.response(429)
        limited.headers = {'retry-after': '3600'}
        with patch('requests.post', side_effect=[limited, self.response()]) as post:
            w.request_groq('chat/completions', self.payload)
        self.assertEqual(post.call_count, 2)
        self.assertEqual(post.call_args.kwargs['headers']['Authorization'], 'Bearer backup-test')
        self.sleep.assert_not_called()
