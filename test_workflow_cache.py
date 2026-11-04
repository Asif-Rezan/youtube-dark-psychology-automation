"""Prevent optional cache teardown from failing successful inference jobs."""
from pathlib import Path
import unittest

import yaml


def cache_conflicts(workflow):
    conflicts = []
    for name, job in workflow.get('jobs', {}).items():
        steps = job.get('steps', [])
        disables_cache = any('--no-cache-dir' in str(step.get('run', '')) for step in steps)
        caches_pip = any(
            str(step.get('uses', '')).startswith('actions/setup-python@')
            and step.get('with', {}).get('cache') == 'pip'
            for step in steps
        )
        if disables_cache and caches_pip:
            conflicts.append(name)
    return conflicts


class WorkflowCacheTests(unittest.TestCase):
    def test_no_cache_installs_do_not_enable_pip_cache_teardown(self):
        for path in (Path(__file__).parent / '.github/workflows').glob('*.yml'):
            with self.subTest(workflow=path.name):
                self.assertEqual(cache_conflicts(yaml.safe_load(path.read_text())), [],
                                 'Remove setup-python pip caching from jobs using --no-cache-dir')

    def test_detects_original_missing_cache_configuration(self):
        workflow = {'jobs': {'images': {'steps': [
            {'uses': 'actions/setup-python@v5', 'with': {'cache': 'pip'}},
            {'run': 'pip install --no-cache-dir -r requirements-images-cpu.txt'},
        ]}}}
        self.assertEqual(cache_conflicts(workflow), ['images'])
        workflow['jobs']['images']['steps'][0]['with'].pop('cache')
        self.assertEqual(cache_conflicts(workflow), [])
