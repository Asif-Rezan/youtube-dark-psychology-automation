import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import prepare_music
from test_song_generation import CORE, PACKAGE


class PreparationHistoryTests(unittest.TestCase):
    def test_history_is_loaded_before_generation_and_existing_title_is_rechecked(self):
        history = [{'run': 'old', 'title': CORE['title'], 'hash': 'other'},
                   {'run': 'new-run', 'title': 'current identity'}]
        store = Mock()
        store.load.return_value = history
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)/'output'/'new-run'
            root.mkdir(parents=True)
            (root/'song.json').write_text(json.dumps(dict(CORE, **PACKAGE)))
            def generate(day, seen, draft, generation_id, vocal_gender_override='auto'):
                store.load.assert_called_once_with('history.json', [])
                self.assertEqual(seen, history[:1])
                self.assertEqual(json.loads(draft.read_text())['lyrics'], CORE['lyrics'])
                self.assertEqual(generation_id, 'new-run')
                return dict(CORE, **PACKAGE, title='नया नाम')
            with patch('prepare_music.Path', side_effect=lambda value: Path(temp)/value), patch('storage.Store', return_value=store), patch('prepare_music.make_song', side_effect=generate):
                prepare_music.prepare('new-run', 'lyrics', check_history=True)
            self.assertEqual(json.loads((root/'song.json').read_text())['title'], 'नया नाम')

    def test_history_failure_stops_before_expensive_generation(self):
        store = Mock()
        store.load.side_effect = ConnectionError('history unavailable')
        with tempfile.TemporaryDirectory() as temp:
            with patch('prepare_music.Path', side_effect=lambda value: Path(temp)/value), patch('storage.Store', return_value=store), patch('prepare_music.make_song') as generate:
                with self.assertRaises(ConnectionError):
                    prepare_music.prepare('new-run', 'lyrics', check_history=True)
            generate.assert_not_called()
