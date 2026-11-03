"""Tiny Actions integration check: no model downloads or video generation."""
from pathlib import Path
import subprocess
import sys
import tempfile
from worker_limits import run_worker, WorkerFailure

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    output = root/'limits.txt'
    # Inspect the actual service cgroup, not a mocked command list.
    code = '''from pathlib import Path
import os
p=Path('/sys/fs/cgroup')/Path('/proc/self/cgroup').read_text().strip().split('::')[1].lstrip('/')
values=[(p/name).read_text().strip() for name in ('memory.max','memory.swap.max','cpu.max')]
assert values[0] != 'max', values
assert int(values[1]) == 4*1024**3, values
assert values[2].split()[0] != 'max', values
Path(os.environ['HOME']).exists()
Path(%r).write_text(str(values))
''' % str(output)
    run_worker([sys.executable, '-c', code], 15, root/'success.txt')
    assert output.exists(), 'Service did not execute as job user'
    print(output.read_text())
    try:
        run_worker([sys.executable, '-c', 'raise SystemExit(7)'], 15, root/'failure.txt')
    except WorkerFailure:
        assert 'ExecMainStatus=7' in (root/'failure.txt').read_text()
    else:
        raise AssertionError('Failed service reported success')
    try:
        run_worker([sys.executable, '-c', 'import time; time.sleep(30)'], 1, root/'timeout.txt')
    except WorkerFailure:
        assert 'Result=timeout' in (root/'timeout.txt').read_text()
    else:
        raise AssertionError('Service runtime limit was ignored')
print('Real cgroup limits, failure diagnostics and timeout cleanup passed')
