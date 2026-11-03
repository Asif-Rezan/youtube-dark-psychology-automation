import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from rhyme_writer import write_rhyme, novelty_reason, normalized, VERSION, request_json
from lyrics_cpu import StoryGenerationError

WORDS=['amber','blue','coral','daisy','emerald','fern','golden','hazel','indigo','jolly','kiwi','lemon']

def fake_model(schema,prompt,seed,budget=2600):
    if 'chapters' in schema['properties']:
        count=schema['properties']['chapters']['minItems']
        return {'title':f'The Shimmering Seed Adventure {seed}',
            'characters':'A lavender baby elephant and a tiny teal turtle with a golden shell.',
            'visual_world':'A peach-colored seaside garden with shell paths and coral flowers.',
            'story_summary':'Duck and bunny discover a shiny seed and grow a magical garden together.',
            'description':'A playful English rhyme about duck and bunny planting a seed, caring for flowers and sharing kindness.',
            'chapters':[f'Chapter {i}: find a friendly surprise in the garden' for i in range(count)]}
    count=schema['properties']['verses']['minItems']
    # Distinct fixture words, varying with the model request seed.
    signature=''.join(chr(97+int(c,16)) for c in format(seed,'x'))
    return {'verses':[{'lyric':f'{WORDS[i]} friendly {signature} ducklings explore meadow',
                       'visual':f'Duckling and bunny wave beside a {WORDS[i]} flower bed'} for i in range(count)]}

