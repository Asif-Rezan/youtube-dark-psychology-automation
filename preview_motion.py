"""Make a short local motion preview from images, without Google or model access."""
import argparse
from pathlib import Path
import shutil
from motion_video import render_scenes, run_ffmpeg


def preview(images, output, audio=None, width=960,height=540):
    output=Path(output).resolve()
    output.parent.mkdir(parents=True,exist_ok=True)
    work=output.parent/(output.stem+'-sources')
    work.mkdir(exist_ok=True)
    for i,path in enumerate(images):
        shutil.copyfile(path,work/f'scene-{i:03d}-source.png')
    listing=render_scenes(work,[{'index':i} for i in range(len(images))],width,height)
    args=['-f','concat','-safe','1','-i',str(listing)]
    if audio:
        args+=['-i',str(Path(audio).resolve())]
    args+=['-map','0:v:0','-c:v','copy']
    if audio:
        args+=['-map','1:a:0','-c:a','aac','-b:a','192k']
    args+=['-t',str(5*len(images)),'-movflags','+faststart',str(output)]
    run_ffmpeg(args)
    return output


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('images',nargs='+',type=Path)
    parser.add_argument('--audio',type=Path)
    parser.add_argument('--output',type=Path,default=Path('output/motion-preview.mp4'))
    args=parser.parse_args()
    print(preview(args.images,args.output,args.audio))
