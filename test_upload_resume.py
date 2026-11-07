import unittest
from unittest import mock


class UploadResumeTest(unittest.TestCase):
    def test_read_timeout_resumes_same_upload(self):
        from pipeline import upload_resumable
        request = mock.Mock()
        request.next_chunk.side_effect = [(None, None), TimeoutError('The read operation timed out'),
                                          (None, {'id': 'vid'})]
        self.assertEqual(upload_resumable(request, sleep=lambda _: None), {'id': 'vid'})
        self.assertEqual(request.next_chunk.call_count, 3)

    def test_permanent_error_is_not_retried(self):
        from pipeline import upload_resumable
        request = mock.Mock()
        request.next_chunk.side_effect = ValueError('bad')
        with self.assertRaises(ValueError):
            upload_resumable(request, sleep=lambda _: None)
        self.assertEqual(request.next_chunk.call_count, 1)

    def test_gives_up_after_limit(self):
        from pipeline import upload_resumable
        request = mock.Mock()
        request.next_chunk.side_effect = TimeoutError()
        with self.assertRaises(TimeoutError):
            upload_resumable(request, attempts=3, sleep=lambda _: None)
        self.assertEqual(request.next_chunk.call_count, 3)


if __name__ == '__main__':
    unittest.main()
