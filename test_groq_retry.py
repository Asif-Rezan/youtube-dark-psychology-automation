import unittest
from unittest.mock import Mock, patch
import workflow as w


class GroqRetryTests(unittest.TestCase):
    def response(self, status, headers=None, code='rate_limit_exceeded'):
        return Mock(ok=status == 200, status_code=status, headers=headers or {},
                    json=Mock(return_value={'error': {'code': code}}), content=b'audio')

    def call(self, responses, binary=False):
        return patch('requests.post', side_effect=responses)

    @patch.dict('os.environ', {'GROQ_API_KEY': 'test'})
    def test_multiple_rate_limits_honor_server_delay_then_succeed(self):
        responses = [self.response(429, {'retry-after': '125'}),
                     self.response(429, {'retry-after': '2.5'}), self.response(200)]
        with self.call(responses) as post, patch.object(w.time, 'sleep') as sleep:
            self.assertEqual(w.request_groq('audio', {}, binary=True), b'audio')
        self.assertEqual(post.call_count, 3)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [60, 60, 6, 4])

    @patch.dict('os.environ', {'GROQ_API_KEY': 'test'})
    def test_daily_limit_does_not_retry_before_reset(self):
        with self.call([self.response(429, {'retry-after': '3600'})]) as post, patch.object(w.time, 'sleep') as sleep:
            with self.assertRaisesRegex(RuntimeError, 'retry_after_seconds=3601'):
                w.request_groq('chat', {})
        self.assertEqual(post.call_count, 1)
        sleep.assert_not_called()

    @patch.dict('os.environ', {'GROQ_API_KEY': 'test'})
    def test_missing_header_backoff_is_bounded(self):
        with self.call([self.response(429)] * 8) as post, patch.object(w.time, 'sleep'):
            with self.assertRaisesRegex(RuntimeError, 'budget exhausted'):
                w.request_groq('chat', {})
        self.assertLessEqual(post.call_count, 8)

    @patch.dict('os.environ', {'GROQ_API_KEY': 'test'})
    def test_other_errors_are_not_retried(self):
        with self.call([self.response(401)]) as post, patch.object(w.time, 'sleep') as sleep:
            with self.assertRaisesRegex(RuntimeError, 'HTTP 401'):
                w.request_groq('chat', {})
        self.assertEqual(post.call_count, 1)
        sleep.assert_not_called()

    @patch.dict('os.environ', {'GROQ_API_KEY': 'test'})
    def test_invalid_json_only_retries_once(self):
        with self.call([self.response(400, code='json_validate_failed')] * 2) as post, patch.object(w.time, 'sleep'):
            with self.assertRaisesRegex(RuntimeError, 'HTTP 400'):
                w.request_groq('chat', {})
        self.assertEqual(post.call_count, 2)

    def test_date_and_invalid_header(self):
        with patch.object(w.time, 'time', return_value=0):
            self.assertEqual(w.groq_retry_delay(self.response(429, {'retry-after': 'Thu, 01 Jan 1970 00:02:00 GMT'}), 0), 121)
        self.assertEqual(w.groq_retry_delay(self.response(429, {'retry-after': 'invalid'}), 1), 121)
