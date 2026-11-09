import contextlib
import datetime as dt
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
import facebook_publish


class FeedRoutingTests(unittest.TestCase):
    def test_only_new_feed_uploads_are_cropped_and_page_metadata_are_preserved(self):
        target=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(days=4)).replace(microsecond=0)
        for kind,existing,expected_crop in [('video',{},True),('short',{},False),
            ('video',{'video_id':'123','publish_at':int(target.timestamp()),'identity':{'sha256':'old'}},False),
            ('video',{'video_id':'123','publish_at':int(target.timestamp()),'media_format':'feed-4x5-crop-v1'},True)]:
            with self.subTest(kind=kind,state=existing), tempfile.TemporaryDirectory() as tmp, contextlib.chdir(tmp):
                youtube=dict(phase='scheduled',schedule_target=target.isoformat(),
                             upload_body={'snippet':{'title':'Original episode title','description':'Original description'}})
                store=Mock();store.load.side_effect=[youtube,existing]
                def crop(path,store,run_id):return path.parent/'facebook-feed/video.mp4'
                def publish(api,path,media_kind,metadata,stamp,state,save):
                    self.assertEqual(media_kind,kind)
                    self.assertEqual(metadata['title'],'Original episode title')
                    self.assertTrue(metadata['description'].startswith('Original description'))
                    self.assertEqual(stamp,int(target.timestamp()))
                    self.assertEqual('facebook-feed' in path.parts,expected_crop)
                    state.update(identity={},video_id='123');save()
                with patch.dict('os.environ',FACEBOOK_PAGE_ACCESS_TOKEN='test-only'),patch('storage.Store',return_value=store),patch('facebook_feed.prepare',side_effect=crop) as export,patch('facebook_publish.publish',side_effect=publish):
                    facebook_publish.run('episode',kind)
                self.assertEqual(export.call_count,int(expected_crop))
                if expected_crop:self.assertEqual(store.save.call_args.args[1]['media_format'],'feed-4x5-crop-v1')
                self.assertEqual(facebook_publish.PAGE_ID,'301624356367343')
