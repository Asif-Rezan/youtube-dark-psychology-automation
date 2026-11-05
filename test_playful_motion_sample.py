import json
from pathlib import Path
import tempfile
import unittest
from PIL import Image
from character_motion import digest
from playful_motion_sample import verified_layers


class SampleSourceTests(unittest.TestCase):
    def test_sampler_rejects_tampered_character_layers_and_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            folder=root/'characters/scene-000-source'
            folder.mkdir(parents=True)
            source=root/'scene-000-source.png'
            Image.new('RGB',(80,60),'blue').save(source)
            Image.new('RGB',(80,60),'blue').save(folder/'background.png')
            fg=Image.new('RGBA',(80,60))
            fg.paste('red',(25,10,55,50))
            fg.save(folder/'foreground.png')
            saved={'identity':{'source_sha256':digest(source)},'foreground_fraction':.25,
                   'assets':{name:digest(folder/name) for name in ('foreground.png','background.png')}}
            (folder/'layers.json').write_text(json.dumps(saved))
            self.assertEqual(verified_layers(root),folder)
            source.write_bytes(b'changed source')
            with self.assertRaisesRegex(ValueError,'No verified'):
                verified_layers(root)
            saved['identity']['source_sha256']=digest(source)
            (folder/'layers.json').write_text(json.dumps(saved))
            (folder/'foreground.png').write_bytes(b'changed foreground')
            with self.assertRaisesRegex(ValueError,'No verified'):
                verified_layers(root)
