"""Check the rendered audio for replacement verse words, not just song.json."""
import json
from pathlib import Path
import unicodedata


def normalize(text):
    return unicodedata.normalize('NFC',text).replace('़','').lower()


def assess(source_text, rendered_text):
    source=normalize(source_text);rendered=normalize(rendered_text)
    groups=(('तितली','फूल'),('बादल','कागज','नाव'))
    hits=[[word for word in group if word in rendered and word not in source] for group in groups]
    return dict(replacement_verses_detected=all(hits),new_word_hits=hits,
                limitation='ASR lyric check; melody, rhythm and voice still require listening')


def main():
    import whisper
    root=Path('output/preview')
    source=json.loads((root/'source-transcript.json').read_text())
    result=whisper.load_model('base',device='cpu').transcribe(
        str(root/'dudi-continuous-60s.mp3'),language='hi',fp16=False)
    (root/'rendered-transcript.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    report=assess(source['text'],result['text'])
    (root/'lyrics-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False),flush=True)
    if not report['replacement_verses_detected']:
        raise SystemExit('Replacement verse words were not detected in both verses; preview needs review')


if __name__=='__main__':
    main()
