import copy
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from pipeline import publish
from episode_packaging import public_metadata
from test_episode_packaging import fixture_package
from test_prepare_original_lyrics import fixture_song


class EpisodeUploadMetadataTests(unittest.TestCase):
    def test_new_upload_uses_saved_episode_metadata_with_relevant_tags(self):
        client, state = Mock(), {}
        client.videos.return_value.insert.return_value.next_chunk.return_value = (None, {'id':'new-video'})
        def readback():
            video = copy.deepcopy(state['upload_body'])
            video['id'] = state['video_id']
            video['snippet']['channelId'] = 'channel'
            video['status']['uploadStatus'] = 'processed'
            video['contentDetails'] = {'definition':'hd'}
            video['processingDetails'] = {'processingStatus':'succeeded'}
            return {'items':[video]}
        client.videos.return_value.list.return_value.execute.side_effect = readback
        song=fixture_song();song['packaging']=fixture_package(song)
        self._check_upload(client, state, song, 'video')
        self._check_upload(client, state, song, 'shorts')

    def _check_upload(self, client, state, song, kind):
        state.clear()
        with patch.dict('os.environ', {'UPLOAD_MODE':'public'},clear=True), \
                patch('pipeline.required', return_value='channel'), \
                patch('googleapiclient.http.MediaFileUpload'), \
                patch('pipeline.upload_description') as ai_description, \
                patch('pipeline.metadata_tags') as ai_tags:
            publish(client, Path('/unused'), song, state, Mock(), upload_thumbnail=False, metadata_kind=kind)
        actual = client.videos.return_value.insert.call_args.kwargs['body']['snippet']
        expected = public_metadata(song,kind)
        for field in ('title','description','tags'):
            self.assertEqual(actual[field],expected[field])
        self.assertTrue(actual['tags'])
        self.assertNotIn('Original kids rhyme arrangement',actual['description'])
        self.assertEqual(state['phase'],'published')
        ai_description.assert_not_called()
        ai_tags.assert_not_called()
        original=copy.deepcopy(state['upload_body'])
        inserts=client.videos.return_value.insert.call_count
        with patch('episode_packaging.public_metadata',side_effect=AssertionError('Existing metadata changed')), \
             patch('pipeline.required',return_value='channel'):
            publish(client,Path('/unused'),song,state,Mock(),upload_thumbnail=False,metadata_kind=kind)
        self.assertEqual(state['upload_body'],original)
        self.assertEqual(client.videos.return_value.insert.call_count,inserts)
