import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
import numpy as np
from PIL import Image
from thumbnail_variety import next_design,reserve_design,prompt_for,fingerprint,similar,generate_distinct,record_thumbnail,HISTORY_KEY


class ThumbnailVarietyTests(unittest.TestCase):
    def test_five_references_rotate_without_repeat_and_retry_keeps_same_design(self):
        history=[]
        for i in range(15):
            design=next_design({'title':'Rainy puddle play'},f'run-{i}',history)
            history.append(dict(run=f'run-{i}',design=design))
            self.assertEqual(next_design({},f'run-{i}',history),design)
        refs=[row['design']['reference_index'] for row in history]
        for start in range(11):self.assertEqual(len(set(refs[start:start+5])),5)
        for field in ('layout_index','palette_index'):
            self.assertTrue(all(a['design'][field]!=b['design'][field] for a,b in zip(history,history[1:])))
        self.assertIn('umbrella',history[0]['design']['topic'])

    def test_reservation_is_durable_and_repeated_calls_do_not_advance_history(self):
        history=[]
        store=Mock()
        store.load.side_effect=lambda key,default:copy.deepcopy(history)
        store.save.side_effect=lambda key,value:history.__setitem__(slice(None),copy.deepcopy(value))
        song={'title':'Rainbow friends'}
        first=reserve_design(song,'same',store)
        self.assertEqual(reserve_design(song,'same',store),first)
        self.assertEqual(len(history),1)
        self.assertEqual(store.save.call_count,1)
        self.assertIn('rainbow',prompt_for(song,first))
        self.assertNotEqual(prompt_for(song,first),prompt_for(song,first,1))

    def test_similar_image_is_retried_with_different_layout_and_seed(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'thumb.tmp.png'
            Image.new('RGB',(64,36),'red').save(p)
            previous=fingerprint(p)
            design=next_design({'title':'Garden friends'},'new',[])
            design['prior_signatures']=[previous]
            calls=[]
            def generate(prompt,path,**kwargs):
                calls.append((prompt,kwargs['seed']))
                Image.new('RGB',(64,36),'red' if len(calls)==1 else 'blue').save(path)
            plan=dict(seed=42,width=64,height=36,steps=20)
            generate_distinct(p,plan,{'thumbnail_design':design},generate,{})
            self.assertEqual(len(calls),2)
            self.assertNotEqual(calls[0],calls[1])
            self.assertTrue((p.parent/'thumbnail-design.json').exists())
            self.assertFalse(similar(fingerprint(p),[previous]))
            store=Mock();store.load.return_value=[dict(run='new',design=design)]
            record_thumbnail(store,p.parent,'new')
            self.assertIn('signature',store.save.call_args.args[1][0])

    def test_duplicate_retry_is_bounded_and_never_leaves_rejected_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'thumb.tmp.png'
            Image.new('RGB',(64,36),'red').save(p)
            design=next_design({'title':'Party'},'new',[])
            design['prior_signatures']=[fingerprint(p)]
            def generate(prompt,path,**kwargs):Image.new('RGB',(64,36),'red').save(path)
            with self.assertRaisesRegex(RuntimeError,'three compositions'):
                generate_distinct(p,dict(seed=1,width=64,height=36,steps=20),{'thumbnail_design':design},generate,{})
            self.assertFalse(p.exists())
            self.assertFalse((p.parent/'thumbnail-design.json').exists())


    def test_similarity_history_imports_existing_drive_thumbnail(self):
        from thumbnail_variety import seed_existing
        store=Mock();store.find.return_value='existing-file'
        def download(file_id,path):Image.new('RGB',(640,360),'green').save(path)
        store.download.side_effect=download
        history=seed_existing([], [{'run':'published','video_id':'abcdefghijk'}],store)
        self.assertIn('signature',history[0])
        store.download.assert_called_once()
        self.assertEqual(len(seed_existing(history,[{'run':'published'}],store)),1)

    def test_next_layout_avoids_the_actual_retry_layout(self):
        history=[dict(run='last',design=dict(reference_index=0,layout_index=0,palette_index=0),
                      actual_layout_index=1,actual_palette_index=1)]
        design=next_design({'title':'Party'},'next',history)
        self.assertNotEqual(design['layout_index'],1)
        self.assertNotEqual(design['palette_index'],1)
