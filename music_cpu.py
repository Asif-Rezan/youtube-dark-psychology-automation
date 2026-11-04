"""Run pinned ACE-Step 1.5 music inference on a GitHub Actions CPU runner."""
import argparse
from contextlib import contextmanager
import importlib
import resource
import threading
import time
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

SOURCE_REVISION = 'ca1e85fe9430179831e6bc6be790c332190a3866'
MODEL_REPO = 'ACE-Step/Ace-Step1.5'
MODEL_REVISION = '19671f406d603126926c1b7e2adc169acbcade22'
MODEL = 'acestep-v15-turbo'
COMPONENTS = (MODEL, 'vae', 'Qwen3-Embedding-0.6B')
CPU_GENERATION_TIMEOUT = 18000
WORKER_TIMEOUT = CPU_GENERATION_TIMEOUT + 900
DEFAULT_REFERENCE_AUDIO = Path(__file__).resolve().parent/'assets/reference/style-reference.mp3'


def checkpoints(root):
    from huggingface_hub import snapshot_download
    snapshot_download(repo_id=MODEL_REPO, revision=MODEL_REVISION,
        allow_patterns=[name + '/*' for name in COMPONENTS],
        local_dir=str(root), token=False, max_workers=2)
    for name in COMPONENTS:
        if not any((root/name).glob('*.safetensors')):
            raise RuntimeError('Missing pinned ACE-Step component: ' + name)


def configure_cpu_timeout():
    # Upstream reads this once, at module import, with a GPU-oriented 600s default.
    os.environ['ACESTEP_GENERATION_TIMEOUT'] = str(CPU_GENERATION_TIMEOUT)


@contextmanager
def generation_progress():
    started = time.monotonic()
    stop = threading.Event()
    def report():
        while not stop.wait(60):
            usage = resource.getrusage(resource.RUSAGE_SELF)
            print(json.dumps({'phase':'CPU synthesis running',
                'elapsed_seconds':round(time.monotonic()-started),
                'cpu_seconds':round(usage.ru_utime+usage.ru_stime),
                'peak_memory_mb':round(usage.ru_maxrss/1024)}), flush=True)
    reporter = threading.Thread(target=report, daemon=True)
    reporter.start()
    try:
        yield
    finally:
        stop.set()
        reporter.join(timeout=1)


def runtime(source):
    configure_cpu_timeout()
    revision = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != SOURCE_REVISION:
        raise RuntimeError('ACE-Step source revision differs from the reviewed version')
    sys.path.insert(0, str(source))
    import torch
    from acestep.handler import AceStepHandler
    from acestep.inference import GenerationParams, GenerationConfig, generate_music

    execution = importlib.import_module('acestep.core.generation.handler.generate_music_execute')
    if execution._DEFAULT_GENERATION_TIMEOUT != CPU_GENERATION_TIMEOUT:
        raise RuntimeError('ACE-Step was imported before the CPU timeout was configured')
    print(json.dumps({'check':'native CPU generation timeout',
        'seconds':execution._DEFAULT_GENERATION_TIMEOUT}), flush=True)

    class CpuHandler(AceStepHandler):
        def _ensure_models_present(self, *, checkpoint_path, config_path, prefer_source, vae_variant=None):
            # Upstream's convenience downloader also requires a 1.7B planning LM.
            # This workflow uses Qwen lyrics and DiT-only synthesis, so verify
            # only the three pinned components actually used by inference.
            if config_path != MODEL:
                raise RuntimeError('Unexpected music model')
            for name in COMPONENTS:
                if not any((checkpoint_path/name).glob('*.safetensors')):
                    raise RuntimeError('Music component missing: ' + name)
            return None

    return torch, CpuHandler, GenerationParams, GenerationConfig, generate_music


def reference_cover_options(song, reference):
    """Pinned ACE-Step: higher cover_noise_strength is closer to source audio."""
    import math
    if not song.get('reference_cover'):
        return {}
    strength = float(song.get('cover_strength', 1.0))
    noise = float(song.get('cover_noise_strength', 0.2))
    if not all(math.isfinite(v) and 0 <= v <= 1 for v in (strength, noise)):
        raise ValueError('Reference cover strengths must be finite values in 0..1')
    return dict(task_type='cover', src_audio=reference,
                audio_cover_strength=strength, cover_noise_strength=noise)


def prepare_cover_source(reference, seconds, directory):
    """Cover inference follows source length: trim long references, never loop short ones."""
    import hashlib
    import math
    from pipeline import duration
    seconds = float(seconds)
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError('Cover duration must be finite and positive')
    reference = Path(reference)
    measured = duration(reference)
    if measured < seconds - .05:
        raise ValueError('Reference cover source is shorter than the requested segment')
    if abs(measured - seconds) <= .05:
        return str(reference)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with reference.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            digest.update(chunk)
    digest.update(str(seconds).encode())
    target = directory / ('cover-source-'+digest.hexdigest()[:16]+'.wav')
    if not target.exists() or abs(duration(target)-seconds) > .05:
        temporary = target.with_suffix('.part.wav')
        try:
            subprocess.run(['ffmpeg','-y','-v','error','-i',str(reference),
                '-t',str(seconds),'-ar','48000','-ac','2',str(temporary)],check=True)
            if abs(duration(temporary)-seconds) > .05:
                raise ValueError('Prepared cover source duration mismatch')
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    return str(target)


