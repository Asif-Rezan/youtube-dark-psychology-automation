import copy
import unittest
from youtube_metadata import public_description, upload_body, verify_upload_settings


class UploadMetadataTests(unittest.TestCase):
    def setUp(self):
        self.body = upload_body({'title': 'Dark Psychology: Recognizing Manipulation',
                                 'tags': ['dark psychology', 'manipulation']}, 'Educational description')

    def test_explicit_requested_settings(self):
        verify_upload_settings(self.body)
        self.assertEqual(self.body['snippet']['categoryId'], '24')
        self.assertEqual(self.body['snippet']['defaultAudioLanguage'], 'en')
        self.assertTrue(self.body['status']['containsSyntheticMedia'])
        self.assertIs(self.body['paidProductPlacementDetails']['hasPaidProductPlacement'], False)
        self.assertEqual(self.body['status']['privacyStatus'], 'private')
        self.assertNotIn('academicSystem', self.body['snippet'])

    def test_every_remote_setting_is_checked(self):
        for section in ('snippet', 'status', 'paidProductPlacementDetails'):
            fields = ('categoryId', 'defaultLanguage', 'defaultAudioLanguage') if section == 'snippet' else (
                'containsSyntheticMedia',) if section == 'status' else ('hasPaidProductPlacement',)
            for field in fields:
                if field == 'hasPaidProductPlacement':
                    continue  # Omitted optional false is YouTube's no-promotion default.
                with self.subTest(field=field):
                    remote = copy.deepcopy(self.body)
                    remote[section].pop(field)
                    with self.assertRaisesRegex(RuntimeError, field):
                        verify_upload_settings(remote)

    def test_old_source_block_is_removed_from_checkpoints(self):
        result = public_description('Learn about influence.\n\nSources and further reading:\nhttps://example.com/books/')
        self.assertEqual(result, 'Learn about influence.')

    def test_model_links_removed_without_losing_anchor_text(self):
        result = public_description('Learn [boundaries](https://example.com) and influence.\nSource: https://example.org\nRead www.example.net')
        self.assertIn('Learn boundaries and influence.', result)
        self.assertNotIn('https', result)
        self.assertNotIn('www.', result)
        self.assertNotIn('Source:', result)


