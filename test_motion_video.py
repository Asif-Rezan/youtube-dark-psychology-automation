import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image
from motion_video import render_scenes, render_identity, render_is_current, FPS

class MotionTests(unittest.TestCase):
    def test_verified_character_clips_are_used_for_every_scene(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            scenes=[{'index':i,'prompt':f'Character {i}'} for i in range(3)]
            for scene in scenes:
                Image.new('RGB',(32,18),'yellow').save(root/f"scene-{scene['index']:03d}-source.png")
            with patch('character_motion.cached_clip',return_value=True) as cached, \
                 patch('character_motion.verify_clip') as verified:
                listing=render_scenes(root,scenes,320,180)
            self.assertEqual(cached.call_count,3)
            self.assertEqual(verified.call_count,3)
            self.assertEqual(len(listing.read_text().splitlines()),3)
            with patch('character_motion.cached_clip',return_value=False):
                with self.assertRaisesRegex(RuntimeError,'regenerate its image shard'):
                    render_scenes(root,scenes,320,180)

    def test_static_or_changed_inputs_invalidate_old_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'song.json').write_text(json.dumps({'scenes':[{'index':0}]}))
            for name in ('song.wav','thumbnail-source.png','scene-000-source.png','video.mp4'):
                (root/name).write_bytes(b'fixture')
            self.assertFalse(render_is_current(root))
            (root/'render-state.json').write_text(json.dumps(render_identity(root)))
            self.assertTrue(render_is_current(root))
            (root/'scene-000-source.png').write_bytes(b'new illustration')
            self.assertFalse(render_is_current(root))