def synthesize(song, target, source, model_root):
    from pipeline import validate_song, validate_duration, duration
    # Segment requests are derived from a validated full-song manifest.
    if not song.get('_segment'):
        validate_song(song)
    reference = reference_audio()
    cover_options = reference_cover_options(song, reference)
    if cover_options:
        cover_options['src_audio'] = prepare_cover_source(reference, song['duration'], target.parent)
    checkpoints(model_root)
    os.environ['ACESTEP_CHECKPOINTS_DIR'] = str(model_root.resolve())
    os.environ['ACESTEP_INIT_LLM'] = 'false'
    os.environ['CUDA_VISIBLE_DEVICES'] = ''
    os.environ['ACESTEP_VAE_DECODE_CHUNK_SIZE'] = '128'
    torch, Handler, Params, Config, infer = runtime(source)
    torch.set_num_threads(min(3, max(1, (os.cpu_count() or 1) - 1)))
    torch.set_num_interop_threads(1)
    handler = Handler()
    print(json.dumps({'phase':'loading music model', 'model':MODEL, 'device':'cpu'}), flush=True)
    _, ready = handler.initialize_service(project_root=str(source), config_path=MODEL,
        device='cpu', use_flash_attention=False, compile_model=False,
        offload_to_cpu=False, offload_dit_to_cpu=False, quantization=None,
        prefer_source='huggingface', use_mlx_dit=False)
    if not ready or handler.device != 'cpu':
        raise RuntimeError('ACE-Step CPU initialization failed')
    params = Params(caption=song['prompt'], lyrics=song['lyrics'],
        duration=song['duration'], bpm=song.get('bpm'), reference_audio=reference, vocal_language=song.get('vocal_language','en'), instrumental=False,
        inference_steps=8, thinking=False, use_cot_metas=False,
        use_cot_caption=False, use_cot_language=False, **cover_options)
    seed = song.get('generation_seed')
    seed_options = dict(use_random_seed=False, seeds=[int(seed)]) if seed is not None else {}
    config = Config(batch_size=1, audio_format='wav', allow_lm_batch=False, **seed_options)
    print(json.dumps({'phase':'synthesizing music', 'device':'cpu',
        'duration':song['duration'], 'steps':8}), flush=True)
    with torch.inference_mode(), generation_progress():
        result = infer(handler, None, params, config, save_dir=str(target.parent/'cpu-audio'))
    if not result.success or not result.audios:
        raise RuntimeError('ACE-Step CPU music synthesis failed')
    audio = Path(result.audios[0]['path'])
    if abs(duration(audio) - song['duration']) > 2:
        raise RuntimeError('Generated segment duration differs from requested duration')
    temporary = target.with_suffix('.part.wav')
    shutil.copyfile(audio, temporary)
    temporary.replace(target)
    print(json.dumps({'phase':'music ready', 'duration':duration(target), 'device':'cpu'}), flush=True)


def reference_audio():
    # Match the motivation project's bundled style even outside Actions.
    # Resolve repository-relative overrides independently of the worker's cwd.
    value = os.getenv('REFERENCE_AUDIO_PATH', '').strip()
    path = Path(value).expanduser() if value else DEFAULT_REFERENCE_AUDIO
    if not path.is_absolute():
        path = Path(__file__).resolve().parent/path
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError('Reference audio is missing or empty: ' + str(path))
    return str(path.resolve())


def generate(song, target, state, save):
    from kids_rhymes import generate_music
    return generate_music(song, target, state, save)


def generate_segment(song, target, state, save):
    # Local CPU generation has no remote task to duplicate. A failed or killed
    # runner can regenerate the same saved lyrics without resubmitting to a service.
    from pipeline import validate_duration, duration
    if target.exists():
        if abs(duration(target) - song['duration']) > 2:
            raise ValueError('Invalid saved segment duration')
        return
    source = Path(os.environ.get('ACESTEP_SOURCE_DIR', '.vendor/ace-step')).resolve()
    model_root = Path(os.environ.get('ACESTEP_CHECKPOINTS_DIR', '.models/acestep')).resolve()
    state.update(backend='github-actions-cpu', generation_started=True)
    save()
    request = target.parent/'cpu-song-input.json'
    request.write_text(json.dumps(song, ensure_ascii=False))
    from worker_limits import run_worker, WorkerFailure
    try:
        run_worker([sys.executable, '-u', str(Path(__file__).resolve()),
            '--song', str(request.resolve()), '--target', str(target.resolve()),
            '--source', str(source), '--models', str(model_root)], timeout=WORKER_TIMEOUT,
            diagnostic=target.parent/'worker-resources.txt')
        if abs(duration(target) - song['duration']) > 2:
            raise ValueError('Invalid generated segment duration')
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, WorkerFailure, OSError, ValueError) as exc:
        state.update(generation_started=False, generation_failed=str(exc), audio_ready=False)
        save()
        raise RuntimeError('Local ACE-Step CPU worker failed; saved lyrics and parts retained: ' + str(exc)) from exc
    state.pop('generation_failed', None)
    state.update(audio_ready=True, generation_started=False)
    save()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--song', required=True)
    parser.add_argument('--target', required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--models', required=True)
    args = parser.parse_args()
    synthesize(json.loads(Path(args.song).read_text()), Path(args.target), Path(args.source), Path(args.models))
