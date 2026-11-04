from pathlib import Path
import subprocess
import tempfile
import unittest
from chorus_arrangement import selective_plan, assemble, reference_sections, REFRAIN

VERSES=['नन्हे बच्चे बाग में गाएं\nतितली संग हम नाच दिखाएं',
        'बादल आए पानी लाएं\nनाव चलाकर खुश हो जाएं']

class ChorusArrangementTests(unittest.TestCase):
    def test_intro_once_and_separate_refrain_between_new_verses(self):
        plan=selective_plan(VERSES,'one')
        self.assertEqual(plan['sequence'],['intro','verse-1','refrain','verse-2','refrain'])
        self.assertEqual(plan['reference_windows'],{'intro':[0,19],'refrain':[19,30]})
        self.assertEqual(len(plan['requests']),2)
        self.assertEqual(plan['retained_seconds']['verse-1'],10)
        for request in plan['requests'].values():
            self.assertFalse(request['reference_cover'])
            self.assertNotIn(REFRAIN,request['lyrics'])
        other=selective_plan(VERSES,'two')
        self.assertNotEqual(plan['requests']['verse-1']['generation_seed'],other['requests']['verse-1']['generation_seed'])

    def test_duplicate_verses_and_impossible_reference_lengths_rejected(self):
        with self.assertRaises(ValueError):
            selective_plan([VERSES[0],VERSES[0]],'one')
        for seconds in (19,60,float('nan')):
            with self.assertRaises(ValueError):
                selective_plan(VERSES,'one',seconds)

    def test_real_extraction_and_crossfade_produce_one_minute(self):
        from pipeline import duration
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);reference=root/'reference.wav'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=220:duration=19',
                '-f','lavfi','-i','sine=frequency=440:duration=11','-filter_complex',
                '[0:a][1:a]concat=n=2:v=0:a=1[out]','-map','[out]','-y',str(reference)],check=True)
            plan=selective_plan(VERSES,'one')
            paths=reference_sections(reference,plan,root/'sections')
            self.assertAlmostEqual(duration(paths['intro']),19,places=2)
            self.assertAlmostEqual(duration(paths['refrain']),11,places=2)
            self.assertNotEqual(paths['intro'].read_bytes(),paths['refrain'].read_bytes())
            for i,key in enumerate(plan['requests']):
                paths[key]=root/(key+'.wav')
                subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',
                    f'sine=frequency={550+i*110}:duration=12','-y',str(paths[key])],check=True)
            target=root/'joined.wav';assemble(plan,paths,target)
            self.assertAlmostEqual(duration(target),60,places=2)
            paths['refrain']=paths['intro']
            with self.assertRaisesRegex(ValueError,'separate'):
                assemble(plan,paths,target)
