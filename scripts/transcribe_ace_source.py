"""ASR source lyrics, with an explicit hash-bound partial lyric fallback."""
import hashlib
import json
import os
from pathlib import Path


def resolve_transcript(result, reference, fallback):
    if result.get('text','').strip():
        return dict(result,provenance='whisper-base',partial_lyrics=False)
    digest=hashlib.sha256(Path(reference).read_bytes()).hexdigest()
    if fallback.get('source_sha256') != digest or not fallback.get('known_lyrics','').strip():
        raise ValueError('No source lyrics detected and no matching supplied lyric reference')
    return dict(text=fallback['known_lyrics'],segments=[],provenance='user-supplied refrain',
                partial_lyrics=True,scope='Known refrain only; not a full source transcript')


def main():
    import whisper
    reference=Path(os.environ['REFERENCE_AUDIO_PATH'])
    target=Path(os.environ['ACE_SOURCE_TRANSCRIPT'])
    target.parent.mkdir(parents=True,exist_ok=True)
    result=whisper.load_model('base',device='cpu').transcribe(str(reference),language='hi',fp16=False)
    fallback=json.loads(Path('assets/reference/ace-source-lyrics.json').read_text())
    transcript=resolve_transcript(result,reference,fallback)
    target.write_text(json.dumps(transcript,ensure_ascii=False,indent=2))
    print(json.dumps({k:transcript[k] for k in ['provenance','partial_lyrics']},ensure_ascii=False))


if __name__=='__main__':
    main()
