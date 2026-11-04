"""Keep full-suite workflow jobs independent of runner image audio packages."""
from pathlib import Path
import re
import unittest


WORKFLOWS = Path(__file__).parent / '.github' / 'workflows'


def jobs_missing_audio_tools(source):
    jobs = re.split(r'(?m)^  ([A-Za-z_][A-Za-z0-9_-]*):\s*$', source)
    missing = []
    for name, body in zip(jobs[1::2], jobs[2::2]):
        suite = re.search(r'\bpython(?:3)? -m unittest\b', body)
        if suite and not re.search(
            r'\bbash scripts/install-runner-packages\.sh\s+ffmpeg\b',
            body[:suite.start()],
        ):
            missing.append(name)
    return missing


class WorkflowMediaDependenciesTests(unittest.TestCase):
    def test_full_suite_jobs_install_audio_tools_before_tests(self):
        for path in sorted(WORKFLOWS.glob('*.y*ml')):
            with self.subTest(workflow=path.name):
                self.assertEqual(jobs_missing_audio_tools(path.read_text()), [],
                                 'Install ffmpeg (including ffprobe) before the full suite.')

    def test_guard_rejects_missing_late_and_other_job_installs(self):
        source = '''jobs:
  tests:
    steps:
      - run: python -m unittest -v
  media:
    steps:
      - run: bash scripts/install-runner-packages.sh ffmpeg
'''
        self.assertEqual(jobs_missing_audio_tools(source), ['tests'])
        late = source.replace('  media:\n    steps:\n', '')
        self.assertEqual(jobs_missing_audio_tools(late), ['tests'])
        fixed = source.replace('      - run: python',
                               '      - run: bash scripts/install-runner-packages.sh ffmpeg\n      - run: python')
        self.assertEqual(jobs_missing_audio_tools(fixed), [])


if __name__ == '__main__':
    unittest.main()
