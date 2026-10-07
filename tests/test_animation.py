import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from animation import AnimationPlayer
from skin import Animation, Skin, discover_skins, VISUAL_KEYS


class AnimationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_selection_loop_cache_and_single_frame_timer(self):
        for name in discover_skins():
            skin = Skin.load(name)
            self.assertEqual(len(skin.animations['IDLE'].frames), 1)
            self.assertEqual(len(skin.animations['WALK_LEFT'].frames), 4)
            self.assertEqual(skin.animations['WALK_LEFT'].frame_duration_ms, 180)
            player = AnimationPlayer(skin)
            try:
                player.select('IDLE')
                self.assertFalse(player.timer.isActive())
                player.select('WALK_LEFT')
                self.assertEqual(player.frame_index, 0)
                self.assertTrue(player.timer.isActive())
                # Playback only accesses already-loaded objects.
                with patch.object(Skin, 'load', side_effect=AssertionError('reload')):
                    for index in (1, 2, 3, 0):
                        player._advance_frame()
                        self.assertEqual(player.frame_index, index)
                        self.assertIs(player.frame, skin.animations['WALK_LEFT'].frames[index])
                    player._advance_frame()
                    player.select('WALK_LEFT')
                    self.assertEqual(player.frame_index, 1)
                    player.select('WALK_RIGHT')
                    self.assertEqual(player.frame_index, 0)
                    player.select('IDLE')
                    self.assertEqual(player.frame_index, 0)
                    self.assertFalse(player.timer.isActive())
                # Exercise actual timeout delivery at a short test-only duration.
                animation = skin.animations['WALK_LEFT']
                skin.animations['WALK_LEFT'] = Animation(animation.frames, 30)
                player.select('WALK_LEFT')
                for _ in range(100):
                    if player.frame_index != 0:
                        break
                    QTest.qWait(5)
                self.assertEqual(player.frame_index, 1)
            finally:
                player.timer.stop()
                player.deleteLater()

    def test_animation_errors_identify_skin_and_semantic_key(self):
        definitions = {key: {'frames': ['missing.png'], 'frame_duration_ms': 400}
                       for key in VISUAL_KEYS}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = root / 'test'
            folder.mkdir()
            for definition in (None, {'frames': [], 'frame_duration_ms': 180},
                               {'frames': ['missing.png'], 'frame_duration_ms': 0},
                               {'frames': ['missing.png'], 'frame_duration_ms': True},
                               {'frames': ['missing.png'], 'frame_duration_ms': '180'},
                               {'frames': ['missing.png'], 'frame_duration_ms': 180}):
                manifest = {'id': 'test', 'display_name': 'Test',
                            'animations': dict(definitions)}
                if definition is None:
                    del manifest['animations']['IDLE']
                else:
                    manifest['animations']['IDLE'] = definition
                (folder / 'skin.json').write_text(json.dumps(manifest))
                with self.assertRaisesRegex(ValueError, "Invalid skin 'test': IDLE"):
                    Skin.load('test', root=root)
