import json
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
import music_cpu as music

SONG = dict(title='याद', lyrics='तेरी यादों में मेरा दिल खो गया', prompt='Hindi acoustic pop', duration=240, description='Original Hindi music')


class CpuMusicTests(unittest.TestCase):
    def test_downloads_pinned_weights_anonymously_without_planning_lm(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in music.COMPONENTS:
                (root/name).mkdir()
                (root/name/'model.safetensors').touch()
            with patch('huggingface_hub.snapshot_download') as download:
                music.checkpoints(root)
            call = download.call_args.kwargs
            self.assertEqual(call['revision'], music.MODEL_REVISION)
            self.assertIs(call['token'], False)
            self.assertEqual(call['allow_patterns'], [name+'/*' for name in music.COMPONENTS])
            self.assertFalse(any('5Hz' in name for name in call['allow_patterns']))

    def test_source_revision_must_match_reviewed_code(self):
        with patch.object(music.subprocess, 'check_output', return_value='different-ref'):
            with self.assertRaisesRegex(RuntimeError, 'revision'):
                music.runtime(Path('source'))

    def test_music_runs_only_on_cpu_with_original_hindi_and_full_duration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio = root/'native.wav'
            audio.write_bytes(b'RIFF-original-song')
            target = root/'song.wav'
            torch = Mock()
            torch.inference_mode.return_value.__enter__ = Mock()
            torch.inference_mode.return_value.__exit__ = Mock(return_value=False)
            handler = Mock(device='cpu')
            handler.initialize_service.return_value = ('ready', True)
            params, config = Mock(), Mock()
            infer = Mock(return_value=types.SimpleNamespace(success=True, audios=[{'path':str(audio)}]))
            with patch.object(music, 'checkpoints'), patch.object(music, 'runtime', return_value=(torch, Mock(return_value=handler), params, config, infer)), patch('pipeline.duration', return_value=240):
                music.synthesize(SONG, target, root/'source', root/'models')
            self.assertEqual(handler.initialize_service.call_args.kwargs['device'], 'cpu')
            self.assertEqual(params.call_args.kwargs['duration'], 240)
            self.assertEqual(params.call_args.kwargs['lyrics'], SONG['lyrics'])
            self.assertFalse(params.call_args.kwargs['thinking'])
            self.assertEqual(config.call_args.kwargs['batch_size'], 1)
            self.assertIsNone(infer.call_args.args[1])
            self.assertEqual(target.read_bytes(), audio.read_bytes())

    def test_interrupted_local_worker_can_resume_without_remote_submission(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)/'song.wav'
            state = {'generation_started':True}
            def worker(*args, **kwargs):
                target.write_bytes(b'RIFF-local-song')
            with patch.object(music.subprocess, 'run', side_effect=worker), patch('pipeline.duration', return_value=240):
                music.generate(SONG, target, state, Mock())
            self.assertEqual(state['backend'], 'github-actions-cpu')
            self.assertTrue(state['audio_ready'])
            self.assertFalse(state['generation_started'])

    def test_failed_cpu_process_retains_song_and_resumable_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)/'song.wav'
            state = {}
            with patch.object(music.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'worker')):
                with self.assertRaisesRegex(RuntimeError, 'resume'):
                    music.generate(SONG, target, state, Mock())
            self.assertEqual(json.loads((target.parent/'cpu-song-input.json').read_text()), SONG)
            self.assertFalse(state['generation_started'])

    def test_cpu_timeout_replaces_gpu_default_before_runtime_import(self):
        with patch.dict('os.environ', {'ACESTEP_GENERATION_TIMEOUT':'600'}):
            with patch.object(music.subprocess, 'check_output', return_value='different-ref'):
                with self.assertRaises(RuntimeError):
                    music.runtime(Path('source'))
            self.assertEqual(music.os.environ['ACESTEP_GENERATION_TIMEOUT'], '18000')

    def test_parent_worker_has_a_bounded_cpu_deadline_and_recovers_on_expiry(self):
        with tempfile.TemporaryDirectory() as directory:
            state = {}
            error = subprocess.TimeoutExpired('worker', music.WORKER_TIMEOUT)
            with patch.object(music.subprocess, 'run', side_effect=error) as worker:
                with self.assertRaisesRegex(RuntimeError, 'resume'):
                    music.generate(SONG, Path(directory)/'song.wav', state, Mock())
            self.assertEqual(worker.call_args.kwargs['timeout'], 18900)
            self.assertFalse(state['generation_started'])
