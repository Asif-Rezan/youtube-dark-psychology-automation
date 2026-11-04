"""Downstream recovery must restore input, never unexpectedly run lyric inference."""
import contextlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from prepare_music import prepare


class StageRecoveryTests(unittest.TestCase):
    def test_missing_lyrics_stops_before_model_generation(self):
        for stage in ('music', 'images', 'render'):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as folder, contextlib.chdir(folder):
                with patch('prepare_music.make_song') as generate:
                    with self.assertRaisesRegex(RuntimeError, 'Lyrics checkpoint missing'):
                        prepare('missing-input', stage)
                    generate.assert_not_called()
