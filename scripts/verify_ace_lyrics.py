"""Check the rendered audio for replacement verse words, not just song.json."""
import json
import os
from pathlib import Path
import unicodedata


def normalize(text):
    return unicodedata.normalize('NFC',text).replace('़','').lower()


def assess(source_text, rendered_text):
    source=normalize(source_text);rendered=normalize(rendered_text)
    groups=(('तितली','फूल'),('बादल','कागज','नाव'))
    hits=[[word for word in group if word in rendered and word not in source] for group in groups]
    return dict(status='passed' if all(hits) else 'needs_review',
                replacement_verses_detected=all(hits),new_word_hits=hits,
                limitation='ASR lyric check; melody, rhythm and voice still require listening')


def write_report(root, report):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    (root/'lyrics-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False),flush=True)
    summary=os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        message={
            'passed':'Audio generated. Replacement words detected in both verses; listening review remains required.',
            'needs_review':'Audio generated, but replacement words were not detected in both verses. Lyrics are unverified; this is a quality-gate failure, not a generation crash.',
            'runtime_error':'Lyric verification could not run because of a runtime error. See traceback.'
        }[report['status']]
        with open(summary,'a') as stream:
            stream.write('\n### ACE preview verification\n\n'+message+'\n')


def main(root=Path('output/preview')):
    root=Path(root)
    try:
        import whisper
        source=json.loads((root/'source-transcript.json').read_text())
        if not (root/'dudi-continuous-60s.mp3').is_file():
            raise FileNotFoundError('Generated preview audio missing')
        result=whisper.load_model('small',device='cpu').transcribe(
            str(root/'dudi-continuous-60s.mp3'),language='hi',fp16=False,temperature=0,
            beam_size=5,condition_on_previous_text=False)
        (root/'rendered-transcript.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
        report=assess(source['text'],result['text'])
    except Exception as error:
        write_report(root,dict(status='runtime_error',error_type=type(error).__name__,error=str(error)))
        raise
    write_report(root,report)
    if report['status']=='needs_review':
        print('::error title=Lyrics need review::Audio was generated, but replacement lyrics were not verified. Inspect the saved audio and transcripts.')
        raise SystemExit(2)


if __name__=='__main__':
    main()
