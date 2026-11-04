import copy
import hashlib
import types
import unittest
from unittest.mock import Mock, patch

from cleanup_drive import cleanup, PublicationPending, CleanupNotEligible, sweep, run_states, verify_public
from pipeline import metadata_tags, upload_description


class DriveCleanupTests(unittest.TestCase):
    def setUp(self):
        self.run_id = 'original-hindi-20261026-artwork-01'
        self.key = f'runs/{self.run_id}/video.mp4'
        self.song = {'title': 'नई सुबह', 'description': 'A hopeful Hindi song', 'tags': ['Hindi music']}
        self.state = {'phase': 'published', 'video_id': 'video', 'thumbnail_uploaded': True, 'song': self.song}
        self.video = {'id': 'video', 'snippet': {'channelId': 'channel', 'title': self.song['title'],
            'description': upload_description(self.song),
            'tags': metadata_tags(self.song)}, 'status': {'privacyStatus': 'public', 'uploadStatus': 'processed'},
            'processingDetails': {'processingStatus': 'succeeded'}, 'contentDetails': {'definition': 'hd'}}
        self.client = Mock()
        self.client.videos().list().execute.return_value = {'items': [self.video]}
        self.store = Mock(folder='folder')
        self.journal = {'run': self.run_id, 'video_id': 'video', 'files': [{'id': 'file', 'name': 'video.mp4'}], 'deleted': []}
        self.store.load.return_value = self.journal
        self.remote = {'id': 'file', 'name': self.key.replace('/', '__'), 'parents': ['folder'],
            'appProperties': {'workflow_key': hashlib.sha256(self.key.encode()).hexdigest()}, 'mimeType': 'video/mp4'}
        self.store.client.files().get().execute.return_value = self.remote
        self.environment = patch.dict('os.environ', {'EXPECTED_CHANNEL_ID': 'channel'})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_failed_unpublished_or_missing_thumbnail_never_deletes(self):
        for field, value in [('phase', 'generating'), ('video_id', ''), ('thumbnail_uploaded', False)]:
            with self.assertRaises(RuntimeError):
                cleanup(self.store, self.client, self.run_id, dict(self.state, **{field: value}))
        self.store.client.files().delete.assert_not_called()

    def test_fresh_remote_verification_requires_public_hd_success_and_matching_metadata(self):
        original = copy.deepcopy(self.video)
        cases = [('status', 'privacyStatus', 'private'), ('status', 'uploadStatus', 'failed'),
                 ('contentDetails', 'definition', 'sd'), ('processingDetails', 'processingStatus', 'processing'),
                 ('snippet', 'title', 'Wrong title'), ('snippet', 'channelId', 'other'),
                 ('snippet', 'description', 'changed'), ('snippet', 'tags', ['other'])]
        for section, field, value in cases:
            self.video.clear()
            self.video.update(copy.deepcopy(original))
            self.video[section][field] = value
            with self.assertRaises(RuntimeError):
                cleanup(self.store, self.client, self.run_id, self.state)
        self.store.client.files().delete.assert_not_called()

    def test_deletes_only_exact_media_id_and_repeat_is_idempotent(self):
        cleanup(self.store, self.client, self.run_id, self.state)
        self.store.client.files().delete.assert_called_once_with(fileId='file')
        self.assertTrue(self.journal['complete'])
        cleanup(self.store, self.client, self.run_id, self.state)
        self.store.client.files().delete.assert_called_once_with(fileId='file')

    def test_rejects_other_folder_hash_name_or_folder_type(self):
        original = copy.deepcopy(self.remote)
        for field, value in [('parents', ['other']), ('name', 'unrelated.mp4'),
                             ('appProperties', {'workflow_key': 'wrong'}),
                             ('mimeType', 'application/vnd.google-apps.folder')]:
            self.remote.clear()
            self.remote.update(copy.deepcopy(original))
            self.remote[field] = value
            with self.assertRaises(RuntimeError):
                cleanup(self.store, self.client, self.run_id, self.state)
        self.store.client.files().delete.assert_not_called()

    def test_preserves_state_history_lyrics_and_unrelated_files(self):
        self.store.load.return_value = None
        self.store.find.side_effect = lambda key: 'file' if key == self.key else None
        cleanup(self.store, self.client, self.run_id, self.state)
        keys = [call.args[0] for call in self.store.find.call_args_list]
        self.assertNotIn(f'runs/{self.run_id}/state.json', keys)
        self.assertNotIn(f'runs/{self.run_id}/song.json', keys)
        self.assertNotIn('history.json', keys)
        self.assertNotIn(f'runs/{self.run_id}/image-manifest.json', keys)
        calls = [call[0] for call in self.store.mock_calls]
        self.assertLess(calls.index('save'), calls.index('client.files().delete'))

    def test_deleted_before_checkpoint_is_safe_to_resume(self):
        error = RuntimeError('not found')
        error.resp = types.SimpleNamespace(status=404)
        self.store.client.files().get().execute.side_effect = error
        cleanup(self.store, self.client, self.run_id, self.state)
        self.assertEqual(self.journal['deleted'], ['file'])
        self.store.client.files().delete.assert_not_called()

    def test_delete_failure_preserves_checkpoint_for_retry(self):
        self.store.client.files().delete().execute.side_effect = RuntimeError('permission denied')
        with self.assertRaises(RuntimeError):
            cleanup(self.store, self.client, self.run_id, self.state)
        self.assertEqual(self.journal['deleted'], [])
        self.assertNotIn('complete', self.journal)

    def test_scheduled_private_is_pending_and_never_deletes(self):
        self.video['status']['privacyStatus']='private'
        state=dict(self.state,phase='scheduled')
        with self.assertRaises(PublicationPending):
            cleanup(self.store,self.client,self.run_id,state)
        self.store.client.files().delete.assert_not_called()
        self.store.save.assert_not_called()

    def test_scheduled_that_has_become_public_is_cleaned_and_state_refreshed(self):
        state=dict(self.state,phase='scheduled')
        cleanup(self.store,self.client,self.run_id,state)
        self.assertEqual(state['phase'],'published')
        self.store.client.files().delete.assert_called_once_with(fileId='file')
        self.store.save.assert_any_call(f'runs/{self.run_id}/state.json',state)

    def test_cleanup_matches_actual_fixed_upload_metadata_instead_of_story_title(self):
        actual={'title':'Owner supplied upload title','description':'Owner description','tags':[]}
        state=dict(self.state,upload_body={'snippet':actual})
        self.video['snippet'].update(actual)
        cleanup(self.store,self.client,self.run_id,state)
        self.store.client.files().delete.assert_called_once_with(fileId='file')

    def test_private_scheduled_wrong_metadata_is_failure_not_pending(self):
        self.video['status']['privacyStatus']='private'
        self.video['snippet']['title']='other upload'
        with self.assertRaises(RuntimeError) as caught:
            cleanup(self.store,self.client,self.run_id,dict(self.state,phase='scheduled'))
        self.assertNotIsInstance(caught.exception,PublicationPending)
        self.store.client.files().delete.assert_not_called()

    def test_sweep_continues_after_pending_and_failed_checks(self):
        store=Mock()
        store.load.return_value=None
        states=[('done',{'phase':'published'}),('later',{'phase':'scheduled'}),
                ('bad',{'phase':'published'}),('unfinished',{'phase':'generating'}),
                ('corrupt',{'_read_error':'ValueError'})]
        def clean(_store,_client,run_id,state):
            if run_id=='later':raise PublicationPending()
            if run_id=='bad':raise RuntimeError('private API response must not appear')
            return {'deleted':['one','two']}
        with patch('cleanup_drive.run_states',return_value=iter(states)), \
             patch('cleanup_drive.quota',return_value={'limit':'10000','usage':'5000'}), \
             patch('cleanup_drive.cleanup',side_effect=clean):
            report=sweep(store,self.client)
        self.assertEqual(report['cleaned'],[{'run':'done','deleted_media':2}])
        self.assertEqual(report['pending'],['later'])
        self.assertEqual(report['preserved'],['unfinished'])
        self.assertEqual([r['run'] for r in report['failed']],['bad','corrupt'])
        self.assertNotIn('private API response',str(report))

    def test_sweep_does_not_repeat_completed_cleanup(self):
        self.store.load.return_value={'complete':True,'run':self.run_id,'video_id':'video'}
        with patch('cleanup_drive.run_states',return_value=iter([(self.run_id,self.state)])), \
             patch('cleanup_drive.quota',return_value={}), patch('cleanup_drive.cleanup') as clean:
            report=sweep(self.store,self.client)
        clean.assert_not_called()
        self.assertFalse(report['failed'])

    def test_inventory_is_paginated_and_only_reads_tagged_automation_checkpoints(self):
        store=Mock(folder='folder')
        key='runs/allowed/state.json'
        valid={'id':'good','name':'runs__allowed__state.json','mimeType':'application/json',
               'appProperties':{'workflow_key':hashlib.sha256(key.encode()).hexdigest()}}
        invalid=dict(valid,id='untagged',appProperties={})
        store.client.files().list().execute.side_effect=[{'files':[invalid],'nextPageToken':'next'}, {'files':[valid]}]
        store.client.files().get_media().execute.return_value=b'{"phase":"scheduled"}'
        self.assertEqual(list(run_states(store)),[('allowed',{'phase':'scheduled'})])
        store.check_private.assert_called_once_with('good')
        store.client.files().get_media.assert_called_with(fileId='good')
        self.assertEqual(store.client.files().list.call_args.kwargs['pageToken'],'next')


    def test_metadata_mismatch_is_preserved_with_safe_field_reasons_not_sweep_failure(self):
        self.video['snippet']['title']='An edited private title value'
        self.store.load.return_value=None
        with patch('cleanup_drive.run_states',return_value=iter([(self.run_id,self.state)])), \
             patch('cleanup_drive.quota',return_value={}):
            report=sweep(self.store,self.client)
        self.assertEqual(report['failed'],[])
        self.assertEqual(report['preserved'],[self.run_id])
        self.assertEqual(report['review'],[dict(run=self.run_id,reason='video_verification_mismatch',fields=['title'])])
        self.assertNotIn('An edited private title value',str(report))
        self.store.save.assert_not_called()
        self.store.client.files().delete.assert_not_called()

    def test_cleanup_uses_the_same_tag_normalization_as_upload_verification(self):
        self.video['snippet']['tags']=['  '+tag.upper().replace(' ','   ')+'  '
                                      for tag in metadata_tags(self.song)]
        cleanup(self.store,self.client,self.run_id,self.state)
        self.store.client.files().delete.assert_called_once_with(fileId='file')

    def test_unavailable_video_preserves_media_with_explicit_reason(self):
        self.client.videos().list().execute.return_value={'items':[]}
        with self.assertRaises(CleanupNotEligible) as caught:
            cleanup(self.store,self.client,self.run_id,self.state)
        self.assertEqual(caught.exception.reason,'video_unavailable')
        self.store.client.files().delete.assert_not_called()

    def test_audit_checks_publication_without_writing_or_deleting(self):
        self.store.load.return_value=None
        with patch('cleanup_drive.run_states',return_value=iter([(self.run_id,self.state)])), \
             patch('cleanup_drive.quota',return_value={}):
            report=sweep(self.store,self.client,dry_run=True)
        self.assertEqual(report['eligible'],[self.run_id])
        self.assertEqual(report['cleaned'],[])
        self.store.save.assert_not_called()
        self.store.find.assert_not_called()
        self.store.client.files().delete.assert_not_called()
        self.client.videos().list().execute.assert_called_with(num_retries=3)

    def test_api_and_delete_failures_remain_visible_sweep_failures(self):
        self.store.load.return_value=None
        error=RuntimeError('Sensitive response text')
        error.resp=types.SimpleNamespace(status=503)
        self.client.videos().list().execute.side_effect=error
        with patch('cleanup_drive.run_states',return_value=iter([(self.run_id,self.state)])), \
             patch('cleanup_drive.quota',return_value={}):
            report=sweep(self.store,self.client)
        self.assertEqual(report['failed'],[dict(run=self.run_id,error_type='RuntimeError',http_status=503)])
        self.assertNotIn('Sensitive response text',str(report))
        self.assertFalse(report['review'])
        self.store.client.files().delete.assert_not_called()


class CleanupQuotaReserveTests(unittest.TestCase):
    def test_tiny_cleanup_journal_can_use_reserve_but_media_upload_cannot(self):
        from storage import Store
        store=object.__new__(Store)
        store.client=Mock()
        limit=15*1024**3
        store.client.about().get().execute.return_value={'storageQuota':{'limit':str(limit),'usage':str(limit-1024*1024)}}
        Store.check_quota(store,4096,reserve_bytes=0)
        with self.assertRaises(RuntimeError):Store.check_quota(store,4096)
        with self.assertRaises(RuntimeError):Store.check_quota(store,2*1024*1024,reserve_bytes=0)


if __name__ == '__main__':
    unittest.main()
