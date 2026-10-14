"""Download public model weights and generate images on a cloud CPU runner.

This does not call Hugging Face Inference Providers and consumes no inference
API credits. The default model revision is pinned for reproducibility.
"""
import argparse
import os
from pathlib import Path
import time

MODEL = 'Lykon/dreamshaper-8'
REVISION = 'a7e52b98680b1ba8ff7bce97c7f9f2e2e5337917'
_pipeline = None


def generate(prompt, path):
    global _pipeline
    import torch
    from diffusers import DiffusionPipeline, DPMSolverMultistepScheduler
    torch.set_num_threads(min(os.cpu_count() or 2, 4))
    model = os.getenv('CPU_IMAGE_MODEL') or MODEL
    revision = os.getenv('CPU_MODEL_REVISION') or (REVISION if model == MODEL else 'main')
    if _pipeline is None:
        print('Loading public image-model weights on CPU', flush=True)
        # Pinned public model repository. Torch >=2.6 is required for safer
        # weights-only loading of the legacy tensor files used by this model.
        _pipeline = DiffusionPipeline.from_pretrained(model, revision=revision,
            torch_dtype=torch.float32, use_safetensors=True, trust_remote_code=False)
        _pipeline.scheduler = DPMSolverMultistepScheduler.from_config(
            _pipeline.scheduler.config, algorithm_type='dpmsolver++', use_karras_sigmas=True)
        _pipeline.to('cpu')
        _pipeline.enable_attention_slicing()
        _pipeline.enable_vae_slicing()
    width = int(os.getenv('CPU_IMAGE_WIDTH', '768'))
    height = int(os.getenv('CPU_IMAGE_HEIGHT', '432'))
    steps = int(os.getenv('CPU_IMAGE_STEPS', '28'))
    if width % 8 or height % 8 or not 256 <= width <= 1024 or not 256 <= height <= 1024:
        raise ValueError('CPU image dimensions must be multiples of eight in 256–1024')
    if not 1 <= steps <= 50:
        raise ValueError('CPU generation requires 1–50 steps')
    start = time.monotonic()
    result = _pipeline(prompt=prompt, negative_prompt='photograph, photorealistic, live action, 3D render, CGI, extra arms, extra legs, deformed hands, duplicate person, watermark, lettering, ' + os.getenv('IMAGE_NEGATIVE_PROMPT', ''), width=width, height=height,
        num_inference_steps=steps, guidance_scale=7.5,
        generator=torch.Generator(device='cpu').manual_seed(int(os.getenv('IMAGE_SEED', '42'))))
    if any(result.nsfw_content_detected or []):
        raise RuntimeError('Image was blocked by model safety check; no substitute is generated')
    image = result.images[0]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    print(f'CPU image generated: {image.width}x{image.height}; {time.monotonic()-start:.1f}s', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--prompt', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    generate(args.prompt, args.output)
