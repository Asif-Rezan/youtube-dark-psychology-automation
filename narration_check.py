"""Exercise the real English tokenizer and Kokoro voice without API credentials."""
import json
from pathlib import Path
import tempfile


def main():
    import numpy as np
    import soundfile as sf
    import spacy
    from voice_cpu import generate

    nlp = spacy.load('en_core_web_sm')
    assert len(nlp('Ancient builders shaped stone into enduring monuments.')) > 0
    with tempfile.TemporaryDirectory(prefix='narration-check-') as directory:
        path = Path(directory) / 'narration.wav'
        generate('Ancient builders shaped stone into enduring monuments.', path)
        audio, rate = sf.read(path)
        duration = len(audio) / rate
        if rate != 24000 or duration < 1 or not np.isfinite(audio).all() or np.max(np.abs(audio)) < .001:
            raise RuntimeError('Narration check produced invalid or silent audio')
        print(json.dumps({'check': 'Real Kokoro narration', 'passed': True,
                          'sample_rate': rate, 'seconds': round(duration, 2),
                          'spacy_version': spacy.__version__}))


if __name__ == '__main__':
    main()
