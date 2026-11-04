import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from continuous_song import continuous_request, render_continuous


class ContinuousSongTests(unittest.TestCase):
    def test_one_full_song_inference_then_whole_file_encoding(self):
        verses=['पहली नई पंक्ति','दूसरी नई पंक्ति']
        with tempfile.TemporaryDirectory() as tmp, \
             patch.dict('os.environ', {'ACESTEP_SOURCE_DIR':'source','ACESTEP_CHECKPOINTS_DIR':'models','ACE_SOURCE_TRANSCRIPT':str(Path(tmp)/'source.json')}), \
             patch('music_cpu.synthesize') as synthesize, \
             patch('pipeline.duration',return_value=60), \
             patch('continuous_song.subprocess.run') as encode:
            (Path(tmp)/'source.json').write_text(json.dumps(dict(text='दूदी दूदी दम दम',segments=[])))
            target=render_continuous(verses,'test',Path(tmp))
            synthesize.assert_called_once()
            request=synthesize.call_args.args[0]
            self.assertEqual(request['duration'],60)
            self.assertTrue(request['reference_cover'])
            self.assertEqual(request['cover_noise_strength'],0.0)
            self.assertFalse(request.get('reference_repaint'))
            self.assertNotIn('edit_source',request)
            for verse in verses:
                self.assertIn(verse,request['lyrics'])
            encode.assert_called_once()
            command=encode.call_args.args[0]
            self.assertEqual(command.count('-i'),1)
            self.assertEqual(command[command.index('-i')+1],str(target))
            report=json.loads((Path(tmp)/'arrangement-report.json').read_text())
            self.assertFalse(report['audio_splicing'])

    def test_short_source_rejected_before_inference(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.dict('os.environ', {'ACE_SOURCE_TRANSCRIPT':str(Path(tmp)/'source.json')}), \
             patch('pipeline.duration', return_value=30), \
             patch('music_cpu.synthesize') as synthesize:
            (Path(tmp)/'source.json').write_text(json.dumps(dict(text='original',segments=[])))
            with self.assertRaisesRegex(ValueError, 'requires a source'):
                render_continuous(['एक','दो'], 'test', Path(tmp))
            synthesize.assert_not_called()

    def test_reject_duplicate_verse_blocks(self):
        with self.assertRaises(ValueError):
            continuous_request(['same','same'],'test','original')


class FlowLyricTests(unittest.TestCase):
    def test_source_and_target_conditioning_are_separate(self):
        from music_cpu import flow_edit_options
        song=continuous_request(['तितली आई','कागज़ की नाव'],'test','दूदी दूदी दम दम',mode='flow-full')
        opts=flow_edit_options(song)
        self.assertTrue(opts['flow_edit_morph'])
        self.assertEqual(opts['flow_edit_n_min'],0.0)
        self.assertEqual(opts['flow_edit_source_lyrics'],'दूदी दूदी दम दम')
        self.assertNotEqual(opts['flow_edit_source_lyrics'],song['lyrics'])
        self.assertEqual(opts['flow_edit_source_caption'],song['prompt'])
        with self.assertRaises(ValueError):
            flow_edit_options(dict(song,source_lyrics=''))

    def test_audio_check_rejects_unchanged_source_and_checks_both_verses(self):
        from scripts.verify_ace_lyrics import assess
        original='दूदी दूदी दम दम'
        self.assertFalse(assess(original,original)['replacement_verses_detected'])
        self.assertFalse(assess(original,'तितली आई')['replacement_verses_detected'])
        self.assertTrue(assess(original,'तितली आई कागज़ की नाव')['replacement_verses_detected'])


class EmptySourceTranscriptTests(unittest.TestCase):
    def test_empty_asr_uses_only_hash_matched_supplied_lyrics(self):
        import hashlib
        from scripts.transcribe_ace_source import resolve_transcript
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.mp3'; source.write_bytes(b'reference')
            fallback=dict(source_sha256=hashlib.sha256(b'reference').hexdigest(),known_lyrics='दूदी दम')
            result=resolve_transcript(dict(text='',segments=[]),source,fallback)
            self.assertTrue(result['partial_lyrics'])
            self.assertEqual(result['text'],'दूदी दम')
            with self.assertRaises(ValueError):
                resolve_transcript(dict(text=''),source,dict(fallback,source_sha256='wrong'))
            recognized=resolve_transcript(dict(text='recognized',segments=[]),source,fallback)
            self.assertFalse(recognized['partial_lyrics'])
            self.assertEqual(recognized['text'],'recognized')


class FullScheduleRegressionTests(unittest.TestCase):
    def test_default_cover_releases_late_steps_to_new_lyrics_without_noise_truncation(self):
        from music_cpu import reference_cover_options, flow_edit_options
        request=continuous_request(['पहली पंक्ति','दूसरी पंक्ति'],'test','दूदी दम')
        opts=reference_cover_options(request,'source.mp3')
        self.assertEqual(opts['cover_noise_strength'],0.0)
        self.assertLess(opts['audio_cover_strength'],1.0)
        self.assertEqual(flow_edit_options(request),{})
        self.assertEqual(int(8*opts['audio_cover_strength']),5)

    def test_invalid_flow_start_rejected(self):
        from music_cpu import flow_edit_options
        request=continuous_request(['पहली पंक्ति','दूसरी पंक्ति'],'test','दूदी दम',mode='flow-full')
        for value in [1,-1,float('nan')]:
            with self.assertRaises(ValueError):
                flow_edit_options(dict(request,flow_edit_n_min=value))
