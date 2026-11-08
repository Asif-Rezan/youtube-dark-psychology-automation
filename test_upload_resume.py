import io
import json
import unittest
from unittest import mock


class UploadResumeTest(unittest.TestCase):
    def test_transport_preserves_resumable_308_and_timeout(self):
        from pipeline import youtube_http_transport, YOUTUBE_HTTP_TIMEOUT
        http = youtube_http_transport()
        self.assertNotIn(308, http.redirect_codes)
        self.assertIn(301, http.redirect_codes)
        self.assertIn(302, http.redirect_codes)
        self.assertEqual(http.timeout, YOUTUBE_HTTP_TIMEOUT)

    def test_authenticated_client_uses_upload_safe_transport(self):
        from pipeline import youtube_client, YOUTUBE_HTTP_TIMEOUT
        client = mock.Mock()
        client.channels.return_value.list.return_value.execute.return_value = {'items': [{'id': 'channel'}]}
        with mock.patch.dict('os.environ', {'EXPECTED_CHANNEL_ID': 'channel', 'YOUTUBE_TOKEN_JSON': '{}'}), \
                mock.patch('google.oauth2.credentials.Credentials.from_authorized_user_info'), \
                mock.patch('googleapiclient.discovery.build', return_value=client) as build:
            self.assertIs(youtube_client(), client)
        transport = build.call_args.kwargs['http'].http
        self.assertNotIn(308, transport.redirect_codes)
        self.assertEqual(transport.timeout, YOUTUBE_HTTP_TIMEOUT)

    def test_real_client_continues_after_308_without_location(self):
        import httplib2
        from googleapiclient.http import HttpRequest, MediaIoBaseUpload
        from pipeline import youtube_http_transport, upload_resumable
        http = youtube_http_transport()
        # Exercise httplib2's real redirect handling and googleapiclient's
        # real chunk state machine; only the network connection is mocked.
        responses = [
            (httplib2.Response({'status': '200', 'location': 'https://upload.example/session'}), b''),
            (httplib2.Response({'status': '308', 'range': 'bytes=0-3'}), b''),
            (httplib2.Response({'status': '200'}), b'{"id":"vid"}'),
        ]
        request = HttpRequest(http, lambda response, content: json.loads(content),
            'https://upload.example/start', method='POST', body='{}',
            resumable=MediaIoBaseUpload(io.BytesIO(b'abcdefgh'), 'video/mp4',
                                      chunksize=4, resumable=True))
        with mock.patch.object(http, '_conn_request', side_effect=responses) as network:
            self.assertEqual(upload_resumable(request, sleep=lambda _: None), {'id': 'vid'})
        self.assertEqual(network.call_count, 3)
        self.assertEqual(request.resumable_progress, 4)

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
