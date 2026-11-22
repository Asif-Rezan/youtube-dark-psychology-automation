"""Free Kokoro English narration and Faster-Whisper word alignment on cloud CPUs."""
import os
import subprocess
import numpy as np

_pipeline = None
_whisper = None
VOICE_RENDER_VERSION = 'deeper-documentary-v1'


def deepen_voice(path):
    """Lower pitch gently while keeping narration and captions in sync."""
    ratio = .94
    shifted = path.with_name(path.stem + '.shifted.wav')
    try:
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(path),
            '-af', f'asetrate={round(24000 * ratio)},aresample=24000,'
                   f'atempo={1 / ratio:.8f},highpass=f=65',
            '-ar', '24000', '-ac', '1', str(shifted)], check=True)
        shifted.replace(path)
    finally:
        shifted.unlink(missing_ok=True)


def generate(text, path):
    global _pipeline
    import soundfile as sf
    import torch
    torch.set_num_threads(2)
    if _pipeline is None:
        from kokoro import KPipeline
        _pipeline = KPipeline(lang_code='a', device='cpu', repo_id='hexgrad/Kokoro-82M')
    parts = [audio.numpy() for _, _, audio in _pipeline(text,
        voice=os.getenv('CPU_TTS_VOICE', 'am_michael'), speed=.9, split_pattern=r'\n+')]
    if not parts:
        raise RuntimeError('Kokoro returned no narration')
    sf.write(str(path), np.concatenate(parts), 24000)
    deepen_voice(path)


def transcribe_audio(path):
    global _whisper
    if _whisper is None:
        from faster_whisper import WhisperModel
        _whisper = WhisperModel('base.en', device='cpu', compute_type='int8', cpu_threads=2)
    import subprocess
    decoded = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(path),
        '-f', 'f32le', '-ac', '1', '-ar', '16000', 'pipe:1'],
        capture_output=True, check=True)
    audio = np.frombuffer(decoded.stdout, dtype='<f4').copy()
    segments, info = _whisper.transcribe(audio, language='en', word_timestamps=True,
        beam_size=3, vad_filter=False)
    words = [dict(word=w.word, start=w.start, end=w.end) for segment in segments for w in segment.words or []
        if w.end > w.start]
    if not words:
        raise RuntimeError('CPU transcription returned no aligned words')
    return words
