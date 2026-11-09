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


def synthesize(song, target, source, model_root):
    from pipeline import validate_song, validate_duration, duration
    # Segment requests are derived from a validated full-song manifest.
    if not song.get('_segment'):
        validate_song(song)
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
        duration=song['duration'], bpm=song.get('bpm'), reference_audio=reference_audio(), vocal_language='en', instrumental=False,
        inference_steps=inference_steps(), thinking=False, use_cot_metas=False,
        use_cot_caption=False, use_cot_language=False)
    config = Config(batch_size=1, audio_format='wav', allow_lm_batch=False)
    print(json.dumps({'phase':'synthesizing music', 'device':'cpu',
        'duration':song['duration'], 'steps':inference_steps()}), flush=True)
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


def inference_steps():
    """The pinned turbo checkpoint is distilled for 8 steps; allow bounded tuning."""
    steps = int(os.getenv('ACESTEP_INFERENCE_STEPS', '8'))
    if not 1 <= steps <= 20:
        raise ValueError('ACESTEP_INFERENCE_STEPS must be 1-20 for the turbo model')
    return steps


def reference_audio():
    value = os.getenv('REFERENCE_AUDIO_PATH')
    if value and not Path(value).is_file():
        raise ValueError('REFERENCE_AUDIO_PATH does not exist')
    return str(Path(value).resolve()) if value else None


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
