"""Render MusicRNN notes as a restrained historical-exploration score."""
import json
import math
from pathlib import Path
import subprocess
import wave
import numpy as np


RATE = 24000
STEP = 60 / 76 / 4
# D minor pentatonic avoids busy chromatic turns beneath spoken history.
SCALE = (50, 53, 55, 57, 60, 62, 65, 67, 69, 72)


def render_sequence(sequence, path):
    seconds = float(sequence['totalQuantizedSteps']) * STEP + 3
    if not 20 <= seconds <= 180 or not sequence.get('notes'):
        raise ValueError('Generated score has no usable notes or duration')
    audio = np.zeros((math.ceil(seconds * RATE), 2), dtype=np.float32)
    # Slowly moving low strings create a sense of distance without copying a
    # region-specific musical tradition or overpowering the historical story.
    t = np.arange(len(audio), dtype=np.float32) / RATE
    swell = .7 + .3 * np.sin(2 * np.pi * .045 * t) ** 2
    drone = (.038 * np.sin(2 * np.pi * 73.416 * t) +
             .019 * np.sin(2 * np.pi * 110 * t) +
             .010 * np.sin(2 * np.pi * 146.832 * t)) * swell
    audio[:, 0] += drone * .92
    audio[:, 1] += drone
    for index, note in enumerate(sequence['notes']):
        start = int(int(note['quantizedStartStep']) * STEP * RATE)
        if start < 0 or start >= len(audio):
            continue
        length = max(.35, (int(note['quantizedEndStep']) - int(note['quantizedStartStep'])) * STEP)
        count = min(int((length + 2.5) * RATE), len(audio) - start)
        nt = np.arange(count, dtype=np.float32) / RATE
        pitch = min(SCALE, key=lambda value: abs(value - int(note['pitch'])))
        hz = 440 * 2 ** ((pitch - 69) / 12)
        # Warm plucked strings: quick attack, long soft decay, little high end.
        envelope = np.minimum(nt / .035, 1) * np.exp(-nt / 1.8)
        envelope *= np.exp(-np.maximum(nt - length, 0) * 1.4)
        tone = (np.sin(2 * np.pi * hz * nt) +
                .20 * np.sin(2 * np.pi * hz * 2 * nt) +
                .06 * np.sin(2 * np.pi * hz * 3 * nt))
        pan = .43 + .14 * (index % 3) / 2
        signal = tone * envelope * .065
        audio[start:start+count, 0] += signal * (1-pan)
        audio[start:start+count, 1] += signal * pan
    # A sparse, soft low pulse suggests forward movement through a place.
    for start_step in range(0, int(sequence['totalQuantizedSteps']), 16):
        start = int(start_step * STEP * RATE)
        count = min(int(.42 * RATE), len(audio) - start)
        if count <= 0:
            continue
        pt = np.arange(count, dtype=np.float32) / RATE
        pulse = .028 * np.sin(2 * np.pi * (64 - 18 * pt) * pt) * np.exp(-pt * 12)
        audio[start:start+count] += pulse[:, None]
    # A short stereo reflection adds space without turning the bed into a wash.
    for delay, gain in ((.37, .15), (.73, .08)):
        shift = int(delay * RATE)
        audio[shift:] += audio[:-shift, ::-1].copy() * gain
    fade = min(RATE, len(audio)//2)
    audio[:fade] *= np.linspace(0, 1, fade)[:, None]
    audio[-fade:] *= np.linspace(1, 0, fade)[:, None]
    peak = float(np.max(np.abs(audio)))
    if not np.isfinite(audio).all() or peak < .001:
        raise RuntimeError('Generated music is silent or invalid')
    audio *= .45 / peak
    with wave.open(str(path), 'wb') as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes((audio * 32767).astype('<i2').tobytes())
    return seconds


def generate(path):
    notes_path = path.with_suffix('.notes.json')
    subprocess.run(['node', str(Path(__file__).with_name('music_rnn.cjs')), str(notes_path)], check=True)
    sequence = json.loads(notes_path.read_text())
    seconds = render_sequence(sequence, path)
    print(json.dumps({'check': 'Generated music audio', 'passed': True, 'duration_seconds': round(seconds, 2)}), flush=True)


if __name__ == '__main__':
    import sys
    generate(Path(sys.argv[1]))
