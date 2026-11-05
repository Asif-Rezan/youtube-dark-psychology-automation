import unittest
from pipeline import pipeline_failure_message

class PublicationDiagnosticTests(unittest.TestCase):
    def test_local_guard_is_actionable(self):
        message='Drive upload checksum or size verification failed'
        self.assertIn(message,pipeline_failure_message(RuntimeError(message)))

    def test_arbitrary_runtime_error_remains_private(self):
        self.assertNotIn('secret-token',pipeline_failure_message(RuntimeError('secret-token')))


class PublicationPreflightTests(unittest.TestCase):
    def test_missing_configuration_stops_before_storage_network_or_local_outputs(self):
        import os
        import contextlib
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        import pipeline
        complete = dict.fromkeys(pipeline.PUBLICATION_CONFIGURATION, 'test-only')
        for missing in pipeline.PUBLICATION_CONFIGURATION:
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as tmp, contextlib.chdir(tmp):
                environment = {key: value for key, value in complete.items() if key != missing}
                with patch.dict(os.environ, environment, clear=True), patch('pipeline.Store') as store, patch('pipeline.youtube_client') as youtube:
                    with self.assertRaises(RuntimeError) as caught:
                        pipeline.run('saved-episode')
                    diagnostic = pipeline.pipeline_failure_message(caught.exception)
                    self.assertIn('[configuration_missing]', diagnostic)
                    self.assertIn(missing, diagnostic)
                    self.assertIn('recovery on current main', diagnostic)
                    store.assert_not_called()
                    youtube.assert_not_called()
                    self.assertFalse(Path('output').exists())

    def test_missing_channel_stops_youtube_before_constructing_client(self):
        import os
        from unittest.mock import patch
        from pipeline import youtube_client
        with patch.dict(os.environ, {}, clear=True), patch('googleapiclient.discovery.build') as build:
            with self.assertRaisesRegex(RuntimeError, 'Missing configuration: EXPECTED_CHANNEL_ID'):
                youtube_client()
            build.assert_not_called()

    def test_untrusted_configuration_error_is_not_echoed(self):
        error=RuntimeError('Missing configuration: secret-token-access-token')
        self.assertNotIn('secret-token', pipeline_failure_message(error))
