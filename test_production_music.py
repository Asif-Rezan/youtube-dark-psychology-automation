from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch
from production_music import request,source_window
from lyrics_quality import assess,identity,validate_segment,LyricsQualityError


class ProductionMusicTests(unittest.TestCase):
    def test_source_offset_and_new_lyrics_survive_request(self):
        song=dict(duration=120,lyrics='रंग बिरंगी तितली आई\ndudi dudi dam dam dudi dudi dam',prompt='old')
        prepared=request(song,120)
        self.assertEqual(prepared['reference_start'],120)
        self.assertIn('तितली',prepared['lyrics'])
        self.assertNotEqual(prepared['source_lyrics'],prepared['lyrics'])
        self.assertTrue(prepared['verify_lyrics'])
        self.assertEqual(prepared['flow_edit_task'],'text2music')
        self.assertEqual(prepared['flow_edit_n_min'],0)
        self.assertEqual(song['prompt'],'old')

    def test_reference_window_does_not_loop_and_rejects_short_source(self):
        import subprocess
        from pipeline import duration
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source.wav'
            subprocess.run(['ffmpeg','-y','-v','error','-f','lavfi','-i',
                'sine=frequency=440:duration=3',str(source)],check=True)
            window=source_window(source,1,1,root)
            self.assertAlmostEqual(duration(window),1,places=2)
            with self.assertRaisesRegex(ValueError,'shorter'):
                source_window(source,2,2,root)


class DynamicLyricsVerificationTests(unittest.TestCase):
    song=dict(lyrics='रंग बिरंगी तितली आई\nदूदी दूदी दम दम\nनीले बादल पानी लाएं')

    def test_checks_episode_specific_lyrics_without_hardcoded_preview_words(self):
        self.assertEqual(assess(self.song,'रंग बिरंगी तितली आई नीले बादल पानी लाएं')['status'],'passed')
        self.assertEqual(assess(self.song,'दूदी दूदी दम दम')['status'],'needs_review')
        self.assertEqual(assess(self.song,'रंग बिरंगी तितली आई')['status'],'needs_review')
        other=dict(lyrics='लाल गुब्बारा ऊपर उड़ा\nपीला बच्चा हंसता चला')
        self.assertEqual(assess(other,other['lyrics'])['status'],'passed')
        self.assertEqual(assess(other,self.song['lyrics'])['status'],'needs_review')

    def test_cached_audio_requires_matching_verified_lyrics(self):
        song=dict(self.song,verify_lyrics=True)
        with tempfile.TemporaryDirectory() as tmp:
            audio=Path(tmp)/'part.wav';audio.write_bytes(b'audio')
            report=audio.with_suffix('.lyrics-quality.json')
            report.write_text(json.dumps(dict(status='passed',**identity(song,audio))))
            state={}
            with patch('worker_limits.run_worker') as worker:
                validate_segment(song,audio,state,lambda:None)
                worker.assert_not_called()
            self.assertEqual(state['lyrics_quality']['status'],'passed')

    def test_quality_failure_retains_audio_and_blocks_ready_state(self):
        from worker_limits import WorkerFailure
        with tempfile.TemporaryDirectory() as tmp:
            audio=Path(tmp)/'part.wav';audio.write_bytes(b'audio')
            report=audio.with_suffix('.lyrics-quality.json')
            def fail(*a,**kw):
                report.write_text(json.dumps(dict(status='needs_review')))
                raise RuntimeError('unused')
            # A worker exit without verified words must never be reclassified as passed.
            report.write_text(json.dumps(dict(status='needs_review')))
            state={'audio_ready':True}
            with patch('worker_limits.run_worker',side_effect=OSError('exit 2')):
                with self.assertRaises(LyricsQualityError):
                    validate_segment(dict(self.song,verify_lyrics=True),audio,state,lambda:None)
            self.assertTrue(audio.exists())
            self.assertFalse(state['audio_ready'])


class PublicationFailureMessageTests(unittest.TestCase):
    def test_quality_failure_has_distinct_safe_message(self):
        from pipeline import pipeline_failure_message
        message=pipeline_failure_message(LyricsQualityError('internal details'))
        self.assertIn('[lyrics_unverified]',message)
        self.assertIn('Publication blocked',message)
        self.assertNotIn('internal details',message)


class PublicationLyricGateTests(unittest.TestCase):
    def test_missing_mismatched_and_unverified_audio_cannot_publish(self):
        from lyrics_quality import require_verified
        song=dict(lyrics='नए शब्द')
        with tempfile.TemporaryDirectory() as tmp:
            audio=Path(tmp)/'song.wav';audio.write_bytes(b'audio')
            with self.assertRaises(LyricsQualityError):require_verified(song,audio)
            report=audio.with_suffix('.lyrics-quality.json')
            report.write_text(json.dumps(dict(status='passed',**identity(song,audio))))
            require_verified(song,audio)
            with self.assertRaises(LyricsQualityError):require_verified(dict(lyrics='changed'),audio)
            audio.write_bytes(b'changed audio')
            with self.assertRaises(LyricsQualityError):require_verified(song,audio)
