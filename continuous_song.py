"""Generate a source-conditioned full-song cover without audio splicing."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

from chorus_arrangement import REFRAIN


def continuous_request(verses, identity):
    if len(verses) != 2 or len(set(verses)) != 2 or any(not v.strip() or REFRAIN in v for v in verses):
        raise ValueError('Two distinct new verse blocks required')
    return dict(
        _segment=True, duration=60, vocal_language='hi',
        reference_cover=True, cover_strength=1.0, cover_noise_strength=0.85,
        generation_seed=int(hashlib.sha256((identity+'\n'.join(verses)).encode()).hexdigest()[:8],16),
        lyrics='\n'.join(['[Intro]', '[Verse]', verses[0], '[Chorus]', REFRAIN, REFRAIN,
                          '[Verse]', verses[1], '[Chorus]', REFRAIN, REFRAIN, '[Outro]']),
        prompt='Replace the source verse words with the supplied Hindi lyrics; do not '
               'sing the original verse words. Keep only the opening hook and Dudi refrain '
               'from the source. Fit every supplied verse line to the existing musical phrases. '
               'Cover the supplied source song with the new Hindi lyrics. Preserve its '
               'rhythm, chord progression, melody, bass line, drums, instrumentation, '
               'singer timbre, vocal register, phrasing and mix. '
               'One continuous Hindi nursery performance. '
               'Use the reference singer character, playful instrumentation, groove and tonal mood. '
               'An opening musical hook appears only once at the beginning, approximately the first '
               '19 seconds; then sing the supplied new verses with the Dudi refrain between verses '
               'and near the ending. Keep one consistent singer, accompaniment, tempo, key and mix '
               'throughout. Fit the Hindi syllables naturally into coherent musical phrases. '
               'Smooth musical transitions, no restarts or repeated opening hook. '
               'Compose and perform the entire 60-second song as one uninterrupted performance.')


def render_continuous(verses, identity, root):
    from music_cpu import synthesize, reference_audio
    from pipeline import duration
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    song=continuous_request(verses,identity)
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
        seconds=duration(target),method='single source-conditioned full-song cover',
        generation_calls=1,audio_splicing=False,
        quality='Hook timing, refrain similarity and musical continuity require listening review'),indent=2))
    return target