class DisclosureRepairTests(unittest.TestCase):
    def setUp(self):
        from unittest.mock import Mock
        self.client = Mock()
        self.client.videos.return_value.update.return_value.execute.return_value = {'id': 'existing-video', 'status': {'containsSyntheticMedia': True}}
        self.video = upload_body({'title': 'Title', 'tags': []}, 'Description')
        self.video.update(id='existing-video')
        self.video['snippet']['channelId'] = 'expected-channel'
        self.video['status'].update(license='youtube', embeddable=True,
                                    publishAt='2027-01-01T00:00:00Z')

    def repair(self, video):
        from youtube_metadata import ensure_upload_settings
        from unittest.mock import Mock
        self.pause = Mock()
        return ensure_upload_settings(self.client, 'existing-video', video,
                                      'expected-channel', pause=self.pause)

    def test_missing_ai_flag_is_updated_and_delayed_readback_is_retried(self):
        stale = copy.deepcopy(self.video)
        stale['status'].pop('containsSyntheticMedia')
        stale['status'].update(uploadStatus='processed', madeForKids=False)
        self.client.videos.return_value.list.return_value.execute.side_effect = [
            {'items': [stale]}, {'items': [self.video]}]
        self.assertEqual(self.repair(stale), self.video)
        body = self.client.videos.return_value.update.call_args.kwargs['body']
        self.assertEqual(body['id'], 'existing-video')
        self.assertEqual(body['status']['privacyStatus'], 'private')
        self.assertEqual(body['status']['publishAt'], self.video['status']['publishAt'])
        self.assertTrue(body['status']['containsSyntheticMedia'])
        self.assertTrue(body['status']['embeddable'])
        self.assertNotIn('uploadStatus', body['status'])
        self.assertNotIn('madeForKids', body['status'])
        self.assertNotIn('snippet', body)
        self.pause.assert_called_once_with(5)
        self.client.videos.return_value.insert.assert_not_called()

    def test_verified_settings_need_no_update(self):
        self.repair(self.video)
        self.client.videos.return_value.update.assert_not_called()

    def test_omitted_paid_promotion_false_is_valid_but_true_is_repaired(self):
        missing = copy.deepcopy(self.video)
        missing.pop('paidProductPlacementDetails')
        self.repair(missing)
        self.client.videos.return_value.update.assert_not_called()
        paid = copy.deepcopy(self.video)
        paid['paidProductPlacementDetails']['hasPaidProductPlacement'] = True
        self.client.videos.return_value.list.return_value.execute.return_value = {'items': [self.video]}
        self.repair(paid)
        self.assertEqual(self.client.videos.return_value.update.call_args.kwargs['part'],
                         'paidProductPlacementDetails')

    def test_persistent_mismatch_stops_without_duplicate_insert(self):
        stale = copy.deepcopy(self.video)
        stale['status']['containsSyntheticMedia'] = False
        self.client.videos.return_value.list.return_value.execute.return_value = {'items': [stale]}
        with self.assertRaisesRegex(RuntimeError, 'containsSyntheticMedia'):
            self.repair(stale)
        self.assertEqual(self.client.videos.return_value.update.call_count, 1)
        self.assertEqual(self.client.videos.return_value.list.call_count, 6)
        self.client.videos.return_value.insert.assert_not_called()

    def test_wrong_channel_and_unknown_visibility_never_updated(self):
        for section, field, value in [('snippet', 'channelId', 'wrong'),
                                      ('status', 'privacyStatus', None)]:
            bad = copy.deepcopy(self.video)
            bad[section][field] = value
            bad['status']['containsSyntheticMedia'] = False
            with self.assertRaises(RuntimeError):
                self.repair(bad)
        self.client.videos.return_value.update.assert_not_called()


    def test_permanently_omitted_readback_retains_accepted_submission_receipt(self):
        omitted = copy.deepcopy(self.video)
        omitted['status'].pop('containsSyntheticMedia')
        self.client.videos.return_value.list.return_value.execute.return_value = {'items': [omitted]}
        result = self.repair(omitted)
        self.assertNotIn('containsSyntheticMedia', result['status'])
        self.assertTrue(result['_ai_disclosure_submission']['api_update_accepted'])
        self.assertEqual(result['_ai_disclosure_submission']['video_id'], 'existing-video')
        verify_upload_settings(result)
        self.client.videos.return_value.insert.assert_not_called()

    def test_omission_without_acknowledged_update_still_fails(self):
        omitted = copy.deepcopy(self.video)
        omitted['status'].pop('containsSyntheticMedia')
        with self.assertRaisesRegex(RuntimeError, 'containsSyntheticMedia'):
            verify_upload_settings(omitted)
        self.client.videos.return_value.update.return_value.execute.return_value = {'id': 'wrong-video'}
        with self.assertRaisesRegex(RuntimeError, 'acknowledge'):
            self.repair(omitted)

    def test_update_failure_is_not_accepted_as_disclosure(self):
        omitted = copy.deepcopy(self.video)
        omitted['status'].pop('containsSyntheticMedia')
        self.client.videos.return_value.update.return_value.execute.side_effect = RuntimeError('denied')
        with self.assertRaisesRegex(RuntimeError, 'denied'):
            self.repair(omitted)

    def test_explicit_false_is_never_accepted_with_a_receipt(self):
        false = copy.deepcopy(self.video)
        false['status']['containsSyntheticMedia'] = False
        false['_ai_disclosure_submission'] = dict(video_id='existing-video', channel_id='expected-channel',
            requested_value=True, api_update_accepted=True)
        with self.assertRaisesRegex(RuntimeError, 'containsSyntheticMedia'):
            verify_upload_settings(false)


    def test_acknowledgement_without_true_disclosure_does_not_bypass_missing_field(self):
        omitted = copy.deepcopy(self.video)
        omitted['status'].pop('containsSyntheticMedia')
        self.client.videos.return_value.update.return_value.execute.return_value = {'id': 'existing-video'}
        self.client.videos.return_value.list.return_value.execute.return_value = {'items': [omitted]}
        with self.assertRaisesRegex(RuntimeError, 'containsSyntheticMedia'):
            self.repair(omitted)
