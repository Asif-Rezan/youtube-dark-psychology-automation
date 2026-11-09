"""Replay the actual failed Short checkpoint without loading the music model."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import music_cpu
import short_music
from audio_mastering import audio_duration,verify_continuity

parser=argparse.ArgumentParser()
parser.add_argument('--run-id',required=True)
args=parser.parse_args()

def unexpected_inference(*_args,**_kwargs):
    raise AssertionError('Checkpoint recovery unexpectedly requested AI regeneration')
music_cpu.generate_segment=unexpected_inference
output=short_music.prepare(args.run_id,0,40)
window=verify_continuity(output,40,allow_edge_trim=False)
state=json.loads((output.parent/'music-state.json').read_text())
report=dict(passed=True,actual_failed_checkpoint=True,no_ai_regeneration=True,
            duration=audio_duration(output),recovered_candidate=state['recovered_candidate'],
            mastering=state['mastering'],final_window=window)
Path('output/audio-continuity-regression.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report),flush=True)
