"""Prefer official CPU wheels; build the same pinned release during wheel outages."""
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent


def install():
    pip = [sys.executable, '-m', 'pip', 'install', '--retries', '3', '--timeout', '45']
    subprocess.run(pip + ['-r', str(ROOT / 'requirements.txt')], check=True, timeout=600)
    for attempt in range(2):
        try:
            subprocess.run(pip + ['-r', str(ROOT / 'requirements-lyrics.txt')],
                           check=True, timeout=300)
            return
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            print(f'::warning::CPU wheel installation attempt {attempt + 1}/2 failed.', flush=True)
    # The source distribution is on PyPI, independent of GitHub release assets.
    # Do not relax the version pin or silently switch inference backends.
    pins = [line.strip() for line in (ROOT / 'requirements-lyrics.txt').read_text().splitlines()
            if line.strip() and not line.lstrip().startswith(('#', '--'))]
    if len(pins) != 1 or not pins[0].startswith('llama-cpp-python=='):
        raise RuntimeError('Expected one exact llama-cpp-python version pin')
    print('::warning::Building the pinned CPU backend from its PyPI source distribution.', flush=True)
    env = dict(os.environ, CMAKE_ARGS='-DGGML_CUDA=OFF -DGGML_BLAS=OFF',
               CMAKE_BUILD_PARALLEL_LEVEL='2')
    subprocess.run(pip + ['--index-url', 'https://pypi.org/simple',
                         '--no-binary=llama-cpp-python', pins[0]],
                   env=env, check=True, timeout=1200)


if __name__ == '__main__':
    install()