class WriterTests(unittest.TestCase):
    def test_original_ai_requests_and_checkpoint_resume(self):
        with tempfile.TemporaryDirectory() as tmp, patch('rhyme_writer.request_json',side_effect=fake_model) as model:
            path=Path(tmp)/'draft.json'
            result=write_rhyme('2026-10-28','one',600,[],path)
            self.assertEqual(model.call_count,6)
            outline_prompt=model.call_args_list[0].args[1]
            self.assertIn('choose a NEW cast',outline_prompt)
            self.assertIn('led by one or two adorable baby animals',outline_prompt)
            self.assertIn('two cute human toddlers',outline_prompt)
            self.assertNotIn('exactly two toddlers',outline_prompt)
            self.assertNotIn('adventure with a yellow duckling',outline_prompt)
            self.assertIn(result['outline']['characters'],model.call_args_list[1].args[1])
            self.assertEqual(sum(map(len,result['sections'])),60)
            self.assertTrue(result['novelty_checked'])
            self.assertEqual(result['writer_version'],VERSION)
            again=write_rhyme('2026-10-28','one',600,[],path)
            self.assertEqual(again,result)
            self.assertEqual(model.call_count,6)
            with self.assertRaises(ValueError): write_rhyme('2026-10-28','another',600,[],path)

    def test_failed_chapter_resumes_without_rewriting_finished_chapters(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'draft.json'
            calls=0
            def interrupted(*args,**kwargs):
                nonlocal calls
                calls+=1
                if calls==4: raise StoryGenerationError('interrupted')
                return fake_model(*args,**kwargs)
            with patch('rhyme_writer.request_json',side_effect=interrupted), self.assertRaises(StoryGenerationError):
                write_rhyme('2026-10-28','resume',480,[],path)
            saved=json.loads(path.read_text())
            self.assertEqual(len(saved['sections']),2)
            with patch('rhyme_writer.request_json',side_effect=fake_model) as model:
                finished=write_rhyme('2026-10-28','resume',480,[],path)
                self.assertEqual(model.call_count,2)
            self.assertEqual(finished['sections'][:2],saved['sections'])

    def test_repeated_lines_fail_without_template_fallback(self):
        def repeated(schema,prompt,seed,budget=2600):
            result=fake_model(schema,prompt,seed)
            if 'verses' in result:
                for row in result['verses']: row['lyric']='Happy little bunny waves hello'
            return result
        with patch('rhyme_writer.request_json',side_effect=repeated), self.assertRaises(StoryGenerationError):
            write_rhyme('2026-10-28','repeat',480,[])

    def test_repairs_only_rejected_lines_with_feedback(self):
        calls=[]
        def model(schema,prompt,seed,budget=2600):
            result=fake_model(schema,prompt,seed)
            if 'verses' in result:
                calls.append((schema['properties']['verses']['minItems'],prompt))
                if len(calls)==1:
                    result['verses'][0]['lyric']='Too short'
                    result['verses'][1]['lyric']=result['verses'][2]['lyric']
            return result
        with patch('rhyme_writer.request_json',side_effect=model):
            result=write_rhyme('2026-10-28','repair',120,[])
        self.assertEqual([call[0] for call in calls],[12,2])
        self.assertIn('word_count',calls[1][1])
        self.assertIn('duplicate_line',calls[1][1])
        self.assertEqual(len(result['sections'][0]),12)
        self.assertNotIn('pending',result)

    def test_exhausted_repairs_save_partial_progress_and_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'draft.json'
            def model(schema,prompt,seed,budget=2600):
                result=fake_model(schema,prompt,seed)
                if 'verses' in result:
                    for row in result['verses']:
                        row['lyric']='Happy little bunny waves hello'
                return result
            with patch('rhyme_writer.request_json',side_effect=model), self.assertRaises(StoryGenerationError) as caught:
                write_rhyme('2026-10-28','partial',120,[],path)
            self.assertEqual(caught.exception.code,'lyrics_verse_validation')
            self.assertTrue(caught.exception.retryable)
            self.assertEqual(caught.exception.details['accepted_lines'],1)
            saved=json.loads(path.read_text())
            self.assertEqual(len(saved['pending']['rows']),1)
            with patch('rhyme_writer.request_json',side_effect=fake_model) as model_call:
                result=write_rhyme('2026-10-28','partial',120,[],path)
            self.assertEqual(model_call.call_count,1)
            self.assertEqual(result['sections'][0][0],saved['pending']['rows'][0])
            self.assertEqual(len(result['sections'][0]),12)

    def test_novelty_compares_verses_not_shared_refrain(self):
        lines=['tiny ducklings carry baskets full of daisies','bunny paints a rainbow across the sky']
        self.assertIsNone(novelty_reason(lines,[]))
        self.assertEqual(novelty_reason(lines,[{'verse_lines':lines}]),'duplicate_verses')
        self.assertEqual(novelty_reason([lines[0],lines[0]],[]),'repeated_verse_in_episode')
        self.assertIsNone(novelty_reason(lines,[{'verse_lines':['gentle sea turtles build castles with sand']}]))

    def test_retryable_model_request_recovers_with_fresh_seed(self):
        error=StoryGenerationError('Invalid JSON',code='lyrics_schema_validation',retryable=True)
        seeds=[]
        def response(endpoint,payload):
            seeds.append(payload['seed'])
            if len(seeds)<3:
                raise error
            self.assertIn('characters',payload['bounded_metadata_fields'])
            self.assertIn('visual_world',payload['bounded_metadata_fields'])
            return {'choices':[{'message':{'content':'{"ready":true}'}}]}
        with patch('rhyme_writer.request_story',side_effect=response):
            self.assertEqual(request_json({},'Write a rhyme',123),{'ready':True})
        self.assertEqual(seeds,[123,8042,15961])

    def test_model_request_retries_are_bounded_and_fatal_errors_not_retried(self):
        for retryable,count in ((True,3),(False,1)):
            error=StoryGenerationError('Model failure',retryable=retryable)
            with patch('rhyme_writer.request_story',side_effect=error) as model:
                with self.assertRaises(StoryGenerationError):
                    request_json({},'Write a rhyme',123)
            self.assertEqual(model.call_count,count)

    def test_recent_identical_cast_is_rejected(self):
        history = [{'visual_identity': {'characters':
            'A lavender baby elephant and a tiny teal turtle with a golden shell.'}}]
        with patch('rhyme_writer.request_json', side_effect=fake_model), self.assertRaises(StoryGenerationError):
            write_rhyme('2026-10-28', 'same-cast', 120, history)

    def test_different_run_ids_produce_different_model_seeds(self):
        with patch('rhyme_writer.request_json',side_effect=fake_model):
            first=write_rhyme('2026-10-28','first',480,[])
            second=write_rhyme('2026-10-28','second',480,[])
        self.assertNotEqual(first['outline'],second['outline'])
        self.assertNotEqual(first['sections'],second['sections'])

    def test_rejected_long_line_is_sent_for_targeted_rewrite(self):
        from lyrics_cpu import LYRIC_WORD_PATTERN
        from jsonschema import Draft202012Validator
        calls=[]
        long_line='One two three four five six seven eight nine ten eleven twelve thirteen'
        def model(schema,prompt,seed,budget=2600):
            result=fake_model(schema,prompt,seed,budget)
            if 'verses' in result:
                calls.append((copy.deepcopy(schema),prompt))
                if len(calls)==1:
                    result['verses'][0]['lyric']=long_line
            return result
        with patch('rhyme_writer.request_json',side_effect=model):
            result=write_rhyme('2026-11-01','long-line-regression',120,[])
        self.assertEqual(len(result['sections'][0]),12)
        self.assertEqual(len(calls),2)
        self.assertIn(long_line,calls[1][1])
        lyric_schema=calls[0][0]['properties']['verses']['items']['properties']['lyric']
        self.assertEqual(lyric_schema['pattern'],LYRIC_WORD_PATTERN)
        validator=Draft202012Validator(lyric_schema)
        self.assertTrue(validator.is_valid('Tiny bunny hops beside flowers'))
        self.assertFalse(validator.is_valid(long_line))
        for line in ('One two three',"Tiny bunny's ears dance and sway",'one two three four-five'):
            self.assertFalse(validator.is_valid(line))
