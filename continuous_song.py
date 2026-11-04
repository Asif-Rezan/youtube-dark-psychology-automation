"""Generate a source-conditioned full-song cover without audio splicing."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

from chorus_arrangement import REFRAIN


def continuous_request(verses, identity, source_lyrics, opening_lyrics=""):
    if not source_lyrics.strip():
        raise ValueError("Original source lyrics are required for flow-edit")
    if len(verses) != 2 or len(set(verses)) != 2 or any(not v.strip() or REFRAIN in v for v in verses):
        raise ValueError('Two distinct new verse blocks required')
    return dict(
        _segment=True, duration=60, vocal_language='hi',
        reference_cover=True, cover_strength=1.0, cover_noise_strength=0.0,
        flow_edit_morph=True, source_lyrics=source_lyrics,
        generation_seed=int(hashlib.sha256((identity+'\n'.join(verses)).encode()).hexdigest()[:8],16),
        lyrics='\n'.join(['[Intro]', opening_lyrics, '[Verse]', verses[0], '[Chorus]', REFRAIN, REFRAIN,
                          '[Verse]', verses[1], '[Chorus]', REFRAIN, REFRAIN, '[Outro]']),
        prompt='Hindi kids nursery dance song, playful bright synth melody, bouncy bass, '
               'steady percussion, cheerful clear high-register lead vocal. Consistent '
               'singer timbre, melody, rhythm, chord progression, instrumentation and mix.')



def render_continuous(verses, identity, root):
    from music_cpu import synthesize, reference_audio
    from pipeline import duration
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    transcript=json.loads(Path(os.environ['ACE_SOURCE_TRANSCRIPT']).read_text())
    source_lyrics=transcript['text'].strip()
    opening='\n'.join(s['text'].strip() for s in transcript.get('segments', []) if s['start'] < 19)
    song=continuous_request(verses,identity,source_lyrics,opening)
    reference_seconds=duration(reference_audio())
    if reference_seconds < song['duration'] - .05:
        raise ValueError(
            f'Source-matched {song["duration"]}s cover requires a source at least that long; '
            f'current reference is {reference_seconds:.2f}s. No looping, splicing or style-only fallback.')
    (root/'song.json').write_text(json.dumps(song,ensure_ascii=False,indent=2))
    target=root/'dudi-continuous-60s.wav'
    synthesize(song,target,Path(os.environ['ACESTEP_SOURCE_DIR']),Path(os.environ['ACESTEP_CHECKPOINTS_DIR']))
    # Encode the entire generated performance. Never insert reference samples or join sections.
    subprocess.run(['ffmpeg','-y','-v','error','-i',str(target),'-codec:a','libmp3lame',
                    '-b:a','192k',str(target.with_suffix('.mp3'))],check=True)
    (root/'arrangement-report.json').write_text(json.dumps(dict(
        seconds=duration(target),method='single source-conditioned flow lyric edit',
        generation_calls=1,audio_splicing=False,
        quality='Hook timing, refrain similarity and musical continuity require listening review'),indent=2))
    return target
