"""Verify generated verse words; keep runtime errors separate from unverified singing."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import unicodedata


class LyricsQualityError(RuntimeError):
    code='lyrics_unverified'


def tokens(text):
    text=unicodedata.normalize('NFC',text).replace('़','').lower()
    return set(re.findall(r'[a-z]+|[\u0900-\u097f]+',text))


def assess(song, transcript):
    refrain=tokens('dudi dudi dam dam दूदी दूडी दुदी डूडी दम डम')
    lines=[tokens(line)-refrain for line in song['lyrics'].splitlines()]
    lines=[line for line in lines if len(line)>=2 and not line & {'intro','verse','chorus','outro'}]
    if not lines:
        raise ValueError('No verse words available for lyric verification')
    heard=tokens(transcript)-refrain
    matches=[len(line & heard)>=min(2,len(line)) for line in lines]
    expected=set().union(*lines)
    coverage=len(expected & heard)/len(expected)
    mid=max(1,len(lines)//2)
    both_halves=any(matches[:mid]) and (any(matches[mid:]) if len(lines)>1 else True)
    passed=coverage>=.35 and sum(matches)>=math.ceil(len(lines)*.5) and both_halves
    return dict(status='passed' if passed else 'needs_review',word_coverage=round(coverage,4),
        matched_lines=sum(matches),verse_lines=len(lines),both_halves_detected=both_halves,
        limitation='ASR estimate only; musical similarity and singer identity require listening')


def identity(song,audio):
    return dict(audio_sha256=hashlib.sha256(Path(audio).read_bytes()).hexdigest(),
                lyrics_sha256=hashlib.sha256(song['lyrics'].encode()).hexdigest())


def write_report(report,path):
    Path(path).write_text(json.dumps(report,ensure_ascii=False,indent=2))
    summary=os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary,'a') as stream:
            stream.write('\n### Music lyric verification\n\nStatus: **'+report['status']+'**. '
                +'Audio is retained. Unverified lyrics block publication.\n')


def validate_segment(song,audio,state,save):
    if not song.get('verify_lyrics'):
        return
    audio=Path(audio);report_path=audio.with_suffix('.lyrics-quality.json')
    ids=identity(song,audio)
    if report_path.exists():
        previous=json.loads(report_path.read_text())
        if previous.get('status')=='passed' and all(previous.get(k)==v for k,v in ids.items()):
            state['lyrics_quality']=previous;save();return
    request_path=audio.with_suffix('.lyrics-input.json')
    request_path.write_text(json.dumps(song,ensure_ascii=False))
    from worker_limits import run_worker,WorkerFailure
    try:
        run_worker([sys.executable,'-u',str(Path(__file__).resolve()),'--song',str(request_path.resolve()),
            '--audio',str(audio.resolve()),'--report',str(report_path.resolve())],timeout=1800,
            diagnostic=audio.with_suffix('.lyrics-resources.txt'))
    except (WorkerFailure,subprocess.CalledProcessError,subprocess.TimeoutExpired,OSError):
        report=json.loads(report_path.read_text()) if report_path.exists() else dict(status='runtime_error')
        state.update(lyrics_quality=report,audio_ready=False,generation_started=False)
        save()
        if report.get('status')=='needs_review':
            raise LyricsQualityError('Audio generated but replacement verse lyrics were not verified; publication blocked. See '+str(report_path)) from None
        raise
    report=json.loads(report_path.read_text())
    if report.get('status')!='passed' or any(report.get(k)!=v for k,v in ids.items()):
        raise LyricsQualityError('Lyric verifier did not return a matching passed report')
    state['lyrics_quality']=report;save()


def verify(song,audio,report_path):
    try:
        import whisper
        transcript=whisper.load_model('small',device='cpu').transcribe(str(audio),language=song.get('vocal_language','hi'),
            fp16=False,temperature=0,beam_size=5,condition_on_previous_text=False)
        report=dict(assess(song,transcript['text']),**identity(song,audio),transcript=transcript['text'])
    except Exception as error:
        write_report(dict(status='runtime_error',error_type=type(error).__name__,error=str(error)),report_path)
        raise
    write_report(report,report_path)
    if report['status']!='passed':
        print('::error title=Lyrics unverified::Audio was generated but verse lyrics were not verified. Publication is blocked; audio and transcript retained.')
        raise SystemExit(2)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for arg in ('song','audio','report'):
        parser.add_argument('--'+arg,required=True)
    args=parser.parse_args()
    verify(json.loads(Path(args.song).read_text()),Path(args.audio),Path(args.report))
