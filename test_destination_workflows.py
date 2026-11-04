"""Prevent reference migration from dropping destination identity configuration."""
import os
from pathlib import Path
import unittest
from unittest.mock import patch
import yaml


class DestinationWorkflowTests(unittest.TestCase):
    def test_all_channel_bindings_keep_existing_destination_fallback(self):
        bindings = []
        for path in Path('.github/workflows').glob('*.yml'):
            workflow = yaml.safe_load(path.read_text())
            for name, job in workflow.get('jobs', {}).items():
                value = job.get('env', {}).get('EXPECTED_CHANNEL_ID')
                if value is not None:
                    bindings.append((path.name, name))
                    with self.subTest(workflow=path.name, job=name):
                        self.assertEqual(value, "${{ secrets.EXPECTED_CHANNEL_ID || vars.EXPECTED_CHANNEL_ID || 'UCYjz7d66SsshimfpxZahlhQ' }}")
        self.assertEqual(len(bindings), 6)

    def test_missing_channel_fails_before_refreshing_credentials(self):
        from verify_connections import verify
        with patch.dict(os.environ, {}, clear=True), patch('verify_connections.Credentials') as credentials:
            with self.assertRaisesRegex(RuntimeError, 'Missing configuration: EXPECTED_CHANNEL_ID'):
                verify()
            credentials.from_authorized_user_info.assert_not_called()
