"""Download public model weights and generate images on a cloud CPU runner.

This does not call Hugging Face Inference Providers and consumes no inference
API credits. The default model revision is pinned for reproducibility.
"""
import argparse
import os
from pathlib import Path
import time
import re


class ImageSafetyBlocked(RuntimeError):
    """The model's safety checker rejected a generated image."""


def safer_prompt(prompt):
    """Keep the scene's setting and props while removing graphic/sexual details."""
    replacements = [
        (r'\b(?:bloodied|bloody|gory|gore|bleeding|bloodstains?)\b', 'dramatic'),
        (r'\b(?:corpse|dead body|mutilated body)\b', 'unoccupied place'),
        (r'\b(?:nude|naked|undressed|lingerie|underwear)\b', 'fully clothed'),
        (r'\b(?:strangling|stabbing|shooting|beating|torturing|assaulting)\b', 'confronting'),
        (r'\b(?:knife|gun|pistol|weapon)\b', 'personal belongings'),
        (r'\b(?:sexual assault|rape|abuse)\b', 'tense disagreement'),
        (r'\b(?:wound|injury|bruises?)\b', 'signs of distress'),
    ]
    for pattern, replacement in replacements:
        prompt = re.sub(pattern, replacement, prompt, flags=re.I)
    # Preserve the scene's visual anchor before the encoders' token limit.
    return prompt + ' Gentle child-friendly storybook scene, no violence.'

def recovery_prompt(prompt):
    """Keep the musical mood with a restrained fully clothed composition."""
    return safer_prompt(prompt + ' Keep the same complete cast together, fully clothed, gentle expressions, separate full bodies.')


# Pinned to the same public model as the Rezan After Dark reference project.
MODEL = 'segmind/SSD-1B'
REVISION = '60987f37e94cd59c36b1cba832b9f97b57395a10'
GUIDANCE_SCALE = 7.0


def negative_prompt():
    return ('text, letters, typography, captions, Hindi writing, title, signature, watermark, logo, '
            'poster, magazine, red brushwork, elderly, old man, gray hair, deep wrinkles, '
            'orange skin, underexposed faces, silhouette, crowd, fused faces, '
            'duplicated face, cropped head, extreme close-up, deformed hands, extra limbs, extra ears, extra tails, '
            'plastic skin, blur, low quality, photorealistic, horror, frightening, collage, split screen, '
            'black panel, border, plain studio background, seamless white background, empty backdrop, ' + os.getenv('IMAGE_NEGATIVE_PROMPT', ''))



_pipeline = None

def generate(prompt, path, seed, allow_text=False, width=None, height=None, steps=None, reference_image=None, strength=None):
    if allow_text:
        raise ValueError('Dudi Dam TV artwork must be text-free')
    if reference_image is None and strength is not None:
        raise ValueError('Image-to-image strength requires a reference image')
    if reference_image is not None:
        if strength is None or not 0 < float(strength) <= 1:
            raise ValueError('Reference image strength must be greater than zero and at most one')
        from PIL import Image, ImageOps
        with Image.open(reference_image) as source:
            initial_image=ImageOps.exif_transpose(source).convert('RGB')
    global _pipeline
    import torch
    from diffusers import DiffusionPipeline, DPMSolverMultistepScheduler
    torch.set_num_threads(min(os.cpu_count() or 2, 4))
    width = width if width is not None else int(os.getenv('CPU_IMAGE_WIDTH', '1024'))
    height = height if height is not None else int(os.getenv('CPU_IMAGE_HEIGHT', '576'))
    steps = steps if steps is not None else int(os.getenv('CPU_IMAGE_STEPS', '16'))
    if width % 8 or height % 8 or not 256 <= width <= 1536 or not 256 <= height <= 1536:
        raise ValueError('CPU image dimensions must be multiples of eight in 256–1536')
    if not 1 <= steps <= 50:
        raise ValueError('CPU generation requires 1–50 steps')
    if reference_image is not None and int(steps*float(strength)) < 1:
        raise ValueError('Reference strength and steps must produce at least one denoising step')
    model, revision = MODEL, REVISION
    if _pipeline is None:
        print('Loading public image-model weights on CPU', flush=True)
        # Pinned public SSD-1B safetensors on CPU. Keep the model's safety checker.
        _pipeline = DiffusionPipeline.from_pretrained(model, revision=revision,
            torch_dtype=torch.float32, use_safetensors=True, trust_remote_code=False, token=False)
        _pipeline.scheduler = DPMSolverMultistepScheduler.from_config(
            _pipeline.scheduler.config, algorithm_type='dpmsolver++', use_karras_sigmas=True)
        _pipeline.to('cpu')
        _pipeline.enable_attention_slicing()
        _pipeline.enable_vae_slicing()
    pipeline = _pipeline
    reference_options={}
    if reference_image is not None:
        from diffusers import AutoPipelineForImage2Image
        # Share existing SSD-1B components; do not load a second copy of weights.
        pipeline=AutoPipelineForImage2Image.from_pipe(_pipeline)
        initial_image=ImageOps.fit(initial_image,(width,height),method=Image.Resampling.LANCZOS)
        reference_options=dict(image=initial_image,strength=float(strength))
    start = time.monotonic()
    image = None
    initial_prompt = safer_prompt(prompt)
    rewritten = recovery_prompt(prompt)
    for attempt in range(10):
        # Five seeds per composition; keep input sanitization and output checks.
        candidate = initial_prompt if attempt < 5 else rewritten
        if attempt == 5:
            print('Five safety rejections; retrying a restrained music portrait.', flush=True)
        result = pipeline(prompt=candidate, negative_prompt=negative_prompt(), width=width, height=height,
            num_inference_steps=steps, guidance_scale=GUIDANCE_SCALE,
            generator=torch.Generator(device='cpu').manual_seed(seed + attempt * 10007),**reference_options)
        if any(getattr(result, 'nsfw_content_detected', None) or []):
            print(f'Image safety check rejected attempt {attempt+1}/10.', flush=True)
            continue
        image = result.images[0]
        break
    if image is None:
        raise ImageSafetyBlocked('Image blocked after five initial and five rewritten-prompt attempts; preserve run for review')
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    print(f'CPU image generated: {image.width}x{image.height}; {time.monotonic()-start:.1f}s', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--prompt', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    generate(args.prompt, args.output, seed=42)
