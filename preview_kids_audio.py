"""Audio-only listening candidates; no storage, images or publishing calls."""
import argparse
import json
import os
from pathlib import Path
import subprocess

REFRAIN = 'दूदी दूदी दम दम'


def preview_song(style):
    if style not in ('dance', 'singalong'):
        raise ValueError('Unknown kids preview style')
    bpm = 116 if style == 'dance' else 108
    arrangement = ('Bouncy toy piano and marimba, ukulele offbeats, light handclaps, playful bells, a simple dancing beat.'
                   if style == 'dance' else
                   'Gentle acoustic ukulele, bright glockenspiel, soft handclaps, a simple swaying beat.')
    return dict(_segment=True, vocal_language='hi', vocal_gender='female', duration=30,
        bpm=bpm, generation_seed=20261104 if style == 'dance' else 20261105,
        prompt=f'Hindi preschool sing-along nursery rhyme, {bpm} BPM, C major, cheerful major-key melody. '
            'One bright, warm, sweet female lead singer with a smiling playful delivery, clear natural Hindi pronunciation, '
            'short easy phrases, clean sustained vowels and gentle expressive pitch movement. '
            'Catchy repeated four-note chorus that toddlers can copy. Lead vocal close and clearly above a light backing. '
            +arrangement+' Start singing immediately, steady music, happy little ending.',
        lyrics='\n'.join(['[Chorus]', REFRAIN, 'आओ नाचें छम छम',
            '[Verse]', 'ताली बजाओ, ताली बजाओ', 'हँसते गाते, घूमो घूमो',
            '[Chorus]', REFRAIN, 'आओ नाचें छम छम', REFRAIN]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--style', choices=['dance', 'singalong'], required=True)
    args = parser.parse_args()
    from music_cpu import synthesize
    root = Path('output/preview')
    root.mkdir(parents=True, exist_ok=True)
    song = preview_song(args.style)
    (root/'song.json').write_text(json.dumps(song, ensure_ascii=False, indent=2))
    wav = root/f'hindi-kids-v2-{args.style}.wav'
    synthesize(song, wav, Path(os.environ['ACESTEP_SOURCE_DIR']), Path(os.environ['ACESTEP_CHECKPOINTS_DIR']))
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', str(wav),
        '-af', 'loudnorm=I=-16:TP=-1.5:LRA=9', '-codec:a', 'libmp3lame', '-b:a', '192k',
        str(wav.with_suffix('.mp3'))], check=True)


if __name__ == '__main__':
    main()
