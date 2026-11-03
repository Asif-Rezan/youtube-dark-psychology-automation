import contextlib
import copy
import json
from pathlib import Path
import re
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
from jsonschema import Draft202012Validator
from lyrics_cpu import HINDI_LYRIC_PATTERN
from rhyme_writer import normalized, novelty_reason, write_rhyme
import test_rhyme_writer
import test_kids_rhymes


class HindiLyricsTests(unittest.TestCase):
    def test_devanagari_words_and_marks_are_valid_but_english_is_rejected(self):
        for line in ('नन्हे बच्चे बगीचे में नाचें', 'प्यारी चिड़िया फूलों के पास गाए।'):
            self.assertIsNotNone(re.fullmatch(HINDI_LYRIC_PATTERN,line))
        for line in ('Cute babies dance with animals', 'nanhe bachche bagiche mein naache',
                     'नन्हे बच्चे garden में नाचें', 'नन्हे बच्चे', 'नन्हे बच्चे १२ फूल देखें'):
            self.assertIsNone(re.fullmatch(HINDI_LYRIC_PATTERN,line))

    def test_hindi_novelty_preserves_vowels_and_unicode_equivalence(self):
        first=normalized('नन्हे बच्चे बगीचे में नाचें।')
        second=normalized('प्यारे खरगोश फूलों के पास खेलें।')
        self.assertNotEqual(first,second)
        self.assertTrue(first)
        self.assertIsNone(novelty_reason([first,second],[]))
        self.assertEqual(novelty_reason([first,second],[{'verse_lines':[first,second]}]),'duplicate_verses')
        self.assertEqual(normalized('चिड़िया'),normalized('चिड़िया'))

    def test_writer_repairs_an_english_line_without_replacing_hindi_lines(self):
        prompts=[]
        def model(schema,prompt,seed,budget=2600):
            result=test_rhyme_writer.fake_model(schema,prompt,seed,budget)
            if 'verses' in result:
                prompts.append(prompt)
                if len(prompts)==1:
                    result['verses'][0]['lyric']='Cute little babies dance with animals'
            return result
        with patch('rhyme_writer.request_json',side_effect=model):
            result=write_rhyme('2026-11-03','hindi-repair',120,[])
        self.assertEqual(len(prompts),2)
        self.assertIn('hindi_required',prompts[1])
        self.assertIn('Write visual in English',prompts[0])
        self.assertTrue(all(re.fullmatch(HINDI_LYRIC_PATTERN,row['lyric']) for row in result['sections'][0]))

    def test_song_preserves_exact_refrain_and_rejects_changed_or_english_verses(self):
        fixture=test_kids_rhymes.KidsTests();fixture.setUp()
        try:
            song=fixture.song(480)
        finally:
            fixture.doCleanups()
        from kids_rhymes import REFRAIN,validate_storyboard
        self.assertEqual(song['vocal_language'],'hi')
        self.assertTrue(all(s['lyric']==REFRAIN for s in song['scenes'][1::2]))
        for index,text in ((0,'Little baby dances with animals'),(1,'दूदी दूदी दम दम')):
            changed=copy.deepcopy(song);changed['scenes'][index]['lyric']=text
            changed['lyrics']='\n'.join(s['lyric'] for s in changed['scenes'])
            with self.assertRaises(ValueError):validate_storyboard(changed)

    def test_hindi_grammar_is_retained_for_native_generation(self):
        import lyrics_cpu
        model=Mock(tokenize=Mock(return_value=[1]))
        model.create_chat_completion.return_value={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'lyric':'नन्हे बच्चे बगीचे में नाचें'})}}]}
        schema={'type':'object','properties':{'lyric':{'type':'string','maxLength':100,'pattern':HINDI_LYRIC_PATTERN}},'required':['lyric']}
        payload={'model':lyrics_cpu.MODEL_ID,'messages':[{'role':'user','content':'Write Hindi lyrics'}],
                 'max_completion_tokens':500,'response_format':{'json_schema':{'schema':schema}}}
        with patch('lyrics_cpu.load_model',return_value=model):
            lyrics_cpu.request_story('chat/completions',payload)
        sent=model.create_chat_completion.call_args.kwargs['response_format']['schema']
        self.assertEqual(sent['properties']['lyric']['pattern'],HINDI_LYRIC_PATTERN)
        self.assertNotIn('maxLength',sent['properties']['lyric'])

    def test_music_runtime_receives_hindi_language_without_changing_lyrics(self):
        import music_cpu
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);raw=root/'native.wav';raw.write_bytes(b'audio')
            torch=Mock();torch.inference_mode.return_value=contextlib.nullcontext()
            handler=Mock(device='cpu');handler.initialize_service.return_value=(None,True)
            params=Mock();config=Mock();infer=Mock(return_value=types.SimpleNamespace(success=True,audios=[{'path':str(raw)}]))
            song=dict(_segment=True,prompt='Hindi nursery rhyme',lyrics='नन्हे बच्चे बगीचे में नाचें\ndudi dudi dam dam dudi dudi dam',duration=40,vocal_language='hi',generation_seed=20261104,reference_cover=True,cover_strength=0.75)
            with patch.dict('os.environ',{}),patch('music_cpu.checkpoints'),patch('music_cpu.reference_audio',return_value='reference.mp3'), \
                 patch('music_cpu.runtime',return_value=(torch,Mock(return_value=handler),params,config,infer)), \
                 patch('music_cpu.generation_progress',return_value=contextlib.nullcontext()),patch('pipeline.duration',return_value=40):
                music_cpu.synthesize(song,root/'result.wav',root,root)
            self.assertEqual(params.call_args.kwargs['task_type'],'cover')
            self.assertEqual(params.call_args.kwargs['src_audio'],'reference.mp3')
            self.assertEqual(params.call_args.kwargs['audio_cover_strength'],0.75)
            self.assertEqual(config.call_args.kwargs['seeds'],[20261104])
            self.assertFalse(config.call_args.kwargs['use_random_seed'])
            self.assertEqual(params.call_args.kwargs['reference_audio'],'reference.mp3')
            self.assertEqual(params.call_args.kwargs['vocal_language'],'hi')
            self.assertEqual(params.call_args.kwargs['lyrics'],song['lyrics'])
