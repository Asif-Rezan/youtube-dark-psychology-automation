"""Keep native CPU inference inside a bounded systemd service on Actions."""
import os
from pathlib import Path
import subprocess
import sys
import uuid


class WorkerFailure(RuntimeError):
    pass


def service_command(command, timeout, unit, memory_kib, cpus):
    # Reserve at least 25% RAM and one CPU for the runner, parent and uploads.
    memory_bytes = memory_kib * 1024 * 3 // 4
    if memory_bytes < 2 * 1024**3:
        raise WorkerFailure('Runner has insufficient RAM for bounded CPU synthesis')
    args = ['sudo', '-n', 'systemd-run', '--quiet', '--wait', '--pipe',
            '--service-type=exec', '--unit=' + unit,
            '--uid=' + str(os.getuid()), '--gid=' + str(os.getgid()),
            '--working-directory=' + str(Path.cwd()),
            '-p', 'MemoryMax=' + str(memory_bytes),
            '-p', 'MemorySwapMax=4G', '-p', 'OOMPolicy=kill',
            '-p', 'CPUQuota=' + str(max(1, cpus - 1) * 100) + '%',
            '-p', 'RuntimeMaxSec=' + str(timeout), '-p', 'TimeoutStopSec=15',
            '-p', 'KillMode=control-group']
    # The system manager does not inherit the job environment. Pass only runtime
    # settings; publication credentials are deliberately excluded.
    for key, value in os.environ.items():
        if key in {'PATH', 'HOME', 'VIRTUAL_ENV', 'LD_LIBRARY_PATH', 'REFERENCE_AUDIO_PATH',
                   'CUDA_VISIBLE_DEVICES', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'} or key.startswith(('ACESTEP_', 'HF_HUB_')):
            args.append('--setenv=' + key + '=' + value)
    return args + ['--'] + list(command)


def run_worker(command, timeout, diagnostic):
    if os.getenv('GITHUB_ACTIONS') != 'true' or sys.platform != 'linux':
        return subprocess.run(command, check=True, timeout=timeout)
    if not Path('/sys/fs/cgroup/cgroup.controllers').exists():
        raise WorkerFailure('CPU synthesis requires cgroup v2; refusing unbounded execution')
    memory = next(int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines()
                  if line.startswith('MemTotal:'))
    unit = 'acestep-' + uuid.uuid4().hex
    args = service_command(command, timeout, unit, memory, os.cpu_count() or 1)
    result = None
    report = ''
    try:
        result = subprocess.run(args, timeout=timeout + 45)
    finally:
        # Run outside the limited service so an OOM still leaves an explanation
        # and allows the workflow's always() artifact upload to execute.
        try:
            status = subprocess.run(['sudo', '-n', 'systemctl', 'show', unit,
                '--property=Result,ExecMainStatus,MemoryPeak,CPUUsageNSec'],
                capture_output=True, text=True, timeout=15)
            report = status.stdout or status.stderr
            Path(diagnostic).write_text(report)
            print(report, flush=True)
        finally:
            subprocess.run(['sudo', '-n', 'systemctl', 'stop', unit], timeout=25, check=False)
            subprocess.run(['sudo', '-n', 'systemctl', 'reset-failed', unit], timeout=15, check=False)
    if result.returncode:
        raise WorkerFailure('Bounded ACE-Step worker failed (exit %s). %s '
                            'Saved parts retained; resume the same run after reviewing resource diagnostics.'
                            % (result.returncode, report.strip()))
    return result
