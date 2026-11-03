import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import short_music


class ShortMusicTests(unittest.TestCase):
    def song(self):
        scenes=[dict(index=i,start=i*5,end=(i+1)*5,
            lyric=f'Little turtles dance in garden {i}',prompt='Cute turtles in a garden') for i in range(96)]
        return dict(title='Turtle dance',prompt='Sweet female rhyme',vocal_gender='female',
            duration=480,scenes=scenes,lyrics='\n'.join(s['lyric'] for s in scenes))

    def test_short_synthesis_is_independent_aligned_and_checkpointed(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'output/test'
            root.mkdir(parents=True)
            song=self.song()
            (root/'song.json').write_text(json.dumps(song))
            def generate(request,target,state,save):
                self.assertEqual(request['duration'],40)
                self.assertTrue(request['_segment'])
                self.assertEqual(request['lyrics'],'\n'.join(s['lyric'] for s in song['scenes'][4:12]))
                self.assertIn('fresh standalone short dance arrangement',request['prompt'])
                target.write_bytes(b'independently-generated-audio')
                save()
            def normalize(args,**kwargs):
                shutil.copyfile(args[args.index('-i')+1],args[-1])
            info={'format':{'duration':'40'},'streams':[{'codec_type':'audio'}]}
            with patch('short_music.Path',side_effect=lambda p:Path(directory)/p), \
                    patch('music_cpu.generate_segment',side_effect=generate) as model, \
                    patch('short_music.probe',return_value=info), \
                    patch('short_music.subprocess.run',side_effect=normalize):
                output=short_music.prepare('test',20,40)
                self.assertEqual(output.read_bytes(),b'independently-generated-audio')
                short_music.prepare('test',20,40)
                model.assert_called_once()
                # Neither a long audio file nor a long video exists in this fixture.
                self.assertFalse((root/'song.wav').exists())
                self.assertFalse((root/'video.mp4').exists())
                song['prompt']='Changed story request'
                (root/'song.json').write_text(json.dumps(song))
                with self.assertRaisesRegex(ValueError,'another request'):
                    short_music.prepare('test',20,40)

    def test_out_of_range_clip_stops_before_music_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'output/test'
            root.mkdir(parents=True)
            (root/'song.json').write_text(json.dumps(self.song()))
            with patch('short_music.Path',side_effect=lambda p:Path(directory)/p), patch('music_cpu.generate_segment') as model:
                with self.assertRaisesRegex(ValueError,'exceeds storyboard'):
                    short_music.prepare('test',460,40)
                model.assert_not_called()
