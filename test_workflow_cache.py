"""Prevent successful generation jobs failing in setup-python cache teardown."""
from pathlib import Path
import re
import unittest


WORKFLOWS = Path(__file__).parent / ".github" / "workflows"


def conflicting_jobs(source):
    # Workflow job headers use two spaces; step names and run scripts are deeper.
    jobs = re.split(r"(?m)^  ([A-Za-z_][A-Za-z0-9_-]*):\s*$", source)
    return [
        name for name, body in zip(jobs[1::2], jobs[2::2])
        if "--no-cache-dir" in body
        and re.search(r"(?m)^\s+cache:\s*['\"]?pip['\"]?\s*(?:#.*)?$", body)
    ]


class WorkflowCacheTests(unittest.TestCase):
    def test_no_cache_installs_do_not_enable_setup_python_pip_cache(self):
        for path in sorted(WORKFLOWS.glob("*.y*ml")):
            with self.subTest(workflow=path.name):
                self.assertEqual(
                    conflicting_jobs(path.read_text()), [],
                    "Remove setup-python cache: pip from jobs using --no-cache-dir; "
                    "an absent pip cache makes post-job teardown fail.",
                )

    def test_guard_detects_conflict_without_flagging_separate_cached_job(self):
        source = """jobs:
  generate:
    steps:
      - uses: actions/setup-python@v5
        with:
          cache: pip
      - run: pip install --no-cache-dir -r requirements.txt
  publish:
    steps:
      - uses: actions/setup-python@v5
        with:
          cache: pip
      - run: pip install -r requirements.txt
"""
        self.assertEqual(conflicting_jobs(source), ["generate"])
        self.assertEqual(conflicting_jobs(source.replace("          cache: pip\n", "")), [])


if __name__ == "__main__":
    unittest.main()
