import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from chorus_arrangement import selective_plan, assemble, REFRAIN, PART_SECONDS

VERSES=['नन्हे बच्चे बाग में गाएं\nतितली संग हम नाच दिखाएं',
        'बादल आए पानी लाएं\nनाव चलाकर खुश हो जाएं']

class ChorusArrangementTests(unittest.TestCase):
    def test_only_chorus_uses_melody_cover_and_one_chorus_is_reused(self):
        plan=selective_plan(VERSES,'one')
        self.assertEqual(plan['sequence'].count('chorus'),2)
        self.assertEqual(len(plan['requests']),3)
        self.assertTrue(plan['requests']['chorus']['reference_cover'])
        for name in ('verse-1','verse-2'):
            self.assertFalse(plan['requests'][name]['reference_cover'])
            self.assertNotIn(REFRAIN,plan['requests'][name]['lyrics'])
        other=selective_plan(VERSES,'two')
        self.assertEqual(plan['requests']['chorus'],other['requests']['chorus'])
        self.assertNotEqual(plan['requests']['verse-1']['generation_seed'],other['requests']['verse-1']['generation_seed'])

    def test_duplicate_verses_rejected(self):
        with self.assertRaises(ValueError):
            selective_plan([VERSES[0],VERSES[0]],'one')

    def test_crossfade_output_is_exactly_one_minute_without_padding(self):
        from pipeline import duration
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);paths={}
            plan=selective_plan(VERSES,'one')
            for i,key in enumerate(plan['requests']):
                paths[key]=root/(key+'.wav')
                subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',
                    f'sine=frequency={220+i*110}:duration=16','-y',str(paths[key])],check=True)
            target=root/'joined.wav'
            assemble(plan,paths,target)
            self.assertAlmostEqual(duration(target),60,places=2)
