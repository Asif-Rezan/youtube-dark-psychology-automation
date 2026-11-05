"""Generate one review-only thumbnail using the production design and image runtime."""
import argparse
import json
import os
from pathlib import Path
from song_images import image_plan
from thumbnail_variety import next_design,generate_distinct,HISTORY_KEY,seed_existing
from thumbnail_export import export_thumbnail
from image_cpu import generate


def preview(source,output):
    candidates=sorted(Path(source).rglob('song.json'))
    if len(candidates)!=1:raise ValueError('Preview requires exactly one source song')
    song=json.loads(candidates[0].read_text())
    history=[]
    if os.getenv('DRIVE_TOKEN_JSON') and os.getenv('DRIVE_FOLDER_ID'):
        from storage import Store
        store=Store()
        history=store.load(HISTORY_KEY,[])
        seed_existing(history,store.load('history.json',[]),store)
    # A preview does not reserve a production slot or mutate the durable history.
    song['thumbnail_design']=next_design(song,'review-'+str(os.getenv('GITHUB_RUN_ID','local')),history)
    plan=image_plan(song)[-1]
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    reference=Path(plan['reference_image'])
    if not reference.is_absolute():reference=Path(__file__).resolve().parent/reference
    generate_distinct(output/'thumbnail-source.png',plan,song,generate,
                      dict(reference_image=reference,strength=plan['strength']))
    export_thumbnail(output/'thumbnail-source.png',output/'thumbnail.jpg')
    print(json.dumps({'preview_only':True,'design':song['thumbnail_design'],'output':str(output/'thumbnail.jpg')}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=Path('output/thumbnail-preview'))
    args=parser.parse_args();preview(args.source,args.output)
