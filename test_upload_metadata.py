import copy
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from pipeline import publish
from upload_metadata import fixed_metadata


class FixedUploadMetadataTests(unittest.TestCase):
    def test_new_upload_uses_exact_fixed_metadata_with_empty_tags(self):
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
        song = dict(title='AI story title', description='AI description', tags=['AI tag'])
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
        expected = fixed_metadata(kind)
        for field in ('title','description','tags'):
            self.assertEqual(actual[field],expected[field])
        self.assertEqual(actual['tags'],[])
        self.assertNotIn('Original kids rhyme arrangement',actual['description'])
        self.assertEqual(state['phase'],'published')
        ai_description.assert_not_called()
        ai_tags.assert_not_called()
