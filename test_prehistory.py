import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from episode_packaging import public_metadata
from prehistory.editorial import CHAPTER_COUNT, generate, metadata, valid_chapters
from prehistory.production import FULL_RUNTIME, runtime_timing
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
        self.assertEqual(public_metadata(result)['title'],idea['title'])

    def test_runtime_uses_modest_tempo_correction_and_rejects_impossible_lengths(self):
        self.assertEqual(runtime_timing([17]*60,FULL_RUNTIME),1)
        self.assertLess(runtime_timing([14]*60,FULL_RUNTIME),1)
        self.assertGreater(runtime_timing([20]*60,FULL_RUNTIME),1)
        with self.assertRaisesRegex(RuntimeError,'natural speaking speed'):
            runtime_timing([8]*60,FULL_RUNTIME)

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
