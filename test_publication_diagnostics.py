import unittest
from pipeline import pipeline_failure_message

class PublicationDiagnosticTests(unittest.TestCase):
    def test_local_guard_is_actionable(self):
        message='Drive upload checksum or size verification failed'
        self.assertIn(message,pipeline_failure_message(RuntimeError(message)))

    def test_arbitrary_runtime_error_remains_private(self):
        self.assertNotIn('secret-token',pipeline_failure_message(RuntimeError('secret-token')))
