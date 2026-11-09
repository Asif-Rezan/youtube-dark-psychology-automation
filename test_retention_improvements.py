"""Retention changes: chorus-first 4-minute form, opening thumbnail scene, hook motion, SEO."""
import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import kids_rhymes
from kids_rhymes import song_form, tagged_lyrics, episode_lighting, CHORUS_POSES
from rhyme_writer import CHORUS, REFRAIN, verse_lines, chorus_line, hook_reason
HOOK = ['hoppy hoppy hop hop', 'clap clap clap with me', 'hoppy hoppy hop hop', 'wiggle your ears and spin']


class SongFormTests(unittest.TestCase):
    def test_default_song_is_four_minutes_and_opens_on_the_chorus(self):
        form = song_form(240)
        self.assertEqual(form[0], ('chorus', 4))
        self.assertEqual(form[-1][0], 'chorus')
        self.assertEqual(sum(n for _, n in form), 48)
        self.assertEqual(sum(n for k, n in form if k == 'verse'), 20)
        # Never two verses in a row: a chorus always follows a verse.
        for (kind, _), (following, _) in zip(form, form[1:]):
            if kind == 'verse':
                self.assertEqual(following, 'chorus')

    def test_every_allowed_length_fills_the_storyboard(self):
        for seconds in range(kids_rhymes.MIN_SECONDS, kids_rhymes.MAX_SECONDS + 1, 5):
            self.assertEqual(sum(n for _, n in song_form(seconds)), seconds // 5)

    def test_music_lyrics_carry_section_tags_and_chorus_comes_first(self):
        scenes = [dict(lyric=CHORUS[i % 4], section='chorus') for i in range(4)]
        scenes += [dict(lyric=f'little bunny hops along {i}', section='verse') for i in range(4)]
        lines = tagged_lyrics(scenes).splitlines()
        self.assertEqual(lines[0], '[Chorus - high energy]')
        self.assertEqual(lines[5], '[Verse]')
        self.assertEqual(lines.count('[Chorus - high energy]'), 1)

    def test_chorus_lines_are_not_counted_as_original_verses(self):
        song = dict(scenes=[dict(lyric=line) for line in CHORUS] + [dict(lyric='Tiny ducks paddle in a row')])
        self.assertEqual(verse_lines(song), ['tiny ducks paddle in a row'])
        self.assertTrue(chorus_line('Clap your hands and dance with me!'))

    def test_episode_hook_rules(self):
        self.assertIsNone(hook_reason(HOOK))
        self.assertEqual(hook_reason(list(CHORUS)), 'borrowed_hook')
        self.assertEqual(hook_reason(['bunny jumps so high', 'clap', 'bunny jumps so high', 'spin around now']), 'hook_word_count')
        self.assertEqual(hook_reason(['little bunny hops along', 'clap your hands now', 'little bunny hops along', 'spin around now']), 'hook_needs_repeated_sound')
        self.assertEqual(hook_reason(HOOK[:2] + ['other line here', HOOK[3]]), 'hook_must_repeat_line_one_as_line_three')
        self.assertEqual(hook_reason(HOOK, [{'hook': 'Hoppy hoppy hop hop!'}]), 'repeated_hook')

    def test_final_chorus_is_tagged_as_energetic_finish(self):
        scenes = [dict(lyric='a', section='chorus'), dict(lyric='b', section='verse'), dict(lyric='c', section='chorus')]
        self.assertEqual(tagged_lyrics(scenes).splitlines()[-2], '[Final Chorus - big energetic finish]')

    def test_episode_chorus_lines_are_not_verses(self):
        song = dict(chorus=HOOK, scenes=[dict(lyric=line) for line in HOOK] + [dict(lyric='Tiny ducks paddle')])
        self.assertEqual(verse_lines(song), ['tiny ducks paddle'])

    def test_lighting_follows_the_episode_world(self):
        self.assertEqual(episode_lighting({'visual_world': 'A moonlit meadow with fireflies'}), 'soft moonlit evening')
        self.assertEqual(episode_lighting({'visual_world': 'A sunny flower garden'}), 'bright sunny daytime')


class MakeSongTests(unittest.TestCase):
    def setUp(self):
        self.requested = {}

        def written(day, identity, seconds, history, draft_path=None, verse_count=None):
            self.requested['verse_count'] = verse_count
            return dict(writer_version='test', outline=dict(title='Bunny Finds the Moon',
                characters='A white baby bunny and a yellow duckling with two toddlers.',
                visual_world='A moonlit meadow with soft stars.',
                description='A gentle new story about friends dancing under the moon in a meadow.', chorus=HOOK,
                story_summary='Bunny and duckling dance under the moon with toddlers.'),
                sections=[[dict(lyric=f'Bunny hops to the moon {i}', visual=f'Bunny and toddlers hopping {i}')
                           for i in range(verse_count)]])
        patcher = patch('kids_rhymes.write_rhyme', side_effect=written)
        patcher.start()
        self.addCleanup(patcher.stop)
        with patch.dict(os.environ, VIDEO_DURATION_SECONDS='240'):
            self.song = kids_rhymes.make_song('2026-11-08', [], generation_id='retention')

    def test_storyboard_matches_form_and_requests_exact_verse_count(self):
        self.assertEqual(self.requested['verse_count'], 20)
        self.assertEqual(self.song['duration'], 240)
        self.assertEqual([s['section'] for s in self.song['scenes'][:5]], ['chorus'] * 4 + ['verse'])
        self.assertEqual(self.song['scenes'][0]['lyric'], HOOK[0])
        self.assertEqual(self.song['hook'], HOOK[0])
        self.assertIn('"hoppy hoppy hop hop"', self.song['prompt'])
        self.assertNotIn('dudi', self.song['prompt'].lower())
        self.assertIn('button ending', self.song['prompt'])
        self.assertIn('130 BPM', self.song['prompt'])
        self.assertEqual(self.song['song_form'], kids_rhymes.SONG_FORM)
        self.assertIn('Starts instantly', self.song['prompt'])

    def test_every_scene_shares_the_episode_lighting(self):
        for scene in self.song['scenes']:
            self.assertIn('Consistent soft moonlit evening lighting', scene['prompt'])

    def test_consecutive_chorus_scenes_use_different_dance_poses(self):
        chorus = [s['prompt'] for s in self.song['scenes'] if s['section'] == 'chorus']
        for previous, current in zip(chorus, chorus[1:]):
            self.assertNotEqual(previous, current)
        self.assertGreaterEqual(len({p for p in chorus}), len(CHORUS_POSES))

    def test_thumbnail_must_be_the_opening_scene(self):
        from episode_packaging import schema, chapter_text
        enum = schema(self.song)['properties']['thumbnail']['properties']['scene_index']['enum']
        self.assertEqual(enum, [0])
        chapters = chapter_text(self.song).splitlines()
        self.assertEqual(chapters[0], '0:00 Hoppy hoppy hop hop dance chorus')
        self.assertTrue(chapters[1].startswith('0:20 Verse 1: Bunny hops to the moon'))
        self.assertEqual(len(chapters), 6)

    def test_generated_package_gets_real_chapters_and_rejects_sound_alike_titles(self):
        from episode_packaging import generate_package
        from test_episode_packaging import fixture_package
        good = fixture_package(self.song)
        good['title_candidates'][0] = 'Dodi Dodi Dum Dum Dance | Kids Songs'
        good['video']['title'] = good['title_candidates'][0]
        with patch('rhyme_writer.request_json', return_value=copy.deepcopy(good)) as model:
            package = generate_package(self.song)
        model.assert_called_once()
        self.assertNotIn('dodi', package['video']['title'].casefold())
        self.assertIn('0:20 Verse 1:', package['video']['description'])
        self.assertLessEqual(len(package['video']['description']), 1800)

    def test_opening_clip_uses_thumbnail_artwork(self):
        from character_motion import clip_source
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(FileNotFoundError):
                clip_source(root, self.song, 0)
            (root / 'thumbnail-source.png').write_bytes(b'x')
            self.assertEqual(clip_source(root, self.song, 0).name, 'thumbnail-source.png')
            self.assertEqual(clip_source(root, self.song, 1).name, 'scene-001-source.png')
            self.assertEqual(clip_source(root, self.song, 0, portrait=True).name, 'scene-000-source.png')
            self.assertEqual(clip_source(root, {}, 0).name, 'scene-000-source.png')


class OpeningMotionTests(unittest.TestCase):
    def test_opening_scenes_cut_in_at_the_half_beat(self):
        from scene_actions import plan_scene, camera_viewport
        plan = plan_scene('Two toddlers and bunnies dancing together, clap your hands at 120 BPM', 0)
        later = plan_scene('Two toddlers and bunnies dancing together, clap your hands at 120 BPM', 10)
        self.assertTrue(plan['opening'])
        self.assertFalse(later['opening'])
        bounds = (700, 300, 1100, 900)
        before = camera_viewport((1920, 1080), bounds, plan, 2.4)
        after = camera_viewport((1920, 1080), bounds, plan, 2.6)
        # A hard punch-in: the visible width drops sharply across the cut.
        self.assertGreater((before[2] - before[0]) - (after[2] - after[0]), 150)
        calm = camera_viewport((1920, 1080), bounds, later, 2.6)
        self.assertGreater(calm[2] - calm[0], after[2] - after[0])

    def test_dance_scenes_switch_to_a_second_move(self):
        from scene_actions import plan_scene, BODY_VARIANTS
        plan = plan_scene('toddlers and kittens dancing together at 120 BPM', 7)
        self.assertIn(plan['second_variant'], BODY_VARIANTS)
        self.assertNotEqual(plan['second_variant'], plan['dance_variant'])


class MusicStepsTests(unittest.TestCase):
    def test_turbo_steps_default_and_bounds(self):
        from music_cpu import inference_steps
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('ACESTEP_INFERENCE_STEPS', None)
            self.assertEqual(inference_steps(), 8)
        with patch.dict(os.environ, ACESTEP_INFERENCE_STEPS='12'):
            self.assertEqual(inference_steps(), 12)
        with patch.dict(os.environ, ACESTEP_INFERENCE_STEPS='27'):
            with self.assertRaises(ValueError):
                inference_steps()


if __name__ == '__main__':
    unittest.main()
