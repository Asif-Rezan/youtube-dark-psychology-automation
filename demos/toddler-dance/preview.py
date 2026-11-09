"""Preview actual production image settings and toddler/animal dance motion."""
import gc
import json
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from kids_rhymes import scene_prompt

root=Path('output/toddler-dance-preview')
root.mkdir(parents=True,exist_ok=True)
outline={'characters':'Mia and Leo, two smiling toddlers in coral and teal rompers; Lumi, a fluffy baby white bunny.',
         'visual_world':'A sunny magical flower meadow, pink blossom trees, lush green grass and soft golden daylight.'}
row={'visual':'Two toddlers clap beside their fluffy bunny on a sunny meadow path.'}
prompt=scene_prompt(row,outline,True)
source=root/'scene-000-source.png'
from image_cpu import generate
if not source.exists():
    generate(prompt,source,seed=20261103,width=1024,height=576,steps=20)
# Release the diffusion model before loading the cutout and inpainting models.
import image_cpu
image_cpu._pipeline=None
gc.collect()
from character_motion import render_clip
render_clip(source,root/'toddlers-and-bunny-dance.mp4',1280,720,0,'Two toddlers and bunny dancing and bouncing together')
subprocess.run(['ffmpeg','-v','error','-y','-ss','1.1','-i',str(root/'toddlers-and-bunny-dance.mp4'),
                '-frames:v','1',str(root/'preview-frame.jpg')],check=True)
(root/'artwork-settings.json').write_text(json.dumps({'prompt':prompt,'model':image_cpu.MODEL,
    'revision':image_cpu.REVISION,'steps':20,'width':1024,'height':576,
    'guidance':image_cpu.GUIDANCE_SCALE,'note':'Production image settings unchanged; only cast/action changed'},indent=2))
