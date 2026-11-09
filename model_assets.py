"""Pinned public model downloads, shared by cache preparation and inference."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request

MOTION = {
    'birefnet-general-lite.onnx': dict(
        urls=['https://github.com/danielgatis/rembg/releases/download/v0.0.0/BiRefNet-general-bb_swin_v1_tiny-epoch_232.onnx',
              'https://api.github.com/repos/danielgatis/rembg/releases/assets/188373238'],
        size=224005088, md5='4fab47adc4ff364be1713e97b7e66334'),
    'big-lama.pt': dict(
        urls=['https://github.com/enesmsahin/simple-lama-inpainting/releases/download/v0.1.0/big-lama.pt',
              'https://api.github.com/repos/enesmsahin/simple-lama-inpainting/releases/assets/88575092'],
        size=205803670, sha256='7ba7aa7ac37a4d41fdbbeba3a2af7ead18058552997e3a3cd1a3b2210c9e6b4c'),
}


def motion_root():
    return Path(os.getenv('MOTION_MODEL_CACHE', '.models/motion')).resolve()


def valid_file(path, spec):
    if not path.is_file() or path.stat().st_size != spec['size']:
        return False
    for algorithm in ('sha256', 'md5'):
        if algorithm in spec:
            digest = hashlib.new(algorithm)
            with path.open('rb') as handle:
                for block in iter(lambda: handle.read(1024 * 1024), b''):
                    digest.update(block)
            if digest.hexdigest() != spec[algorithm]:
                return False
    return True


def download_asset(path, spec):
    """Never expose partial/corrupt weights; alternate official delivery endpoints."""
    path = Path(path)
    if valid_file(path, spec):
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f'.{os.getpid()}.partial')
    for attempt in range(4):
        try:
            url = spec['urls'][attempt % len(spec['urls'])]
            request = urllib.request.Request(url, headers={'Accept': 'application/octet-stream',
                                                         'User-Agent': 'youtube-model-cache'})
            deadline = time.monotonic() + 600
            with urllib.request.urlopen(request, timeout=45) as response, temporary.open('wb') as out:
                size = 0
                while block := response.read(1024 * 1024):
                    size += len(block)
                    if size > spec['size'] or time.monotonic() > deadline:
                        raise ValueError('Model download exceeded its size/time budget')
                    out.write(block)
            if not valid_file(temporary, spec):
                raise ValueError('Model size/checksum verification failed')
            temporary.replace(path)
            return path
        except (urllib.error.URLError, OSError, ValueError) as error:
            temporary.unlink(missing_ok=True)
            print(json.dumps({'phase': 'model download retry', 'file': path.name,
                              'attempt': attempt + 1, 'error_type': type(error).__name__}), flush=True)
            if attempt == 3:
                raise RuntimeError(f'Model download failed after four attempts: {path.name}') from error
            time.sleep(min(2 ** attempt, 8))
    raise AssertionError('unreachable')


def ensure_motion_models():
    root = motion_root()
    for name, spec in MOTION.items():
        download_asset(root / name, spec)
    return root


def settings(family):
    if family == 'motion':
        spec = MOTION
    elif family == 'images':
        from image_cpu import MODEL, REVISION
        spec = dict(repo=MODEL, revision=REVISION, dtype='float32-safetensors')
    elif family == 'music':
        from music_cpu import MODEL_REPO, MODEL_REVISION, COMPONENTS
        spec = dict(repo=MODEL_REPO, revision=MODEL_REVISION, components=COMPONENTS)
    elif family == 'lyrics':
        from lyrics_cpu import GGUF_REPO, GGUF_REVISION, GGUF_FILE, GGUF_SHA256
        spec = dict(repo=GGUF_REPO, revision=GGUF_REVISION, filename=GGUF_FILE, sha256=GGUF_SHA256)
    else:
        raise ValueError('Unknown model family')
    root = Path('.models') / ('acestep' if family == 'music' else family)
    identity = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:24]
    return root, f'model-v1-{family}-{identity}', spec


def prepare(family):
    root, key, spec = settings(family)
    if family == 'motion':
        ensure_motion_models()
    else:
        from huggingface_hub import hf_hub_download, snapshot_download
        for attempt in range(3):
            try:
                if family == 'lyrics':
                    from lyrics_cpu import verify_model
                    path = hf_hub_download(repo_id=spec['repo'], revision=spec['revision'],
                                           filename=spec['filename'], cache_dir=str(root), token=False)
                    if not verify_model(path):
                        Path(path).unlink(missing_ok=True)
                        raise ValueError('Pinned lyric model checksum mismatch')
                elif family == 'music':
                    from music_cpu import checkpoints
                    checkpoints(root)
                else:
                    # Match DiffusionPipeline's float32 safetensors exactly. Exclude
                    # alternate fp16 weights and redundant 4GB monolithic exports.
                    patterns = ['model_index.json', 'scheduler/*', 'tokenizer/*', 'tokenizer_2/*']
                    for part in ('text_encoder', 'text_encoder_2'):
                        patterns += [part + '/config.json', part + '/model.safetensors']
                    for part in ('unet', 'vae'):
                        patterns += [part + '/config.json', part + '/diffusion_pytorch_model.safetensors']
                    snapshot_download(repo_id=spec['repo'], revision=spec['revision'],
                                      allow_patterns=patterns, cache_dir=str(root), token=False, max_workers=2)
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(2 ** (attempt + 1))
    print(json.dumps({'phase': 'model cache ready', 'family': family, 'key': key}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('family', choices=['motion', 'images', 'music', 'lyrics'])
    parser.add_argument('--settings', action='store_true')
    args = parser.parse_args()
    if args.settings:
        root, key, _ = settings(args.family)
        with open(os.environ['GITHUB_OUTPUT'], 'a') as out:
            out.write(f'path={root}\nkey={key}\n')
    else:
        prepare(args.family)
