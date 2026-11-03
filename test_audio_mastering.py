import json
from pathlib import Path
import shutil
import tempfile
import types
import unittest
from unittest.mock import Mock,MagicMock,patch
import wave
import numpy as np
from audio_mastering import master_parts,verify_continuity,AudioGapError


def tone(path,seconds=4,amplitude=.02,gap=False):
    rate=44100
    t=np.arange(round(seconds*rate))/rate
    data=amplitude*np.sin(2*np.pi*440*t)
    if gap:
        data[(t>=1.5)&(t<2.5)]=0
    pcm=(data*32767).astype('<i2')
    with wave.open(str(path),'wb') as out:
        out.setnchannels(1);out.setsampwidth(2);out.setframerate(rate);out.writeframes(pcm.tobytes())


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg runtime required')
class ActualAudioTests(unittest.TestCase):
    def test_crossfade_mix_is_louder_unclipped_and_keeps_storyboard_duration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for i in range(2):tone(root/f'{i}.wav')
            master_parts([root/'0.wav',root/'1.wav'],root/'song.wav',8)
            with wave.open(str(root/'song.wav'),'rb') as audio:
                self.assertEqual(audio.getnchannels(),2)
                self.assertAlmostEqual(audio.getnframes()/audio.getframerate(),8,delta=.1)
                data=np.frombuffer(audio.readframes(audio.getnframes()),dtype='<i2').astype(float)/32768
            self.assertGreater(np.sqrt(np.mean(data**2)),.02*3)
            self.assertLessEqual(np.max(np.abs(data)),.85)
            verify_continuity(root/'song.wav',8)

    def test_silence_gap_is_rejected_and_cannot_replace_good_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            tone(root/'bad.wav',gap=True)
            with self.assertRaises(AudioGapError):verify_continuity(root/'bad.wav',4)
            (root/'song.wav').write_bytes(b'existing-good-master')
            with self.assertRaises(AudioGapError):master_parts([root/'bad.wav'],root/'song.wav',4)
            self.assertEqual((root/'song.wav').read_bytes(),b'existing-good-master')
            self.assertFalse((root/'song.master.tmp.wav').exists())


class MusicTempoTests(unittest.TestCase):
    def test_model_gets_native_tempo_without_speeding_up_the_voice_file(self):
        import music_cpu as music
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'native.wav';source.write_bytes(b'generated')
            torch=MagicMock();handler=Mock(device='cpu')
            handler.initialize_service.return_value=('ready',True)
            params=Mock();config=Mock()
            infer=Mock(return_value=types.SimpleNamespace(success=True,audios=[{'path':str(source)}]))
            song=dict(_segment=True,prompt='Sweet female voice, 120 BPM',lyrics='Happy friends sing',duration=120,bpm=120)
            with patch.object(music,'checkpoints'),patch.object(music,'runtime',return_value=(torch,Mock(return_value=handler),params,config,infer)),patch.object(music,'reference_audio',return_value='reference.mp3'),patch('pipeline.duration',return_value=120):
                music.synthesize(song,root/'part.wav',root/'source',root/'models')
            self.assertEqual(params.call_args.kwargs['bpm'],120)
            self.assertEqual(params.call_args.kwargs['duration'],120)

    def test_motion_uses_the_requested_faster_beat_but_old_scenes_keep_old_tempo(self):
        from scene_actions import plan_scene
        self.assertEqual(plan_scene('animals dancing at 120 BPM')['beat_seconds'],.5)
        self.assertEqual(plan_scene('animals dancing')['beat_seconds'],.6)


