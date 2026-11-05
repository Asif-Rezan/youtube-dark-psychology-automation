import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import Mock,patch
from facebook_feed import render,probe,prepare


class FacebookFeedTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg required')
    def test_real_center_crop_preserves_audio_duration_and_caches(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'video.mp4';target=Path(tmp)/'feed.mp4'
            subprocess.run(['ffmpeg','-y','-v','error','-f','lavfi','-i',
                'color=c=green:s=320x180:d=1,drawbox=x=95:y=0:w=20:h=180:color=red:t=fill,drawbox=x=205:y=0:w=20:h=180:color=blue:t=fill',
                '-f','lavfi','-i','sine=frequency=440:duration=1','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(source)],check=True)
            render(source,target)
            data=probe(target);video=next(s for s in data['streams'] if s['codec_type']=='video')
            self.assertEqual((video['width'],video['height']),(1080,1350))
            self.assertTrue(any(s['codec_type']=='audio' for s in data['streams']))
            frame=subprocess.check_output(['ffmpeg','-v','error','-i',str(target),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'])
            def pixel(x,y):return frame[(y*1080+x)*3:(y*1080+x)*3+3]
            left,right=pixel(120,675),pixel(920,675)
            self.assertGreater(left[0],left[2]+100)
            self.assertGreater(right[2],right[0]+100)
            real_run=subprocess.run
            def cached_run(command,*args,**kwargs):
                if command[0]=='ffmpeg':raise AssertionError('cache re-encoded')
                return real_run(command,*args,**kwargs)
            with patch('facebook_feed.subprocess.run',side_effect=cached_run):
                render(source,target)

    def test_saved_feed_bytes_are_restored_instead_of_reencoding(self):
        store=Mock();store.find.return_value='saved-file'
        with tempfile.TemporaryDirectory() as tmp,patch('facebook_feed.verify') as verify,patch('facebook_feed.render') as encode:
            source=Path(tmp)/'video.mp4'
            path=prepare(source,store,'episode')
            self.assertEqual(path,source.parent/'facebook-feed/video.mp4')
            store.download.assert_called_once_with('saved-file',path)
            encode.assert_not_called();verify.assert_called_once()
