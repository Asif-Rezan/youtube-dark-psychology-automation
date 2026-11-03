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
