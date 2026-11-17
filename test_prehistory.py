import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from episode_packaging import public_metadata
from prehistory.editorial import (CHAPTER_COUNT, ancient_humans_title, chapter_issues, expand_short_narration, generate,
                                  metadata, normalize_chapter_label, valid_chapters)
from prehistory.production import FULL_RUNTIME, MASTER_GAIN, NARRATION_PAUSE, calibrate_narration_speed, narration_filter, runtime_timing
from prehistory.visuals import cover, scene
from upload_settings import load_settings, upload_body


class PrehistoryTests(unittest.TestCase):
    def test_qwen_plan_produces_distinct_story_and_measured_chapters(self):
        idea = {'topic':'stone-tools','title':'Why Did Early Humans Break Stones on Purpose?',
                'hook':'BREAK STONES?','description':'A single sharp edge changed what early people could do.',
                'angle':'Start with a stone flake','tags':['stone tools']*6}
        story = []
        for index in range(CHAPTER_COUNT):
            label = ('A Broken Stone','Making an Edge')[index] if index<2 else f'New Evidence {index}'
            narration = ('This looks like an ordinary stone at first. Why did early toolmakers strike another stone '
                         'against it to make a sharper edge? One small flake can preserve clues about how somebody shaped a larger stone long before the tool itself was found.')
            story.append({'label':label,'beats':[{'narration':narration,'action':'show','prop':'stone'}]*3})
        responses = [idea]+[{'chapters':story[i:i+4]} for i in range(0,CHAPTER_COUNT,4)]
        with patch('prehistory.editorial.ask',side_effect=responses):
            plan = generate('prehistory-test',[])
        self.assertEqual(len(plan['chapters']),20)
        result = metadata(plan,list(range(0,600,30)))
        self.assertEqual(plan['hook'],'WHAT DID IT CUT?')
        self.assertIn('00:00 A Broken Stone\n00:30 Making an Edge',result['description'])
        self.assertIn('Smithsonian Human Origins Program',result['description'])
        self.assertEqual(public_metadata(result)['title'],'Why Did Ancient Humans Break Stones on Purpose?')

    def test_short_chapter_repair_preserves_valid_work_and_resumes_from_checkpoint(self):
        idea = {'topic':'stone-tools','title':'Why Did Early Humans Break Stones on Purpose?',
                'hook':'WHAT DID IT CUT?', 'description':'A sharp edge changed what was possible.',
                'tags':['stone tools']*6,'angle':'Start with a flake.'}
        text = ('At first this looks like an ordinary broken stone. The edge can offer a clue about '
                'how early humans made cutting tools. Could this flake have broken off because somebody struck a larger core on purpose?')
        def chapter(index, narration=text):
            return {'label':f'Stone Evidence {index}',
                    'beats':[{'narration':narration,'action':'show','prop':'stone'} for _ in range(3)]}
        saved = []
        checkpoint = {'idea':idea,'chapters':[chapter(i) for i in range(1,17)]}
        bad = [chapter(17),chapter(18,'Too short.'),chapter(19),chapter(20)]
        with patch('prehistory.editorial.ask',side_effect=[{'chapters':bad},{'chapters':[chapter(18)]}]) as call:
            result = generate('prehistory-resume',[],checkpoint,lambda data: saved.append(len(data['chapters'])))
        self.assertEqual(saved,[17,20])
        self.assertEqual(len(result['chapters']),20)
        self.assertIn('Write only chapters [18]',call.call_args_list[1].args[0])

    def test_one_word_label_and_underwritten_beats_are_repaired_without_redrawing(self):
        marker = {'sex':'female','action':'work','position':'left'}
        counts = (22,19,21)
        chapter = {'label':normalize_chapter_label('  Origins  ',3,set()),
                   'beats':[{'narration':' '.join(['evidence']*count)+'.','cast':[marker],
                             'setting':'workshop','framing':'detail','prop':'stone','secondary_prop':'none'}
                            for count in counts]}
        addition = ('A researcher can compare the tool with similar finds and look for signs of how it was made.')
        with patch('prehistory.editorial.ask',return_value={f'beat_{i}':addition for i in range(1,4)}) as call:
            result = expand_short_narration(chapter,3,'Stone flakes preserve signs of toolmaking.',100)
        self.assertEqual(call.call_count,1)
        self.assertEqual(result['label'],'Origins')
        self.assertEqual(chapter_issues(result,set()),[])
        self.assertEqual(result['beats'][0]['cast'],[marker])
        self.assertNotEqual(normalize_chapter_label('Origins',4,{'origins'}).casefold(),'origins')

    def test_evidence_fallback_repairs_the_failed_chapter_word_counts(self):
        from prehistory.editorial import TOPICS
        from lyrics_cpu import StoryGenerationError

        for counts in ((51,24,23),(25,25,30),(28,23,26),(35,32,24)):
            for _, _, evidence, prop, _ in TOPICS.values():
                with self.subTest(counts=counts, prop=prop):
                    beats = [{'narration':' '.join(['original']*count)+'.',
                              'action':'show','prop':prop} for count in counts]
                    chapter = {'label':'Material Evidence','beats':beats}
                    with patch('prehistory.editorial.ask',side_effect=StoryGenerationError(
                            'Truncated JSON',retryable=True)):
                        result = expand_short_narration(chapter,5,evidence,77)
                    self.assertEqual(chapter_issues(result,set()),[])
                    for old, new in zip(beats,result['beats']):
                        self.assertTrue(new['narration'].startswith(old['narration']))
                        self.assertEqual(old['prop'],new['prop'])

    def test_ancient_humans_branding_applies_once_to_saved_titles(self):
        self.assertEqual(ancient_humans_title('How did early humans find food?'),
                         'How did Ancient Humans find food?')
        title = ancient_humans_title('What Did the First Hearths Change?')
        self.assertEqual(title, 'What Did the First Hearths Change? | Ancient Humans')
        self.assertEqual(ancient_humans_title(title),title)

    def test_parallel_chapters_use_global_shot_indices_and_require_matching_timing(self):
        import json
        from prehistory.production import plan_digest, render_shots, timed_shots

        beat = {'prop':'stone','action':'watch'}
        plan = {'chapters':[{'label':'Start','beats':[beat,beat]},
                            {'label':'Evidence','beats':[beat]},
                            {'label':'Conclusion','beats':[beat]}]}
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            timing = work/'timing.json'
            timing.write_text(json.dumps({'plan_sha256':plan_digest(plan),'frames':[260,300,320,240]}))
            with patch.dict('os.environ',{},clear=True), patch('prehistory.production.clip') as clip:
                render_shots(plan,work,chapter=1)
            clip.assert_called_once_with(beat,2,320,work/'v-2.mp4','Evidence')
            plan['chapters'][0]['label'] = 'Different plan'
            with self.assertRaisesRegex(ValueError,'do not match'):
                timed_shots(plan,work)

    def test_deeper_pitch_preserves_the_requested_tempo(self):
        for rate in (24000,48000):
            filters = dict(item.split('=',1) for item in narration_filter(1.05,rate).split(',')[:-1])
            self.assertLess(int(filters['asetrate']),rate)
            self.assertAlmostEqual(int(filters['asetrate'])/rate*float(filters['atempo']),1.05,places=6)
        self.assertEqual(MASTER_GAIN,2.0)

    def test_kokoro_calibration_slows_a_fast_voice_to_fit_the_documentary(self):
        beats = [{'narration':'word '*40} for _ in range(60)]
        with tempfile.TemporaryDirectory() as tmp, patch('builtins.print'):
            measured = {}
            def synthesize(text,path,*,speed):
                measured[path] = len(text.split())*.29*.95/speed
            speed = calibrate_narration_speed(synthesize,Path(tmp),beats,FULL_RUNTIME,measured.__getitem__)
        self.assertLess(speed,.95)
        lengths = [40*.29*.95/speed]*60
        tempo = runtime_timing(lengths,FULL_RUNTIME,word_count=2400)
        self.assertTrue(900<=sum(lengths)/tempo+60*NARRATION_PAUSE<=1500)
        self.assertEqual(len(measured),3)

    def test_runtime_uses_modest_tempo_correction_and_rejects_impossible_lengths(self):
        self.assertEqual(runtime_timing([17]*60,FULL_RUNTIME),1)
        self.assertLess(runtime_timing([14]*60,FULL_RUNTIME),1)
        self.assertGreater(runtime_timing([25]*60,FULL_RUNTIME),1)
        with self.assertRaisesRegex(RuntimeError,'natural speaking speed'):
            runtime_timing([8]*60,FULL_RUNTIME)

    def test_runtime_uses_measured_spoken_pace_for_larger_corrections(self):
        for raw, words in ((700, 2160), (1800, 3300)):
            with self.subTest(raw=raw):
                lengths = [raw / 60] * 60
                tempo = runtime_timing(lengths, FULL_RUNTIME, word_count=words)
                self.assertFalse(.85 <= tempo <= 1.15)
                adjusted = raw / tempo + 60 * NARRATION_PAUSE
                self.assertTrue(900 <= adjusted <= 1500)
        with self.assertRaisesRegex(RuntimeError, 'required_tempo='):
            runtime_timing([1800 / 60] * 60, FULL_RUNTIME, word_count=5000)
        with self.assertRaisesRegex(RuntimeError, 'required_tempo='):
            runtime_timing([480 / 60] * 60, FULL_RUNTIME, word_count=2160)

    def test_work_animation_has_white_stage_and_moving_pixels(self):
        beat = {'prop':'stone','action':'work'}
        first, next_frame = scene(beat,0,8,0), scene(beat,.22,8,0)
        self.assertEqual(first.getpixel((16,16)),(255,255,255))
        self.assertNotEqual(first.tobytes(),next_frame.tobytes())
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)/'cover.jpg'
            cover({'topic':'stone-tools','hook':'WHAT DID IT CUT?'},target)
            with Image.open(target) as image:
                self.assertEqual(image.size,(1920,1080))
            self.assertLess(target.stat().st_size,2*1024**2)

    def test_story_cast_supports_independent_male_and_female_actions(self):
        beat = {'prop':'food','setting':'camp','secondary_prop':'fire','framing':'wide',
                'narration':'The group brings food back to the hearth, where some gather supplies and the others prepare to share them.',
                'cast':[{'sex':'male','action':'carry','position':'left'},
                        {'sex':'female','action':'share','position':'right'}]}
        self.assertTrue(valid_chapters([{'label':'Back at Camp','beats':[beat]}]))
        first = scene(beat,0,10,0)
        second = scene(beat,1.6,10,0)
        self.assertNotEqual(first.crop((180,195,480,630)).tobytes(),
                            second.crop((180,195,480,630)).tobytes())
        self.assertNotEqual(first.crop((840,195,1060,630)).tobytes(),
                            second.crop((840,195,1060,630)).tobytes())
        beat['cast'][1]['position'] = 'left'
        self.assertFalse(valid_chapters([{'label':'Back at Camp','beats':[beat]}]))

    def test_explaining_character_continues_to_move(self):
        beat = {'prop':'map','action':'show'}
        self.assertNotEqual(scene(beat,.2,10,0).tobytes(),scene(beat,.55,10,0).tobytes())

    def test_scene_sets_have_distinct_terrain_and_preserve_white_canvas(self):
        workshop = scene({'prop':'stone','action':'work'},0,10,0)
        hearth = scene({'prop':'fire','action':'show'},0,10,0)
        self.assertEqual(workshop.getpixel((16,16)),(255,255,255))
        self.assertEqual(hearth.getpixel((16,16)),(255,255,255))
        self.assertNotEqual(workshop.crop((0,272,240,580)).tobytes(),
                            hearth.crop((0,272,240,580)).tobytes())

    def test_daylight_and_hearth_covers_use_different_scene_contrast(self):
        with tempfile.TemporaryDirectory() as tmp:
            samples = {}
            for topic, hook in (('food','WHAT WAS DINNER?'),('hearths','AFTER DARK?')):
                path = Path(tmp)/f'{topic}.jpg'
                cover({'topic':topic,'title':topic,'hook':hook},path)
                with Image.open(path) as image:
                    samples[topic] = image.getpixel((400,290))
            self.assertGreater(sum(samples['food']),sum(samples['hearths'])+60)

    def test_documentary_upload_is_english_education_for_a_general_audience(self):
        body = upload_body({'title':'A History Episode'},'Description',['prehistory'],load_settings(prehistory=True))
        self.assertEqual(body['snippet']['categoryId'],'27')
        self.assertEqual(body['snippet']['defaultAudioLanguage'],'en')
        self.assertIs(body['status']['selfDeclaredMadeForKids'],False)
        self.assertIs(body['paidProductPlacementDetails']['hasPaidProductPlacement'],False)
        self.assertTrue(load_settings()['made_for_kids'])
