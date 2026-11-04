import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from continuous_song import continuous_request, render_continuous


class ContinuousSongTests(unittest.TestCase):
    def test_one_full_song_inference_then_whole_file_encoding(self):
        verses=['पहली नई पंक्ति','दूसरी नई पंक्ति']
        with tempfile.TemporaryDirectory() as tmp, \
             patch.dict('os.environ', {'ACESTEP_SOURCE_DIR':'source','ACESTEP_CHECKPOINTS_DIR':'models'}), \
             patch('music_cpu.synthesize') as synthesize, \
             patch('pipeline.duration',return_value=60), \
             patch('continuous_song.subprocess.run') as encode:
            target=render_continuous(verses,'test',Path(tmp))
            synthesize.assert_called_once()
            request=synthesize.call_args.args[0]
            self.assertEqual(request['duration'],60)
            self.assertTrue(request['reference_cover'])
            self.assertEqual(request['cover_noise_strength'],.95)
            self.assertFalse(request.get('reference_repaint'))
            self.assertNotIn('edit_source',request)
            for verse in verses:
                self.assertIn(verse,request['lyrics'])
            encode.assert_called_once()
            command=encode.call_args.args[0]
            self.assertEqual(command.count('-i'),1)
            self.assertEqual(command[command.index('-i')+1],str(target))
            report=json.loads((Path(tmp)/'arrangement-report.json').read_text())
            self.assertFalse(report['audio_splicing'])

    def test_short_source_rejected_before_inference(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch('pipeline.duration', return_value=30), \
             patch('music_cpu.synthesize') as synthesize:
            with self.assertRaisesRegex(ValueError, 'requires a source'):
                render_continuous(['एक','दो'], 'test', Path(tmp))
            synthesize.assert_not_called()

    def test_reject_duplicate_verse_blocks(self):
        with self.assertRaises(ValueError):
            continuous_request(['same','same'],'test')
