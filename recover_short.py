"""Resume only an existing Shorts upload; never generate or insert a video."""
import argparse
import json
from pathlib import Path
import re

from pipeline import publish, youtube_client
from shorts import atomic_json
from storage import Store


def recover(run_id):
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}',run_id):
        raise ValueError('Invalid source run ID')
    matches=list(Path('recovery').glob(f'{run_id}/*/state.json'))
    if len(matches)!=1:
        raise ValueError('Exactly one original Shorts checkpoint required')
    local=json.loads(matches[0].read_text())
    clip=matches[0].parent.name
    if not re.fullmatch(r'(?:music-)?portrait-clip-[0-9]+-[0-9]+|clip-[0-9]+-[0-9]+',clip):
        raise ValueError('Invalid Shorts checkpoint identity')
    store=Store()
    key=f'shorts/{run_id}/{clip}/state.json'
    state=store.load(key,{})
    if not state.get('video_id') or state.get('video_id')!=local.get('video_id'):
        raise ValueError('Original uploaded video ID must match Drive checkpoint')
    if state.get('source_plan')!=local.get('source_plan'):
        raise ValueError('Source checkpoint mismatch')
    def save():
        atomic_json(matches[0],state)
        store.save(key,state)
    client=youtube_client()
    # Existing ID is mandatory above; publish takes its verification branch.
    publish(client,matches[0].parent,{},state,save,upload_thumbnail=False)
    print(json.dumps({'phase':state['phase'],'video_id':state['video_id'],
        'publish_at':state.get('schedule_target')}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--run-id',required=True)
    recover(parser.parse_args().run_id)
