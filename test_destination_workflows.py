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
        self.assertEqual(len(bindings), 7)

    def test_missing_channel_fails_before_refreshing_credentials(self):
        from verify_connections import verify
        with patch.dict(os.environ, {}, clear=True), patch('verify_connections.Credentials') as credentials:
            with self.assertRaisesRegex(RuntimeError, 'Missing configuration: EXPECTED_CHANNEL_ID'):
                verify()
            credentials.from_authorized_user_info.assert_not_called()


    def test_generation_preflight_runs_before_lyrics_with_publication_bindings(self):
        workflow = yaml.safe_load(Path('.github/workflows/music.yml').read_text())
        steps = workflow['jobs']['lyrics']['steps']
        check = next(step for step in steps if step.get('name') == 'Verify publication accounts before generation')
        generation = next(step for step in steps if step.get('name') == 'Write original AI kids lyrics and five-second storyboard')
        self.assertLess(steps.index(check), steps.index(generation))
        self.assertEqual(check['if'], "vars.PUBLISH_ENABLED == 'true'")
        for name in ('EXPECTED_CHANNEL_ID', 'YOUTUBE_TOKEN_JSON', 'DRIVE_TOKEN_JSON', 'DRIVE_FOLDER_ID'):
            self.assertEqual(check['env'][name], workflow['jobs']['publish']['env'][name])
        self.assertIn('load_settings()', check['run'])
        self.assertIn('python verify_connections.py', check['run'])


    def test_finished_recovery_has_independent_facebook_and_guarded_cleanup(self):
        jobs=yaml.safe_load(Path('.github/workflows/recover-publication.yml').read_text())['jobs']
        self.assertEqual(jobs['facebook']['needs'], 'recover')
        self.assertEqual(jobs['facebook']['with']['source_run'], '${{ inputs.source_run }}')
        self.assertEqual(jobs['cleanup']['needs'], 'recover')
        self.assertIn("needs.recover.result == 'success'", jobs['cleanup']['if'])
        self.assertTrue(any('cleanup_drive.py' in step.get('run', '') for step in jobs['cleanup']['steps']))
