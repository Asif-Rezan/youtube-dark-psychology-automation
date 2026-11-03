import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import lyrics_cpu as cpu
from rhyme_writer import write_rhyme, VERSION
from prepare_music import record_failure

class BoundsTests(unittest.TestCase):
    def request(self, data, properties, fields):
        payload={'messages':[{'role':'user','content':'Write a rhyme'}],
            'response_format':{'json_schema':{'schema':{'type':'object','properties':properties,
                'required':list(properties),'additionalProperties':False}}},
            'bounded_metadata_fields':fields,'max_completion_tokens':256}
        model=Mock(tokenize=Mock(return_value=[1]),create_chat_completion=Mock(return_value={
            'choices':[{'finish_reason':'stop','message':{'content':json.dumps(data)}}]}))
        with patch.object(cpu,'load_model',return_value=model):
            result=cpu.request_story('chat/completions',payload)
        return json.loads(result['choices'][0]['message']['content']),model

    def test_failed_description_is_bounded_without_changing_lyrics(self):
        lyrics='Little ducklings splash and play'
        result,model=self.request({'description':'Duck and bunny explore the sunny garden together. '*30,'lyric':lyrics},
            {'description':{'type':'string','minLength':80,'maxLength':650},'lyric':{'type':'string'}},['description'])
        self.assertLessEqual(len(result['description']),650)
        self.assertTrue(result['description'].endswith('.'))
        self.assertEqual(result['lyric'],lyrics)
        model.create_chat_completion.assert_called_once()

    def test_title_and_whitespace_normalization_are_returned(self):
        result,_=self.request({'title':'The bright bunny and duck explore a magical rainbow garden', 'description':'  Happy   friends.  '},
            {'title':{'type':'string','maxLength':25},'description':{'type':'string','maxLength':650}},['title','description'])
        self.assertEqual(result['title'],'The bright bunny and duck')
        self.assertEqual(result['description'],'Happy friends.')

    def test_overlong_visual_identity_recovers_without_model_retry(self):
        # Reproduce the production failure (285 characters versus a 180 limit),
        # and cover both new outline fields and extreme overlong prose.
        for field in ('characters', 'visual_world'):
            for length in (206, 210, 285, 1500):
                with self.subTest(field=field, length=length):
                    text=('A lavender elephant and teal turtle explore a pastel garden. ' * 30)[:length]
                    result,model=self.request({field:text,'lyric':'Tiny friends jump beside flowers',
                        'visual':'Elephant and turtle hop beside pink flowers.'},
                        {field:{'type':'string','minLength':20,'maxLength':180},
                         'lyric':{'type':'string'},'visual':{'type':'string'}},
                        [field,'lyric','visual'])
                    self.assertTrue(20 <= len(result[field]) <= 180)
                    self.assertTrue(result[field].endswith('.'))
                    self.assertEqual(result['lyric'],'Tiny friends jump beside flowers')
                    self.assertEqual(result['visual'],'Elephant and turtle hop beside pink flowers.')
                    model.create_chat_completion.assert_called_once()

    def test_sung_lyrics_are_never_truncated(self):
        with self.assertRaises(cpu.StoryGenerationError) as caught:
            self.request({'lyric':'private words '*30},{'lyric':{'type':'string','maxLength':100}},['lyric'])
        self.assertEqual(caught.exception.code,'lyrics_schema_validation')
        self.assertEqual(caught.exception.details['actual_length'],420)
        self.assertEqual(caught.exception.details['attempts'],3)
        self.assertTrue(caught.exception.retryable)

    def test_nonobject_json_produces_structured_failure(self):
        with self.assertRaises(cpu.StoryGenerationError) as caught:
            self.request([],{'description':{'type':'string'}},['description'])
        self.assertEqual(caught.exception.details['constraint'],'type')

    def test_initial_failure_keeps_identity_and_safe_diagnostics(self):
        with tempfile.TemporaryDirectory() as directory:
            draft=Path(directory)/'draft.json'
            error=cpu.StoryGenerationError('Invalid generated JSON',code='lyrics_schema_validation',details={'field':'description'},retryable=True)
            with patch('rhyme_writer.request_json',side_effect=error):
                with self.assertRaises(cpu.StoryGenerationError):
                    write_rhyme('2026-10-28','new-song',600,[],draft)
            state=json.loads(draft.read_text())
            self.assertEqual((state['writer_version'],state['run_id']),(VERSION,'new-song'))
            with patch('prepare_music.Path',side_effect=lambda p:Path(directory)/p):
                record_failure('new-song','lyrics',error)
                record_failure('private-error','lyrics',RuntimeError('secret token'))
            failure=json.loads((Path(directory)/'output/new-song/failure.json').read_text())
            self.assertEqual(failure['details'],{'field':'description'})
            self.assertNotIn('secret token',(Path(directory)/'output/private-error/failure.json').read_text())

    def test_compact_word_constraint_is_retained_in_native_grammar(self):
        from lyrics_cpu import LYRIC_WORD_PATTERN
        result,model=self.request({'lyric':'Tiny bunny hops beside flowers'},
            {'lyric':{'type':'string','maxLength':100,'pattern':LYRIC_WORD_PATTERN}},[])
        schema=model.create_chat_completion.call_args.kwargs['response_format']['schema']
        self.assertEqual(schema['properties']['lyric']['pattern'],LYRIC_WORD_PATTERN)
        self.assertNotIn('maxLength',schema['properties']['lyric'])
        self.assertEqual(result['lyric'],'Tiny bunny hops beside flowers')
