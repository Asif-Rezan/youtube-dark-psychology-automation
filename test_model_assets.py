import hashlib
import io
from pathlib import Path
import tempfile
import unittest
import urllib.error
from unittest.mock import patch
import yaml
import model_assets as assets


class DownloadTests(unittest.TestCase):
    def spec(self, data=b'verified weights'):
        return dict(urls=['https://github.com/release', 'https://api.github.com/asset'],
                    size=len(data), sha256=hashlib.sha256(data).hexdigest())

    def test_504_retries_official_asset_api_and_atomically_publishes_verified_file(self):
        data = b'verified weights'
        error = urllib.error.HTTPError('https://github.com/release', 504, 'gateway', {}, None)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'model.pt'
            with patch('model_assets.urllib.request.urlopen', side_effect=[error, io.BytesIO(data)]) as request, \
                 patch('model_assets.time.sleep'):
                assets.download_asset(path, self.spec())
            self.assertEqual(path.read_bytes(), data)
            self.assertEqual(request.call_args.args[0].full_url, 'https://api.github.com/asset')
            self.assertEqual(list(Path(tmp).glob('*.partial')), [])
            with patch('model_assets.urllib.request.urlopen', side_effect=AssertionError('Network on cache hit')):
                assets.download_asset(path, self.spec())

    def test_corrupt_weight_does_not_replace_existing_file_and_retry_is_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'model.pt'
            path.write_bytes(b'existing cache')
            with patch('model_assets.urllib.request.urlopen', side_effect=lambda *a, **kw: io.BytesIO(b'bad')), \
                 patch('model_assets.time.sleep') as sleep:
                with self.assertRaisesRegex(RuntimeError, 'four attempts'):
                    assets.download_asset(path, self.spec())
            self.assertEqual(sleep.call_count, 3)
            self.assertEqual(path.read_bytes(), b'existing cache')
            self.assertEqual(list(Path(tmp).glob('*.partial')), [])

    def test_same_size_corruption_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'model.pt'
            path.write_bytes(b'x' * self.spec()['size'])
            self.assertFalse(assets.valid_file(path, self.spec()))


class CacheContractTests(unittest.TestCase):
    def test_keys_are_stable_across_runs_and_change_with_model_revision(self):
        original = assets.settings('images')
        with patch('image_cpu.REVISION', 'different-reviewed-revision'):
            changed = assets.settings('images')
        self.assertNotEqual(original[1], changed[1])
        self.assertEqual(original[0], changed[0])
        self.assertEqual(original, assets.settings('images'))
        for family in ('lyrics', 'music', 'images', 'motion'):
            path, key, _ = assets.settings(family)
            self.assertTrue(str(path).startswith('.models/'))
            self.assertNotIn('run_id', key)

    def test_cache_save_occurs_before_inference_and_has_no_prefix_fallback(self):
        action = yaml.safe_load(Path('.github/actions/model-cache/action.yml').read_text())
        steps = action['runs']['steps']
        restore = next(s for s in steps if s.get('uses') == 'actions/cache/restore@v4')
        save = next(s for s in steps if s.get('uses') == 'actions/cache/save@v4')
        self.assertEqual(restore['with'], save['with'])
        self.assertNotIn('restore-keys', restore['with'])
        self.assertIn('cache-hit', save['if'])
        self.assertIn("inputs.family != 'music'", restore['if'])
        self.assertIn("inputs.family != 'music'", save['if'])
        self.assertTrue(any('model_assets.py' in s.get('run', '') for s in steps))

    def test_production_and_manual_shorts_restore_each_required_model(self):
        contracts = {
            'music.yml': {'lyrics': ['lyrics'], 'music': ['music'], 'short_music': ['music'],
                          'images': ['images', 'motion'], 'short_images': ['images', 'motion']},
            'shorts.yml': {'short_music': ['music'], 'short_images': ['images', 'motion']},
        }
        for name, jobs in contracts.items():
            workflow = yaml.safe_load((Path('.github/workflows') / name).read_text())
            for job, families in jobs.items():
                steps = workflow['jobs'][job]['steps']
                restored = [s['with']['family'] for s in steps if s.get('uses') == './.github/actions/model-cache']
                self.assertEqual(restored, families, (name, job))
                if any('--no-cache-dir' in s.get('run', '') for s in steps):
                    self.assertFalse(any(s.get('with', {}).get('cache') == 'pip' for s in steps))
        workflow = yaml.safe_load(Path('.github/workflows/music.yml').read_text())
        self.assertEqual(workflow['jobs']['lyrics']['needs'], 'models')
        self.assertEqual(workflow['jobs']['models']['strategy']['matrix']['family'], ['lyrics','images','motion'])

    def test_image_prefetch_excludes_unused_weight_variants(self):
        with patch('huggingface_hub.snapshot_download') as download:
            assets.prepare('images')
        options = download.call_args.kwargs
        self.assertEqual(options['cache_dir'], '.models/images')
        self.assertIn('unet/diffusion_pytorch_model.safetensors', options['allow_patterns'])
        self.assertNotIn('*', options['allow_patterns'])
        self.assertFalse(any('fp16' in pattern for pattern in options['allow_patterns']))


class StageRecoveryTests(unittest.TestCase):
    def test_resume_restores_matching_shards_before_regenerating(self):
        jobs = yaml.safe_load(Path('.github/workflows/music.yml').read_text())['jobs']
        for job in ('images', 'short_images', 'short_music'):
            steps = jobs[job]['steps']
            restore = next(s for s in steps if s.get('name') == 'Restore saved stage assets when resuming')
            self.assertIn("inputs.prepared_run != ''", restore['if'])
            self.assertIn('needs.lyrics.outputs.restore_artifacts', restore['if'])
            self.assertEqual(restore['with']['run-id'], '${{ inputs.prepared_run }}')
            generate = next(s for s in steps if s.get('name', '').startswith('Generate '))
            self.assertLess(steps.index(restore), steps.index(generate))