class MusicGapRetryTests(unittest.TestCase):
    def test_only_the_gapped_part_is_regenerated_and_valid_parts_are_kept(self):
        import test_kids_rhymes
        import kids_rhymes
        from audio_mastering import VERSION
        fixture=test_kids_rhymes.KidsTests();fixture.setUp()
        try:
            song=fixture.song(600)
        finally:
            fixture.doCleanups()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);target=root/'song.wav';state={}
            def generate(request,path,part_state,save):
                path.write_bytes(b'part')
            def normalize(args,**kwargs):
                shutil.copyfile(args[args.index('-i')+1],args[-1])
            def master(parts,path,seconds):path.write_bytes(b'final mix')
            with patch('music_cpu.generate_segment',side_effect=generate) as model,patch('audio_mastering.verify_continuity',side_effect=[AudioGapError('gap'),None,None,None,None,None]),patch('audio_mastering.master_parts',side_effect=master),patch('pipeline.duration',return_value=120),patch('kids_rhymes.subprocess.run',side_effect=normalize):
                kids_rhymes.generate_music(song,target,state,Mock())
            self.assertEqual(model.call_count,6)
            self.assertEqual(model.call_args_list[0].args[1],model.call_args_list[1].args[1])
            self.assertEqual(state['parts']['0']['continuity_retries'],1)
            self.assertEqual(state['mastering_version'],VERSION)
            self.assertEqual(target.read_bytes(),b'final mix')
            self.assertTrue((root/'part-000.rejected-gap.wav').exists())


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg runtime required')
class BoundaryRepairTests(unittest.TestCase):
    def make_audio(self,path,leading=0,trailing=0,internal=False):
        rate=44100
        t=np.arange(40*rate)/rate
        signal=.03*np.sin(2*np.pi*440*t)
        signal[(t<leading)|(t>40-trailing)]=0
        if internal:signal[(t>=15.466083)&(t<16.857417)]=0
        with wave.open(str(path),'wb') as audio:
            audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(rate)
            audio.writeframes((signal*32767).astype('<i2').tobytes())

    def test_original_failure_edge_pattern_is_repaired_without_silent_padding(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            self.make_audio(root/'source.wav',1.294708,1.865729)
            result=master_parts([root/'source.wav'],root/'fixed.wav',40)
            self.assertAlmostEqual(result['tempo_compensation'],.92099,delta=.002)
            window=verify_continuity(root/'fixed.wav',40,allow_edge_trim=False)
            self.assertLess(window['edge_trim_seconds'],.1)

    def test_true_internal_dropout_and_excessive_outro_remain_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            self.make_audio(root/'internal.wav',1.29,1.86,True)
            self.make_audio(root/'tail.wav',0,4.587896)
            for name,code in [('internal','internal_gap'),('tail','excessive_edge_silence')]:
                with self.assertRaises(AudioGapError) as caught:
                    verify_continuity(root/f'{name}.wav',40)
                self.assertEqual(caught.exception.code,code)

    def test_failed_short_keeps_diagnostics_then_recovers_saved_native_without_inference(self):
        import short_music,test_short_music
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'output/test';root.mkdir(parents=True)
            song=test_short_music.ShortMusicTests().song()
            song['audio_mastering']='continuous-kids-mix-v1'
            (root/'song.json').write_text(json.dumps(song))
            def bad_generate(request,path,state,save):
                self.make_audio(path,internal=True)
            with patch('short_music.Path',side_effect=lambda p:Path(directory)/p),patch('music_cpu.generate_segment',side_effect=bad_generate) as model:
                with self.assertRaisesRegex(ValueError,'three quality attempts'):
                    short_music.prepare('test')
                self.assertEqual(model.call_count,3)
            target=root/'short-audio/clip-0-40'
            state=json.loads((target/'music-state.json').read_text())
            self.assertFalse(state['audio_ready'])
            self.assertEqual(len(state['quality_attempts']),3)
            self.assertEqual(len(list(target.glob('rejected-*.wav'))),3)
            native=target/'cpu-audio';native.mkdir()
            (native/'000-corrupt.wav').write_bytes(b'interrupted wave file')
            self.make_audio(native/'saved-valid.wav',1.294708,1.865729)
            with patch('short_music.Path',side_effect=lambda p:Path(directory)/p),patch('music_cpu.generate_segment') as model:
                output=short_music.prepare('test')
                model.assert_not_called()
            self.assertTrue(output.exists())
            state=json.loads((target/'music-state.json').read_text())
            self.assertTrue(state['audio_ready'])
            self.assertEqual(state['recovered_candidate'],'saved-valid.wav')
            self.assertEqual(state['recovery_rejections'][0]['code'],'unreadable_candidate')
