import unittest
from pipeline import pipeline_failure_message

class PublicationDiagnosticTests(unittest.TestCase):
    def test_local_guard_is_actionable(self):
        message='Drive upload checksum or size verification failed'
        self.assertIn(message,pipeline_failure_message(RuntimeError(message)))

    def test_recovery_and_storage_guards_are_actionable(self):
        for message in (
            'Lyrics checkpoint missing; restore song.json before resuming this stage',
            'DRIVE_FOLDER_ID must identify the dedicated Grow with Rezan folder',
            'Configured Drive folder must belong to the authenticated account',
            'DRIVE_FOLDER_ID must identify an accessible active folder',
            'Multiple kids rhyme folders require reconciliation',
        ):
            with self.subTest(message=message):
                self.assertIn(message, pipeline_failure_message(RuntimeError(message)))

    def test_arbitrary_runtime_error_remains_private(self):
        self.assertNotIn('secret-token',pipeline_failure_message(RuntimeError('secret-token')))
