import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch
from publication import next_publish_time, publish_verified


class PublicationTests(unittest.TestCase):
    def test_72_hours_and_new_york_dst(self):
        for now, expected in [
            ('2026-10-30T05:00:00+00:00', '2026-11-02T11:00:00Z'),
            ('2026-07-01T11:00:00+00:00', '2026-07-05T10:00:00Z'),
            ('2026-07-01T10:00:00+00:00', '2026-07-04T10:00:00Z'),
            ('2026-03-06T10:30:00+00:00', '2026-03-10T10:00:00Z')]:
            self.assertEqual(next_publish_time(datetime.fromisoformat(now)), expected)

    def test_schedule_readback_and_retry_keep_same_time(self):
        client, store = MagicMock(), MagicMock()
        state = {'video_id': 'v'}
        video = {'status': {'privacyStatus': 'private', 'selfDeclaredMadeForKids': False}}
        def readback():
            return {'items': [{'status': {'privacyStatus': 'private', 'publishAt': state['publication']['publish_at']}}]}
        client.videos().list().execute.side_effect = readback
        publish_verified(client, store, 'key', state, video, 'scheduled')
        saved = state['publication']['publish_at']
        self.assertTrue(state['publication']['confirmed'])
        client.videos().update.assert_called_once()
        video['status']['publishAt'] = saved
        publish_verified(client, store, 'key', state, video, 'scheduled')
        client.videos().update.assert_called_once()
        self.assertEqual(state['publication']['publish_at'], saved)

    @patch('publication.time.sleep')
    def test_missing_schedule_readback_fails(self, sleep):
        client, store = MagicMock(), MagicMock()
        client.videos().list().execute.return_value = {'items': [{'status': {'privacyStatus': 'private'}}]}
        state = {'video_id': 'v'}
        with self.assertRaisesRegex(RuntimeError, 'did not confirm'):
            publish_verified(client, store, 'key', state, {'status': {'privacyStatus': 'private'}}, 'scheduled')
        self.assertNotIn('confirmed', state['publication'])

    def test_public_mode(self):
        client, store = MagicMock(), MagicMock()
        client.videos().list().execute.return_value = {'items': [{'status': {'privacyStatus': 'public'}}]}
        state = {'video_id': 'v'}
        publish_verified(client, store, 'key', state, {'status': {'privacyStatus': 'private'}}, 'public')
        self.assertEqual(client.videos().update.call_args.kwargs['body']['status']['privacyStatus'], 'public')
