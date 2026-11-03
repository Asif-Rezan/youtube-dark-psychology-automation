import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from PIL import Image
import shorts


class ShortsTests(unittest.TestCase):
    def test_clip_boundaries_preserve_complete_lyric_refrain_pairs(self):
        for start, seconds in ((0, 40), (10, 20), (100, 50)):
            shorts.validate_clip(start, seconds)
        for start, seconds in ((-10, 40), (5, 40), (0, 60), (0, 0), (0, 40.0)):
            with self.assertRaises(ValueError):
                shorts.validate_clip(start, seconds)

    def test_metadata_uses_existing_song_without_new_generation(self):
        song = {'title':'A' * 100, 'tags':['kids rhymes']}
        meta = shorts.short_metadata(song, 20, 40)
        self.assertLessEqual(len(meta['title']), 100)
        from upload_metadata import fixed_metadata
        self.assertEqual(meta['title'],'Dudi dudi dum dum 🍼😻#shorts #shortsfeed #dudidudidam')
        self.assertEqual(meta['description'],fixed_metadata()['description'])
        self.assertEqual(meta['tags'], [])
        self.assertEqual(meta['clip_start'], 20)

    def test_rejects_missing_audio_and_out_of_range_before_encoding(self):
        with tempfile.TemporaryDirectory() as tmp, patch('shorts.probe') as probe, patch('shorts.subprocess.run') as encode:
            probe.return_value = {'format':{'duration':'40'},'streams':[{'codec_type':'video'}]}
            for start in (0, 590):
                with self.assertRaises(ValueError):
                    shorts.render_short(Path(tmp), Path(tmp)/'short', start, 40)
            encode.assert_not_called()

    def test_render_cache_checks_source_and_output_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp)/'source', Path(tmp)/'short'
            source.mkdir(); target.mkdir()
            audio=source/'short-audio/clip-0-40/song.wav'
            audio.parent.mkdir(parents=True)
            audio.write_bytes(b'source')
            (source/'video.mp4').write_bytes(b'source')
            (target/'video.mp4').write_bytes(b'encoded')
            (source/'song.json').write_text(json.dumps({'scenes':[{'index':i,'prompt':f'Character {i}'} for i in range(8)]}))
            portrait = source/'portrait'
            portrait.mkdir()
            for i in range(8):
                Image.new('RGB',(72,128),'pink').save(portrait/f'scene-{i:03d}-source.png')
            images = {p.name:shorts.digest(p) for p in portrait.glob('*.png')}
            from character_motion import VERSION as character_version
            plan = dict(version=shorts.VERSION, character_version=character_version, portrait_images=images, source_sha256=shorts.digest(audio),
                        start=0, seconds=40, width=1080, height=1920)
            shorts.atomic_json(target/'render.json',dict(plan=plan, output_sha256=shorts.digest(target/'video.mp4')))
            info = {'format':{'duration':'40'},'streams':[{'codec_type':'audio'}]}
            with patch('shorts.probe',return_value=info), patch('shorts.verify_video') as verify, patch('shorts.subprocess.run') as encode, patch('motion_video.render_scenes', return_value=Path(tmp)/'clips.txt'):
                self.assertEqual(shorts.render_short(source,target),plan)
                verify.assert_called_once()
                encode.assert_not_called()
                # A modified source invalidates the cache. Simulate an encoder
                # failure: the previous complete output must remain intact.
                audio.write_bytes(b'changed')
                encode.side_effect = RuntimeError('encoder failed')
                with self.assertRaises(RuntimeError):
                    shorts.render_short(source,target)
                self.assertEqual((target/'video.mp4').read_bytes(),b'encoded')

    def test_publication_reuses_durable_identity_and_skips_thumbnail(self):
        plan = {'source_sha256':'abc','start':0,'seconds':40}
        remote = {}
        with tempfile.TemporaryDirectory() as tmp, patch('shorts.Path', wraps=Path) as paths:
            # Resolve only relative workspace paths inside this temporary tree.
            paths.side_effect = lambda value: Path(tmp)/value
            source = Path(tmp)/'output/episode'
            source.mkdir(parents=True)
            (source/'song.json').write_text(json.dumps({'title':'Tiny Turtle Garden','tags':[]}))
            with patch('shorts.render_short', return_value=plan), patch('storage.Store') as store, patch('pipeline.youtube_client'), patch('pipeline.publish') as publish:
                store.return_value.load.side_effect = lambda key, default: copy.deepcopy(remote.get(key, default))
                store.return_value.save.side_effect = lambda key, state: remote.update({key:copy.deepcopy(state)})
                def uploaded(client, root, metadata, state, save, upload_thumbnail=True, metadata_kind="video"):
                    self.assertFalse(upload_thumbnail)
                    self.assertEqual(metadata_kind,'shorts')
                    state.update(video_id='same-video',phase='scheduled')
                    save()
                publish.side_effect = uploaded
                shorts.run('episode', publish=True)
                shorts.run('episode', publish=True)
                self.assertEqual(publish.call_args.args[3]['video_id'],'same-video')
                self.assertEqual(list(remote),['shorts/episode/music-portrait-clip-0-40/state.json'])
                # Never upload changed media under an already used identity.
                with patch('shorts.render_short',return_value=dict(plan, source_sha256='other')):
                    with self.assertRaisesRegex(ValueError,'source changed'):
                        shorts.run('episode',publish=True)
                self.assertEqual(publish.call_count,2)

    def test_existing_short_verifies_without_thumbnail_or_second_upload(self):
        from pipeline import publish
        client = Mock()
        client.videos.return_value.list.return_value.execute.return_value = {'items':[
            {'id':'existing', 'snippet':{'channelId':'channel'},
             'status':{'containsSyntheticMedia':True}}]}
        state = {'video_id':'existing', 'upload_settings':{'mode':'public'},
                 'upload_body':{'snippet':{'tags':[]}}}
        with patch('pipeline.required',return_value='channel'), patch('upload_settings.verified_phase',return_value='published'):
            publish(client, Path('/unused'), {}, state, Mock(), upload_thumbnail=False)
        self.assertEqual(state['phase'],'published')
        client.thumbnails.assert_not_called()
        client.videos.return_value.insert.assert_not_called()

    def test_tag_normalization_and_repair_use_existing_video(self):
        from upload_settings import normalized_tags, ensure_uploaded_tags
        self.assertEqual(normalized_tags(['Shorts', ' Kids  Rhymes ']),
                         normalized_tags(['shorts', 'kids rhymes']))
        state = {'video_id':'existing', 'upload_body':{'snippet':{
            'title':'A rhyme', 'categoryId':'10', 'tags':['Shorts','kids rhymes']}}}
        client, save = Mock(), Mock()
        video = {'id':'existing', 'snippet':{'tags':['shorts','kids rhymes']}}
        self.assertFalse(ensure_uploaded_tags(client,video,state,save))
        client.videos.assert_not_called()
        video['snippet']['tags'] = []
        self.assertTrue(ensure_uploaded_tags(client,video,state,save))
        self.assertEqual(client.videos.return_value.update.call_args.kwargs['body']['id'],'existing')
        self.assertTrue(ensure_uploaded_tags(client,video,state,save))
        with self.assertRaisesRegex(RuntimeError, 'tags mismatch'):
            ensure_uploaded_tags(client,video,state,save)
        self.assertEqual(client.videos.return_value.update.call_count,2)

    def test_landscape_or_missing_illustrations_cannot_fall_back_to_blur(self):
        info = {'format':{'duration':'40'}, 'streams':[{'codec_type':'audio'}]}
        with tempfile.TemporaryDirectory() as tmp, patch('shorts.probe', return_value=info):
            root=Path(tmp)
            with self.assertRaises(FileNotFoundError):
                shorts.render_short(root,root/'target')
            (root/'song.json').write_text(json.dumps({'scenes':[{'index':i,'prompt':'A dancing bunny'} for i in range(8)]}))
            (root/'portrait').mkdir()
            Image.new('RGB',(128,72),'pink').save(root/'portrait/scene-000-source.png')
            with self.assertRaisesRegex(ValueError,'native 9:16'):
                shorts.render_short(root,root/'target')
