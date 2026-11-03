import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from PIL import Image, ImageDraw
from character_motion import prepare_layers, cached_clip, render_clip, deform, InvalidForegroundMask


class CharacterMotionTests(unittest.TestCase):
    def test_layers_preserve_art_and_invalidate_changed_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            source=root/'source.png'
            image=Image.new('RGB',(80,60),'blue')
            ImageDraw.Draw(image).rectangle((25,10,55,50),fill='red')
            image.save(source)
            mask=Image.new('L',image.size)
            ImageDraw.Draw(mask).rectangle((25,10,55,50),fill=255)
            folder=root/'layers'
            extract=lambda im:mask
            with patch('character_motion.mask_for',side_effect=AssertionError('unexpected model')):
                first=prepare_layers(source,folder,extract,lambda im,m:Image.new('RGB',im.size,'blue'))
                fg=Image.open(folder/'foreground.png')
                self.assertEqual(fg.getpixel((30,20)),(255,0,0,255))
                self.assertEqual(fg.getpixel((0,0))[3],0)
                prepare_layers(source,folder,lambda im:self.fail('cache missed'),lambda im,m:self.fail('cache missed'))
                Image.new('RGB',(80,60),'green').save(source)
                changed=prepare_layers(source,folder,extract,lambda im,m:im)
                self.assertNotEqual(first['identity'],changed['identity'])
                (folder/'background.png').write_bytes(b'broken')
                prepare_layers(source,folder,extract,lambda im,m:im)
                Image.open(folder/'background.png').verify()

    def test_bad_mask_fails_instead_of_reusing_static_scene(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            source=root/'source.png'
            Image.new('RGB',(50,50),'white').save(source)
            for value in (0,255):
                with self.assertRaisesRegex(ValueError,'Invalid foreground'):
                    prepare_layers(source,root/'layers',lambda im:Image.new('L',im.size,value),lambda im,m:im)

    @unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg required')
    def test_rejected_extraction_renders_verified_camera_motion(self):
        for dimensions, coverage in (((160,90),.013),((90,160),.020)):
            with self.subTest(dimensions=dimensions), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                source=root/'source.png'
                image=Image.new('RGB',dimensions,'blue')
                ImageDraw.Draw(image).rectangle((30,20,60,60),fill='red')
                image.save(source)
                target=root/'motion'/'clip.mp4'
                reason=f'Character extraction needs review: foreground coverage {coverage:.3f}'
                with patch('character_motion.prepare_layers',side_effect=InvalidForegroundMask(reason)):
                    render_clip(source,target,*dimensions,0,'wide shot')
                saved=json.loads(target.with_suffix('.json').read_text())
                self.assertEqual(saved['motion_mode'],'camera')
                self.assertEqual(saved['fallback_reason'],reason)
                self.assertTrue(cached_clip(source,target,*dimensions,0,'wide shot'))
                frames=[]
                for at in (0,4):
                    frames.append(subprocess.check_output(['ffmpeg','-v','error','-ss',str(at),
                        '-i',str(target),'-frames:v','1','-pix_fmt','rgb24','-f','rawvideo','pipe:1']))
                self.assertNotEqual(frames[0],frames[1])
                target.write_bytes(b'corrupt')
                self.assertFalse(cached_clip(source,target,*dimensions,0,'wide shot'))

    def test_failed_fallback_encoding_is_not_cached(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            source=root/'source.png'
            Image.new('RGB',(80,60),'blue').save(source)
            target=root/'clip.mp4'
            with patch('character_motion.prepare_layers',side_effect=InvalidForegroundMask('empty')), \
                 patch('character_motion.subprocess.run',side_effect=subprocess.CalledProcessError(1,'ffmpeg')):
                with self.assertRaises(subprocess.CalledProcessError):
                    render_clip(source,target,80,60)
            self.assertFalse(target.exists())
            self.assertFalse(target.with_suffix('.json').exists())
            self.assertFalse(cached_clip(source,target,80,60,0,''))

    def test_unrelated_errors_still_fail(self):
        with patch('character_motion.prepare_layers',side_effect=ValueError('wrong dimensions')):
            with self.assertRaisesRegex(ValueError,'wrong dimensions'):
                render_clip(Path('source.png'),Path('clip.mp4'))

    @unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg required')
    def test_actual_foreground_motion_and_cache_integrity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            source=root/'source.png'
            image=Image.new('RGB',(160,90),'blue')
            ImageDraw.Draw(image).rectangle((55,20,95,80),fill='red')
            image.save(source)
            mask=Image.new('L',image.size)
            ImageDraw.Draw(mask).rectangle((55,20,95,80),fill=255)
            layers=root/'characters'/'source'
            prepare_layers(source,layers,lambda im:mask,lambda im,m:Image.new('RGB',im.size,'blue'))
            target=root/'clip.mp4'
            render_clip(source,target,160,90,0,'rabbit hopping')
            self.assertTrue(cached_clip(source,target,160,90,0,'rabbit hopping'))
            self.assertFalse(cached_clip(source,target,160,90,0,'new narration scene'))
            frames=[]
            for at in (0,1.2):
                raw=subprocess.check_output(['ffmpeg','-v','error','-ss',str(at),'-i',str(target),'-frames:v','1',
                    '-pix_fmt','rgb24','-f','rawvideo','pipe:1'])
                frames.append(np.frombuffer(raw,dtype=np.uint8).reshape(90,160,3).astype(float))
            self.assertGreater(np.abs(frames[0]-frames[1]).mean(),2)
            self.assertLess(np.abs(frames[0][0:10]-frames[1][0:10]).mean(),2)
            target.write_bytes(b'corrupted')
            self.assertFalse(cached_clip(source,target,160,90,0,'rabbit hopping'))
