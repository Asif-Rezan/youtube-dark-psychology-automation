"""Trim natural audio edges, reject internal dropouts and master continuous mixes."""
import json
from pathlib import Path
import re
import subprocess

VERSION='continuous-kids-mix-v2'
BPM=120
LOUDNESS='loudnorm=I=-14:TP=-1.5:LRA=9'
MAX_EDGE_TRIM_RATIO=.10


class AudioGapError(RuntimeError):
    def __init__(self,message,code='internal_gap'):
        self.code=code
        super().__init__(message)


def uses_continuous_mix(song):
    return song.get('audio_mastering') in ('continuous-kids-mix-v1',VERSION)


def audio_duration(path):
    result=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration',
        '-of','json',str(path)],check=True,capture_output=True,text=True,timeout=60)
    return float(json.loads(result.stdout)['format']['duration'])


def verify_continuity(path,seconds,allow_edge_trim=True):
    native=audio_duration(path)
    if native<seconds-.1:
        raise AudioGapError(f'Audio is too short: {native:.3f}s for {seconds:.3f}s','too_short')
    end=min(native,float(seconds))
    result=subprocess.run(['ffmpeg','-hide_banner','-nostats','-i',str(path),'-t',str(end),
        '-af','silencedetect=noise=-45dB:d=0.10','-f','null','-'],
        check=True,capture_output=True,text=True,timeout=300)
    start=None
    gaps=[]
    for line in result.stderr.splitlines():
        found=re.search(r'silence_start: (-?[\d.]+)',line)
        if found:
            start=max(0.,float(found.group(1)))
        found=re.search(r'silence_end: ([\d.]+)',line)
        if found and start is not None:
            gaps.append((start,min(end,float(found.group(1)))))
            start=None
    if start is not None:
        gaps.append((start,end))
    leading=0.
    trailing=end
    internal=[]
    for a,b in gaps:
        if a<=.02:
            leading=max(leading,b)
        elif b>=end-.02:
            trailing=min(trailing,a)
        elif b-a>=.65:
            internal.append((a,b))
    if internal:
        raise AudioGapError('Unexpected internal music silence at '+','.join(f'{a:.2f}-{b:.2f}s' for a,b in internal))
    active=trailing-leading
    if active<=0 or active<float(seconds)*(1-MAX_EDGE_TRIM_RATIO):
        raise AudioGapError('Too much silent onset/outro to repair within the 10% duration budget','excessive_edge_silence')
    if not allow_edge_trim and (leading>.15 or end-trailing>.35):
        raise AudioGapError('Unrepaired onset/outro silence remains after mastering','unrepaired_edges')
    return dict(start=leading,end=trailing,active_seconds=active,
                source_seconds=native,edge_trim_seconds=end-active)


def master_parts(parts,target,seconds):
    """Trim edge silence, crossfade, and restore exact duration without padding."""
    if not parts or seconds<=0:
        raise ValueError('Mastering needs audio parts and a positive duration')
    target=Path(target)
    temporary=target.with_suffix('.master.tmp.wav')
    args=['ffmpeg','-y','-v','error']
    filters=[]
    windows=[]
    for i,part in enumerate(parts):
        native=audio_duration(part)
        window=verify_continuity(part,seconds if len(parts)==1 else native)
        windows.append(window)
        args+=['-i',str(part)]
        filters.append(f'[{i}:a]atrim=start={window["start"]:.9f}:end={window["end"]:.9f},asetpts=PTS-STARTPTS[part{i}]')
    previous='part0'
    for i in range(1,len(parts)):
        label=f'join{i}'
        filters.append(f'[{previous}][part{i}]acrossfade=d=0.08:c1=tri:c2=tri[{label}]')
        previous=label
    active_seconds=sum(w['active_seconds'] for w in windows)-.08*(len(parts)-1)
    ratio=active_seconds/seconds
    # The budget includes both edge trimming and crossfade compensation.
    if not .9<=ratio<=1.1:
        raise AudioGapError('Music needs excessive duration adjustment; regenerate the affected part','duration_budget')
    filters.append(f'[{previous}]atempo={ratio:.12f},{LOUDNESS},atrim=duration={seconds},asetpts=N/SR/TB[out]')
    try:
        subprocess.run(args+['-filter_complex',';'.join(filters),'-map','[out]',
            '-ar','44100','-ac','2','-c:a','pcm_s16le',str(temporary)],
            check=True,capture_output=True,timeout=600)
        if abs(audio_duration(temporary)-seconds)>.1:
            raise ValueError('Mastered music duration differs from the storyboard')
        verify_continuity(temporary,seconds,allow_edge_trim=False)
        temporary.replace(target)
        return dict(version=VERSION,seconds=seconds,tempo_compensation=ratio,windows=windows)
    finally:
        temporary.unlink(missing_ok=True)
