import os
import unittest
from unittest.mock import MagicMock, patch
from test_daily_publish import CleanupTests
from facebook_publish import Facebook, FacebookError, publish, verify_remote, PAGE_ID
from pathlib import Path
import tempfile


class FacebookIsolationTests(unittest.TestCase):
    def test_failed_facebook_preserves_video_but_cleans_other_media(self):
        f = CleanupTests(); f.setUp()
        journal = f.store.load.return_value
        f.store.load.side_effect = [journal, {}]
        from daily_publish import cleanup
        with patch.dict(os.environ, {'FACEBOOK_PUBLISH_ENABLED': 'true'}):
            self.assertFalse(cleanup(f.store, f.run, f.state))
        f.store.client.files().delete.assert_not_called()
        self.assertEqual(journal['deferred_for_facebook'], ['file'])
        self.assertFalse(journal['complete'])
        f.store.load.side_effect = [journal, {'phase': 'scheduled'}]
        with patch.dict(os.environ, {'FACEBOOK_PUBLISH_ENABLED': 'true'}):
            self.assertTrue(cleanup(f.store, f.run, f.state))
        f.store.client.files().delete.assert_called_once_with(fileId='file')

    def test_wrong_page_token_rejected_before_upload(self):
        api = Facebook('secret'); api.request = MagicMock(return_value={'id':'other'})
        with self.assertRaises(FacebookError): api.verify_page()
        self.assertEqual(api.request.call_count, 1)

    def test_initialization_response_loss_never_creates_duplicate(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/'video.mp4'; path.write_bytes(b'video')
            api, state = MagicMock(), {}
            api.request.side_effect = FacebookError('lost response')
            with self.assertRaises(FacebookError):
                publish(api, path, 'video', {'title':'T','description':'D'}, 1800000000, state, lambda:None)
            self.assertTrue(state['initialization_started'])
            with self.assertRaisesRegex(FacebookError, 'response was lost'):
                publish(api, path, 'video', {'title':'T','description':'D'}, 1800000000, state, lambda:None)
            self.assertEqual(api.request.call_count, 1)

    def test_schedule_and_page_must_match(self):
        state = {'video_id':'v','publish_at':1800000000}
        remote = {'id':'v','from':{'id':PAGE_ID},'scheduled_publish_time':1800000000,
                  'status':{'video_status':'ready'}}
        self.assertTrue(verify_remote(remote, state))
        remote['scheduled_publish_time'] += 1
        with self.assertRaises(FacebookError): verify_remote(remote, state)

    def test_errors_never_print_token_or_raw_response(self):
        session = MagicMock(); response = session.request.return_value
        response.status_code = 400
        response.json.return_value = {'error':{'code':190,'message':'secret token url'}}
        with self.assertRaises(FacebookError) as error:
            Facebook('secret',session).request('GET','/v26.0/me')
        self.assertNotIn('secret',str(error.exception))
