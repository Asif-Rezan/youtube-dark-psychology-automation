import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from legacy_drive_cleanup import clean, inventory, verify_root


class LegacyCleanupTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        self.file = dict(id='old-media', name='old-video.mp4', mimeType='video/mp4',
                         parents=['project-root'], size='100', md5Checksum='old', modifiedTime='then')
        self.client.files().get().execute.return_value = self.file
        self.client.permissions().list().execute.return_value = {'permissions':[{'role':'owner','type':'user'}]}
        self.client.about().get().execute.return_value = {'storageQuota':{}}

    def test_audit_never_deletes_or_traverses_kids_folder(self):
        with tempfile.TemporaryDirectory() as tmp, patch('legacy_drive_cleanup.inventory',return_value=([self.file],['kids-folder'])):
            report = clean(self.client,'project-root',Path(tmp)/'report.json')
        self.assertEqual(report['preserved_folders'],['kids-folder'])
        self.assertEqual(report['candidates'],[self.file])
        self.client.files().delete.assert_not_called()

    def test_delete_rechecks_exact_file_and_confirms_no_old_files_remain(self):
        with tempfile.TemporaryDirectory() as tmp, patch('legacy_drive_cleanup.inventory',side_effect=[([self.file],['kids-folder']),([],['kids-folder'])]):
            report = clean(self.client,'project-root',Path(tmp)/'report.json',apply=True)
        self.client.files().delete.assert_called_once_with(fileId='old-media')
        self.assertEqual(report['deleted_bytes'],100)
        self.assertFalse(report['remaining'])

    def test_changed_or_moved_file_is_preserved_with_durable_failure(self):
        for changes in ({'parents':['another-folder']},{'md5Checksum':'changed'},{'mimeType':'application/vnd.google-apps.folder'}):
            with self.subTest(changes=changes), tempfile.TemporaryDirectory() as tmp, patch('legacy_drive_cleanup.inventory',return_value=([self.file],[])):
                self.client.files().get().execute.return_value=dict(self.file,**changes)
                path=Path(tmp)/'report.json'
                with self.assertRaises(RuntimeError):
                    clean(self.client,'project-root',path,apply=True)
                self.assertEqual(json.loads(path.read_text())['failed'][0]['id'],'old-media')
        self.client.files().delete.assert_not_called()

    def test_wrong_project_marker_or_foreign_owner_never_lists_or_deletes(self):
        self.client.about().get().execute.return_value={'user':{'emailAddress':'owner@example.com'}}
        for changes in ({'appProperties':{'dudi_dam_tv_root':'v1'}},{'owners':[{'emailAddress':'other@example.com'}]}):
            root=dict(id='project-root',mimeType='application/vnd.google-apps.folder',trashed=False,
                      appProperties={'grow_with_rezan_root':'v1'},owners=[{'emailAddress':'owner@example.com'}])
            self.client.files().get().execute.return_value=dict(root,**changes)
            with self.assertRaises(RuntimeError):
                inventory(self.client,'project-root')
        self.client.files().list.assert_not_called()
        self.client.files().delete.assert_not_called()

    def test_inventory_paginates_but_preserves_all_subfolders(self):
        self.client.files().list().execute.side_effect=[
            {'files':[dict(id='kids-folder',mimeType='application/vnd.google-apps.folder')],'nextPageToken':'next'},
            {'files':[self.file]}]
        with patch('legacy_drive_cleanup.verify_root'):
            files,folders=inventory(self.client,'project-root')
        self.assertEqual(files,[self.file]);self.assertEqual(folders,['kids-folder'])
        self.assertEqual(self.client.files().list.call_args.kwargs['pageToken'],'next')
