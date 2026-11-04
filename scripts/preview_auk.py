"""One continuous 60-second vocal edit over the original full-length backing."""
import json
from pathlib import Path
import subprocess

ROOT = Path('output/auk-preview')
SOURCE = Path('assets/reference/auk-source-60s.mp3')


def run(*args):
    subprocess.run(list(map(str,args)),check=True)


def seconds(path):
    return float(subprocess.check_output(['ffprobe','-v','error','-show_entries',
        'format=duration','-of','default=noprint_wrappers=1:nokey=1',str(path)],text=True))


def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    if abs(seconds(SOURCE)-60) > .1:
        raise ValueError('Requires a genuine continuous 60-second source')
    run('python','-m','demucs','--two-stems=vocals','--device=cpu','--shifts=0',
        '-n','htdemucs','-o',ROOT/'stems',SOURCE)
    stems=ROOT/'stems/htdemucs'/SOURCE.stem
    vocals=stems/'vocals.wav';backing=stems/'no_vocals.wav'
    import whisper
    transcript=whisper.load_model('base',device='cpu').transcribe(str(vocals),fp16=False)
    original=transcript['text'].strip()
    if not original:
        raise ValueError('No source lyrics transcribed; cannot specify a lyric edit')
    (ROOT/'source-transcript.json').write_text(json.dumps(transcript,ensure_ascii=False,indent=2))
    lyrics='''रंग बिरंगी तितली आई
फूलों संग हम हँसते जाएं
दूदी दूदी दम दम दूदी दूदी दम
नीले बादल पानी लाएं
कागज़ की हम नाव चलाएं
दूदी दूदी दम दम दूदी दूदी दम'''
    instruction=(f'Change the verse lyrics in the vocal recording from "{original}" to '
        f'"{lyrics}". Keep the original opening hook in the first 19 seconds and the '
        'Dudi Dudi Dam Dam refrain unchanged. Preserve the singer voice, melody, '
        'rhythm, note timing, vocal expression and total duration. Fit the new Hindi '
        'verse words naturally to the original melody. Output isolated vocals only.')
    (ROOT/'request.json').write_text(json.dumps(dict(instruction=instruction,
        seconds=60,method='single full-length AuK vocal edit over continuous source backing',
        audio_section_splicing=False,experimental=True),ensure_ascii=False,indent=2))
    from auk.infer.infer_auk import AukInfer,save_audio
    import torch
    torch.set_num_threads(3)
    engine=AukInfer('.models/auk/config.yaml','.models/auk/auk_base.safetensors',
        device='cpu',qwen_path='.models/qwen')
    messages=[dict(role='user',content=[dict(type='text',text=instruction),
                                     dict(type='audio',audio=str(vocals))])]
    edited,sr=engine.generate(messages,gen_seconds=60,seed=20261104,nfe=32)
    target=ROOT/'auk-edited-vocals.wav';save_audio(edited,sr,str(target))
    if abs(seconds(target)-60) > .2:
        raise ValueError('Edited vocal duration mismatch; refusing to loop or stretch')
    run('ffmpeg','-y','-v','error','-i',backing,'-i',target,'-filter_complex',
        '[0:a][1:a]amix=inputs=2:duration=shortest:normalize=0,alimiter=limit=0.95',
        '-codec:a','libmp3lame','-b:a','192k',ROOT/'auk-reference-60s.mp3')
    (ROOT/'report.json').write_text(json.dumps(dict(seconds=seconds(ROOT/'auk-reference-60s.mp3'),
        model='AuK Base',generation_calls=1,audio_section_splicing=False,
        backing='original source separated instrumental',
        quality='Hindi lyrics, singer identity, hook preservation and alignment require listening review'),indent=2))


if __name__=='__main__':
    main()
