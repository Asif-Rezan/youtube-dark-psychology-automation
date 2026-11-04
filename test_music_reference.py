"""Reference conditioning must survive local and worker entry points."""
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import music_cpu


class ReferenceAudioTests(unittest.TestCase):
    def test_unset_and_blank_use_the_motivation_reference(self):
        for value in (None, '', '   '):
            with self.subTest(value=value), patch.dict(os.environ, {}, clear=True):
                if value is not None:
                    os.environ['REFERENCE_AUDIO_PATH'] = value
                reference = Path(music_cpu.reference_audio())
                self.assertEqual(hashlib.sha256(reference.read_bytes()).hexdigest(),
                    'e3495eaad8701640aea5b4a3281775590251abb6d72b763c93781bb493443c61')

    def test_relative_override_is_repository_relative(self):
        with patch.dict(os.environ, REFERENCE_AUDIO_PATH='assets/reference/style-reference.mp3'):
            self.assertEqual(Path(music_cpu.reference_audio()), music_cpu.DEFAULT_REFERENCE_AUDIO)

    def test_missing_or_empty_override_stops_before_model_loading(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'reference.mp3'
            for exists in (False, True):
                if exists:
                    path.touch()
                with patch.dict(os.environ, REFERENCE_AUDIO_PATH=str(path)), \
                     patch('music_cpu.checkpoints') as checkpoints:
                    with self.assertRaisesRegex(ValueError, 'missing or empty'):
                        music_cpu.synthesize({'_segment': True}, Path(tmp)/'song.wav', Path(tmp), Path(tmp))
                    checkpoints.assert_not_called()


class ChorusReferenceTests(unittest.TestCase):
    def test_both_chorus_previews_repeat_exact_hook_and_use_stronger_source_anchoring(self):
        from preview_kids_audio import preview_song, REFRAIN
        for style, noise in (('chorus-close', .85), ('chorus-strict', .95)):
            song = preview_song(style)
            self.assertEqual(song['lyrics'].count(REFRAIN+'\n'+REFRAIN), 2)
            options = music_cpu.reference_cover_options(song, 'reference.mp3')
            self.assertEqual(options['cover_noise_strength'], noise)
            self.assertEqual(options['audio_cover_strength'], 1.0)
            self.assertEqual(options['task_type'], 'cover')
            self.assertEqual(options['src_audio'], 'reference.mp3')
            self.assertIn('instrumental intro', song['prompt'])
            self.assertEqual(song['duration'], 30)

    def test_invalid_cover_settings_fail_before_model_loading(self):
        for value in (-.1, 1.1, float('nan'), float('inf')):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    music_cpu.reference_cover_options({'reference_cover': True,
                        'cover_noise_strength': value}, 'reference.mp3')
        self.assertEqual(music_cpu.reference_cover_options({}, 'reference.mp3'), {})


class CoverSourceDurationTests(unittest.TestCase):
    def test_long_reference_is_trimmed_but_style_reference_is_preserved(self):
        import subprocess
        from pipeline import duration
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); reference=root/'reference.wav'
            subprocess.run(['ffmpeg','-y','-v','error','-f','lavfi','-i',
                'sine=frequency=440:duration=3',str(reference)],check=True)
            original=hashlib.sha256(reference.read_bytes()).hexdigest()
            result=music_cpu.prepare_cover_source(reference,1,root/'prepared')
            self.assertAlmostEqual(duration(result),1,places=2)
            self.assertAlmostEqual(duration(reference),3,places=2)
            self.assertEqual(hashlib.sha256(reference.read_bytes()).hexdigest(),original)
            self.assertEqual(result,music_cpu.prepare_cover_source(reference,1,root/'prepared'))
            with self.assertRaisesRegex(ValueError,'shorter'):
                music_cpu.prepare_cover_source(reference,4,root/'prepared')
            self.assertEqual(music_cpu.prepare_cover_source(reference,3,root),str(reference))

    def test_invalid_duration_rejected(self):
        for seconds in (0,-1,float('nan'),float('inf')):
            with self.assertRaises(ValueError):
                music_cpu.prepare_cover_source('unused.wav',seconds,Path('.'))
