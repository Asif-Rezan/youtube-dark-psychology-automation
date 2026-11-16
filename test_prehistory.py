import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from episode_packaging import public_metadata
from prehistory.editorial import generate, metadata
from prehistory.visuals import cover, scene
from upload_settings import load_settings, upload_body


class PrehistoryTests(unittest.TestCase):
    def test_qwen_plan_produces_distinct_story_and_measured_chapters(self):
        idea = {'topic':'stone-tools','title':'Why Did Early Humans Break Stones on Purpose?',
                'hook':'BREAK STONES?','description':'A single sharp edge changed what early people could do.',
                'angle':'Start with a stone flake','tags':['stone tools']*6}
        story = []
        for index, name in enumerate(('A Broken Stone','Making an Edge','Different Toolkit','The Evidence',
                                      'The Cut Marks','Who Made It','A Missing Clue','The Final Answer')):
            narration = ('This looks like an ordinary stone at first. Why did early toolmakers strike another stone '
                         'against it to make a sharper edge?')
            story.append({'label':name,'beats':[{'narration':narration,'action':'show','prop':'stone'}]*3})
        with patch('prehistory.editorial.ask',side_effect=[idea,{'chapters':story[:4]},{'chapters':story[4:]}]):
            plan = generate('prehistory-test',[])
        result = metadata(plan,list(range(0,240,30)))
        self.assertEqual(plan['hook'],'WHAT DID IT CUT?')
        self.assertIn('00:00 A Broken Stone\n00:30 Making an Edge',result['description'])
        self.assertIn('Smithsonian Human Origins Program',result['description'])
        self.assertEqual(public_metadata(result)['title'],idea['title'])

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
