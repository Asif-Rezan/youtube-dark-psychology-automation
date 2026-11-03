import unittest
from unittest.mock import Mock, patch
from storage import Store


class StorageConfigurationTests(unittest.TestCase):
    def make_store(self, *, children=None, owner='project@example.com', private=True, trashed=False):
        api = Mock()
        api.about().get().execute.return_value = {'user': {'emailAddress': 'project@example.com'}}
        api.files().get().execute.return_value = {
            'mimeType': 'application/vnd.google-apps.folder', 'trashed': trashed,
            'owners': [{'emailAddress': owner}], 'appProperties': {'grow_with_rezan_root':'v1'}}
        api.permissions().list().execute.return_value = {'permissions':
            [{'type': 'user', 'role': 'owner'}] + ([] if private else [{'type': 'anyone', 'role': 'reader'}])}
        api.files().list().execute.return_value = {'files': children or []}
        api.files().create().execute.return_value = {'id': 'kids-child'}
        api.reset_mock()
        with patch.dict('os.environ', {'DRIVE_TOKEN_JSON': '{}', 'DRIVE_FOLDER_ID': 'existing-root'}), \
             patch('google.oauth2.credentials.Credentials.from_authorized_user_info'), \
             patch('googleapiclient.discovery.build', return_value=api):
            store = Store()
        return store, api

    def test_existing_project_account_creates_isolated_kids_folder(self):
        store, api = self.make_store()
        self.assertEqual(store.folder, 'kids-child')
        body = api.files().create.call_args.kwargs['body']
        self.assertEqual(body['parents'], ['existing-root'])
        self.assertEqual(body['appProperties'], {'grow_with_rezan_kids_root': 'v1'})
        api.files().delete.assert_not_called()
        api.files().update.assert_not_called()

    def test_reuses_child_and_does_not_read_ancient_history(self):
        store, api = self.make_store(children=[{'id': 'saved-kids'}])
        self.assertEqual(store.folder, 'saved-kids')
        api.files().create.assert_not_called()

    def test_foreign_owner_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'must belong'):
            self.make_store(owner='other@example.com')

    def test_shared_or_trashed_folder_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'private'):
            self.make_store(private=False)
        with self.assertRaisesRegex(RuntimeError, 'active folder'):
            self.make_store(trashed=True)

    def test_duplicate_children_are_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'Multiple kids'):
            self.make_store(children=[{'id': 'one'}, {'id': 'two'}])
