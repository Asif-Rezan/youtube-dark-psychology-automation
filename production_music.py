"""Source-aligned ACE requests for the full video and its independent Short."""
import hashlib
import math
from pathlib import Path
import subprocess


def request(song, start=0):
    from kids_rhymes import REFRAIN
    source_lyrics='दूदी दूदी दम दम दूदी दूदी दम'
    target=dict(song)
    target['lyrics']=song['lyrics'].replace(REFRAIN,source_lyrics)
    target.update(reference_cover=True,flow_edit_morph=True,flow_edit_task='text2music',
        flow_edit_n_min=0.0,source_lyrics=source_lyrics,
        source_lyrics_provenance='user supplied refrain, partial source conditioning',
        cover_strength=1.,cover_noise_strength=0.,reference_start=float(start),verify_lyrics=True,
        generation_seed=int(hashlib.sha256((str(start)+target['lyrics']).encode()).hexdigest()[:8],16))
    # Keep source and target music descriptions identical: edit words, not genre.
    target['prompt']=song['prompt']
    return target


def source_window(reference, start, seconds, directory):
    from pipeline import duration
    start=float(start);seconds=float(seconds)
    if not all(math.isfinite(x) for x in (start,seconds)) or start<0 or seconds<=0:
        raise ValueError('Invalid source audio window')
    if start+seconds>duration(reference)+.05:
        raise ValueError('Reference is shorter than requested source window; refusing audio looping')
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    identity=hashlib.sha256(Path(reference).read_bytes()+f'{start}:{seconds}'.encode()).hexdigest()[:16]
    target=directory/f'reference-window-{identity}.wav'
    if target.exists() and abs(duration(target)-seconds)<.05:
        return str(target)
    temporary=target.with_suffix('.part.wav')
    try:
        subprocess.run(['ffmpeg','-y','-v','error','-ss',str(start),'-i',str(reference),
            '-t',str(seconds),'-ar','48000','-ac','2',str(temporary)],check=True)
        if abs(duration(temporary)-seconds)>.05:
            raise ValueError('Source audio window duration mismatch')
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return str(target)
