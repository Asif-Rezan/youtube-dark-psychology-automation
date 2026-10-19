"""Checks for the documentary score and timing-preserving deeper narration."""
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np
import soundfile as sf

from music_cpu import RATE, render_sequence
from voice_cpu import deepen_voice


class AudioDesignTests(unittest.TestCase):
    def test_exploration_score_is_stereo_audible_and_bounded(self):
        sequence = {'totalQuantizedSteps': 100, 'notes': [
            {'pitch': 62, 'quantizedStartStep': 0, 'quantizedEndStep': 4},
            {'pitch': 68, 'quantizedStartStep': 16, 'quantizedEndStep': 20}]}
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / 'score.wav'
            seconds = render_sequence(sequence, target)
            with wave.open(str(target)) as audio:
                self.assertEqual(audio.getnchannels(), 2)
                self.assertEqual(audio.getframerate(), RATE)
                self.assertAlmostEqual(audio.getnframes() / RATE, seconds, delta=.01)
            samples, _ = sf.read(target)
            self.assertGreater(np.sqrt(np.mean(samples**2)), .005)
            self.assertLess(np.max(np.abs(samples)), .5)
            # The previous low drone dominated the preview; this score should
            # keep its energy in the lighter mid range.
            spectrum = abs(np.fft.rfft(samples[:, 0])) ** 2
            frequencies = np.fft.rfftfreq(len(samples), 1/RATE)
            self.assertLess(spectrum[frequencies < 100].sum() /
                            spectrum[(frequencies >= 100) & (frequencies < 1200)].sum(), .05)

    def test_deeper_voice_preserves_duration(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / 'voice.wav'
            rate = 24000
            t = np.arange(rate * 2) / rate
            sf.write(target, .2 * np.sin(2 * np.pi * 180 * t), rate)
            deepen_voice(target)
            samples, actual_rate = sf.read(target)
            self.assertEqual(actual_rate, rate)
            self.assertAlmostEqual(len(samples) / rate, 2, delta=.03)
            spectrum = abs(np.fft.rfft(samples[int(.3*rate):int(1.7*rate)]))
            frequencies = np.fft.rfftfreq(int(1.4*rate), 1/rate)
            self.assertAlmostEqual(frequencies[np.argmax(spectrum)], 180*.94, delta=3)


if __name__ == '__main__':
    unittest.main()
