"""Audio-only listening candidates; no storage, images or publishing calls."""
import argparse
import json
import os
from pathlib import Path
import subprocess

REFRAIN = 'दूदी दूदी दम दम दूदी दूदी दम'
STYLES = ('cover-balanced', 'cover-close', 'chorus-close', 'chorus-strict')


def preview_song(style):
    if style not in STYLES:
        raise ValueError('Unknown cover preview style')
    chorus_match = style.startswith('chorus-')
    song = dict(_segment=True, vocal_language='hi', vocal_gender='female', duration=30,
        bpm=123, generation_seed=20261107, reference_cover=True,
        cover_strength=0.75 if style == 'cover-balanced' else 1.0,
        cover_noise_strength={'chorus-close': 0.85, 'chorus-strict': 0.95}.get(style, 0.2),
        prompt='Hindi nursery rhyme cover of the source audio. Preserve the source song melody, '
            'recognizable hook melody, drum groove, bass rhythm, instruments, arrangement and 123 BPM tempo, D major. '
            'A single sweet clear female singer performs the new Hindi lyrics naturally to the source melody. '
            'Playful smiling expression, clear Hindi syllables, one coherent clean vocal and backing arrangement.',
        lyrics='\n'.join(['[Chorus]', 'दूदी दूदी दम दम दूदी दूदी दम',
            'आओ मिलकर नाचें हम, आओ नाचें हम',
            '[Verse]', 'नन्हे मुन्ने ताली बजाएं', 'प्यारे पंछी गीत सुनाएं',
            '[Chorus]', 'दूदी दूदी दम दम दूदी दूदी दम',
            'हँसते गाते झूमें हम, झूमें सारे हम']))
    if chorus_match:
        song['prompt'] = (
            'Preserve the source instrumental intro, melody, groove, arrangement and tempo. '
            'The Dudi chorus follows the source hook pitch contour, rhythm, note lengths, '
            'syllable stress and phrase endings, repeated identically twice. '
            'Do not compose a different chorus melody. Single clear sweet female vocal, '
            'Hindi pronunciation, continuous playful nursery backing, 123 BPM, D major.'
        )
        song['lyrics'] = '\n'.join([
            '[Intro]', '[Chorus]', REFRAIN, REFRAIN,
            '[Verse]', 'नन्हे मुन्ने ताली बजाएं', 'प्यारे पंछी गीत सुनाएं',
            '[Chorus]', REFRAIN, REFRAIN])
    return song



def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--style', choices=STYLES, required=True)
    args = parser.parse_args()
    from music_cpu import synthesize
    root = Path('output/preview')
    root.mkdir(parents=True, exist_ok=True)
    song = preview_song(args.style)
    (root/'song.json').write_text(json.dumps(song, ensure_ascii=False, indent=2))
    wav = root/f'hindi-reference-{args.style}.wav'
    synthesize(song, wav, Path(os.environ['ACESTEP_SOURCE_DIR']), Path(os.environ['ACESTEP_CHECKPOINTS_DIR']))
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', str(wav),
        '-af', 'loudnorm=I=-16:TP=-1.5:LRA=9', '-codec:a', 'libmp3lame', '-b:a', '192k',
        str(wav.with_suffix('.mp3'))], check=True)


if __name__ == '__main__':
    main()
