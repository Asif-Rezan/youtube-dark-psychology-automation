"""Dependency outages must preserve the pinned backend and bound retries."""
import subprocess
import unittest
from unittest.mock import patch
from install_lyrics_dependencies import install


class LyricsDependencyTests(unittest.TestCase):
    def test_successful_wheel_does_not_compile(self):
        with patch('install_lyrics_dependencies.subprocess.run') as run:
            install()
        self.assertEqual(run.call_count, 2)

    def test_wheel_outage_builds_same_pinned_version_on_cpu(self):
        failure = subprocess.CalledProcessError(1, ['pip'])
        with patch('install_lyrics_dependencies.subprocess.run',
                   side_effect=[None, failure, failure, None]) as run:
            install()
        command = run.call_args.args[0]
        self.assertIn('llama-cpp-python==0.3.36', command)
        self.assertIn('--no-binary=llama-cpp-python', command)
        self.assertIn('https://pypi.org/simple', command)
        self.assertIn('-DGGML_CUDA=OFF', run.call_args.kwargs['env']['CMAKE_ARGS'])
        self.assertEqual(run.call_args.kwargs['timeout'], 1200)

    def test_source_failure_propagates_without_unbounded_retries(self):
        failure = subprocess.CalledProcessError(1, ['pip'])
        with patch('install_lyrics_dependencies.subprocess.run',
                   side_effect=[None, failure, failure, failure]) as run:
            with self.assertRaises(subprocess.CalledProcessError):
                install()
        self.assertEqual(run.call_count, 4)
