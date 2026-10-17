import copy
import unittest
from unittest.mock import Mock, patch
import requests
import workflow as w


@patch.dict('os.environ', {'GROQ_API_KEY': 'groq-test', 'GEMINI_API_KEY': 'gemini-test'})
class ProviderFallbackTests(unittest.TestCase):
    def setUp(self):
        self.provider = patch.object(w, '_text_provider', 'groq')
        self.provider.start()
        self.addCleanup(self.provider.stop)
        self.payload = {'model': 'groq-model', 'messages': [{'role': 'user', 'content': 'Return JSON'}],
            'max_completion_tokens': 100, 'response_format': {'type': 'json_schema',
            'json_schema': {'name': 'test', 'strict': True, 'schema': {'type': 'object'}}}}

    def response(self, status=200, finish='stop', content='{"ok":true}'):
        return Mock(ok=status == 200, status_code=status,
            json=Mock(return_value={'choices': [{'finish_reason': finish, 'message': {'content': content}}]}))

    def test_groq_success_never_calls_gemini(self):
        with patch('requests.post', return_value=self.response()) as post, patch.object(w.time, 'sleep') as sleep:
            w.request_groq('chat/completions', self.payload)
        self.assertEqual(post.call_count, 1)
        sleep.assert_not_called()

    def test_failures_switch_immediately_and_stay_on_gemini(self):
        for failure in (self.response(429), self.response(500), self.response(401),
                        requests.Timeout(), self.response(content='invalid'), self.response(finish='length')):
            with self.subTest(failure=failure), patch.object(w, '_text_provider', 'groq'):
                original = copy.deepcopy(self.payload)
                with patch('requests.post', side_effect=[failure, self.response(), self.response()]) as post, patch.object(w.time, 'sleep') as sleep:
                    w.request_groq('chat/completions', self.payload)
                    w.request_groq('chat/completions', self.payload)
                self.assertEqual(post.call_count, 3)
                self.assertIn('api.groq.com', post.call_args_list[0].args[0])
                self.assertIn('generativelanguage.googleapis.com', post.call_args_list[1].args[0])
                self.assertIn('generativelanguage.googleapis.com', post.call_args_list[2].args[0])
                self.assertEqual(post.call_args_list[1].kwargs['json']['response_format'], self.payload['response_format'])
                self.assertNotEqual(post.call_args_list[1].kwargs['headers'], post.call_args_list[0].kwargs['headers'])
                self.assertEqual(self.payload, original)
                sleep.assert_not_called()

    def test_missing_key_is_clear_and_no_wait(self):
        with patch.dict('os.environ', {'GEMINI_API_KEY': ''}), patch('requests.post', return_value=self.response(429)) as post, patch.object(w.time, 'sleep') as sleep:
            with self.assertRaisesRegex(RuntimeError, 'GEMINI_API_KEY is required'):
                w.request_groq('chat/completions', self.payload)
        self.assertEqual(post.call_count, 1)
        sleep.assert_not_called()

    def test_gemini_failures_do_not_loop_or_accept_invalid_output(self):
        for failure in (self.response(429), self.response(finish='length'), self.response(finish='content_filter'), self.response(content='invalid')):
            with self.subTest(failure=failure), patch.object(w, '_text_provider', 'groq'), patch('requests.post', side_effect=[self.response(429), failure]) as post:
                with self.assertRaisesRegex(RuntimeError, 'Gemini fallback'):
                    w.request_groq('chat/completions', self.payload)
                self.assertEqual(post.call_count, 2)

    def test_audio_is_not_sent_to_text_provider(self):
        with patch('requests.post', return_value=self.response(429)) as post:
            with self.assertRaisesRegex(RuntimeError, 'does not support audio'):
                w.request_groq('audio/speech', {}, binary=True)
        self.assertEqual(post.call_count, 1)
