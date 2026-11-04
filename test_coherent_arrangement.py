from pathlib import Path
import tempfile
import unittest
from coherent_arrangement import protect_fixed_sections,write_pcm,read_pcm,RATE,VERSE_WINDOWS

class FixedSectionsTests(unittest.TestCase):
    def test_intro_and_refrains_are_unchanged_while_both_verse_windows_change(self):
        import array
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            old=array.array('h',[100]*(60*RATE*2)).tobytes()
            new=array.array('h',[900]*(60*RATE*2)).tobytes()
            write_pcm(root/'source.wav',old);write_pcm(root/'edited.wav',new)
            protect_fixed_sections(root/'source.wav',root/'edited.wav',root/'result.wav')
            result=read_pcm(root/'result.wav')
            for start,end in ((0,19),(28.5,39.5),(49,60)):
                a,b=int(start*RATE)*4,int(end*RATE)*4
                self.assertEqual(result[a:b],old[a:b])
            for start,end in VERSE_WINDOWS:
                a,b=int((start+.2)*RATE)*4,int((end-.2)*RATE)*4
                self.assertEqual(result[a:b],new[a:b])
            self.assertEqual(len(result),len(old))

    def test_repaint_uses_source_context_and_explicit_mask(self):
        from music_cpu import repaint_options
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.wav'
            write_pcm(source,b'\x00'*(60*RATE*4))
            song=dict(reference_repaint=True,edit_source=str(source),duration=60,edit_start=19,edit_end=49)
            options=repaint_options(song)
            self.assertEqual(options['task_type'],'repaint')
            self.assertEqual(options['src_audio'],str(source))
            self.assertEqual(options['chunk_mask_mode'],'explicit')
            self.assertEqual((options['repainting_start'],options['repainting_end']),(19,49))
            with self.assertRaises(ValueError):
                repaint_options(dict(song,edit_end=61))
