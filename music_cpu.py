"""Render MusicRNN notes as a restrained historical-exploration score."""
import json
import math
from pathlib import Path
import subprocess
import wave
import numpy as np


RATE = 24000
STEP = 60 / 88 / 4
# D Dorian keeps the mystery while its natural sixth leaves room for wonder.
SCALE = (55, 57, 59, 60, 62, 64, 65, 67, 69, 71, 72, 74, 76, 77, 79)
CHORDS = ((62, 65, 69, 76),  # D minor add9
          (60, 64, 67, 71),  # C major 7
          (55, 59, 62, 69),  # G add9
          (60, 64, 67, 74))  # C add9


def render_sequence(sequence, path):
    seconds = float(sequence['totalQuantizedSteps']) * STEP + 3
    if not 20 <= seconds <= 180 or not sequence.get('notes'):
        raise ValueError('Generated score has no usable notes or duration')
    audio = np.zeros((math.ceil(seconds * RATE), 2), dtype=np.float32)
    # Mid-range string chords rise and change rather than sitting on a heavy
    # bass drone. Each new chord suggests another room or vista opening up.
    total_steps = int(sequence['totalQuantizedSteps'])
    for chord_index, start_step in enumerate(range(0, total_steps, 64)):
        start = int(start_step * STEP * RATE)
        count = min(int(64 * STEP * RATE), len(audio) - start)
        ct = np.arange(count, dtype=np.float32) / RATE
        attack = np.minimum(ct / 1.5, 1)
        release = np.minimum((count / RATE - ct) / 1.5, 1)
        envelope = attack * release * (.85 + .15 * np.sin(2 * np.pi * .07 * ct))
        for voice, pitch in enumerate(CHORDS[chord_index % len(CHORDS)]):
            hz = 440 * 2 ** ((pitch - 69) / 12)
            string = (np.sin(2 * np.pi * hz * ct) +
                      .16 * np.sin(2 * np.pi * hz * 1.006 * ct) +
                      .10 * np.sin(2 * np.pi * hz * 2 * ct))
            pan = .35 + .1 * voice
            signal = string * envelope * .014
            audio[start:start+count, 0] += signal * (1-pan)
            audio[start:start+count, 1] += signal * pan
    for index, note in enumerate(sequence['notes']):
        start = int(int(note['quantizedStartStep']) * STEP * RATE)
        if start < 0 or start >= len(audio):
            continue
        length = max(.35, (int(note['quantizedEndStep']) - int(note['quantizedStartStep'])) * STEP)
        count = min(int((length + 2.5) * RATE), len(audio) - start)
        nt = np.arange(count, dtype=np.float32) / RATE
        pitch = min(SCALE, key=lambda value: abs(value - int(note['pitch'])))
        hz = 440 * 2 ** ((pitch - 69) / 12)
        # A lightly bowed/plucked motif moves above the chords without a piano attack.
        envelope = np.minimum(nt / .13, 1) * np.exp(-nt / 2.2)
        envelope *= np.exp(-np.maximum(nt - length, 0) * 1.4)
        tone = (np.sin(2 * np.pi * hz * nt) +
                .20 * np.sin(2 * np.pi * hz * 2 * nt) +
                .06 * np.sin(2 * np.pi * hz * 3 * nt))
        pan = .43 + .14 * (index % 3) / 2
        signal = tone * envelope * .052
        audio[start:start+count, 0] += signal * (1-pan)
        audio[start:start+count, 1] += signal * pan
    # A very quiet upper-register glint gives the scene discovery and air.
    for index, start_step in enumerate(range(0, total_steps, 32)):
        start = int(start_step * STEP * RATE)
        count = min(int(3 * RATE), len(audio) - start)
        if count <= 0:
            continue
        st = np.arange(count, dtype=np.float32) / RATE
        hz = 440 * 2 ** (([74, 76, 79, 76][index % 4] - 69) / 12)
        glint = .008 * np.sin(2 * np.pi * hz * st) * np.minimum(st / .08, 1) * np.exp(-st / 1.5)
        audio[start:start+count, 0] += glint * .4
        audio[start:start+count, 1] += glint * .6
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
