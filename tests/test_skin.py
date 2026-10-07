import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QImage, QPainter, QColor, QPixmap
from PySide6.QtWidgets import QApplication

from main import BehaviorState, CharacterWindow
from skin import Skin, discover_skins, visible_bounds, VISUAL_KEYS


class SkinTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_discovery_loading_scaling_and_state_selection(self):
        self.assertEqual(discover_skins(), ['template'])
        self.assertEqual(Skin.load().id, 'template')
        for skin_id in discover_skins():
            skin = Skin.load(skin_id)
            self.assertEqual(skin.id, skin_id)
            self.assertEqual(skin.scale_mode, 'smooth')
            idle = skin.visual('IDLE')
            self.assertFalse(idle.isNull())
            self.assertTrue(idle.hasAlphaChannel())
            self.assertLessEqual(idle.width(), 128)
            self.assertLessEqual(idle.height(), 128)
            self.assertIs(skin.visual('WALK_LEFT'), skin.visual('WALK_RIGHT'))
            w = CharacterWindow(skin)
            w._proximity.timer.stop()
            w.show()
            self.app.processEvents()
            try:
                for state, direction, key in (
                    (BehaviorState.IDLE, 1, 'IDLE'),
                    (BehaviorState.WALK, -1, 'WALK_LEFT'),
                    (BehaviorState.WALK, 1, 'WALK_RIGHT'),
                    (BehaviorState.SLEEP, 1, 'SLEEP'),
                    (BehaviorState.WORK, 1, 'WORK'),
                    (BehaviorState.REACT, 1, 'REACT'),
                ):
                    with patch('main.random.choice', return_value=direction):
                        w._enter_state(state)
                    image = w.grab().toImage()
                    self.assertEqual(w._animation.key, key)
                    self.assertEqual(w._animation.frame_index, 0)
                    self.assertEqual(image.pixelColor(0, 0).alpha(), 0)
                    bounds = visible_bounds(image)
                    self.assertFalse(bounds.isEmpty())
                    self.assertTrue(image.rect().contains(bounds))
                    if state == BehaviorState.WALK:
                        for _ in range(4):
                            w._animation._advance_frame()
                            frame = w.grab().toImage()
                            bounds = visible_bounds(frame)
                            self.assertFalse(bounds.isEmpty())
                            self.assertTrue(image.rect().contains(bounds))
            finally:
                w.close()
                w.deleteLater()
                self.app.processEvents()

    def test_template_manifest_paths_and_shared_scale(self):
        folder = Path(__file__).resolve().parents[1] / 'Asset' / 'Template'
        manifest = json.loads((folder / 'skin.json').read_text())
        self.assertEqual(manifest['rendering']['scale_mode'], 'smooth')
        originals = {path: hashlib.sha256(path.read_bytes()).digest()
                     for path in folder.rglob('*.png') if '.runtime' not in path.parts}
        bounds = []
        def inspect(image):
            result = visible_bounds(image)
            bounds.append(result)
            return result
        with patch('skin.visible_bounds', side_effect=inspect), patch(
                'skin.prepare_image', side_effect=AssertionError('smooth must use original')):
            skin = Skin.load('template')
        self.assertEqual(skin.scale_mode, 'smooth')
        self.assertEqual(skin.display_name, 'Template')
        self.assertEqual(len(bounds), 8)  # Shared walk paths are loaded only once.
        factor = min(128 / max(b.width() for b in bounds),
                     128 / max(b.height() for b in bounds))
        index = 0
        checked = set()
        for key in VISUAL_KEYS:
            definition = manifest['animations'][key]
            self.assertEqual(skin.animations[key].frame_duration_ms, definition['frame_duration_ms'])
            for filename, frame in zip(definition['frames'], skin.animations[key].frames):
                self.assertTrue((folder / filename).is_file())
                self.assertFalse(frame.isNull())
                if filename not in checked:
                    source = bounds[index].size()
                    target = QSize(max(1, round(source.width() * factor)),
                                   max(1, round(source.height() * factor)))
                    self.assertEqual(frame.size(), source.scaled(target, Qt.KeepAspectRatio))
                    checked.add(filename)
                    index += 1
        self.assertEqual(len(skin.animations['WALK_LEFT'].frames), 4)
        for left, right in zip(skin.animations['WALK_LEFT'].frames,
                               skin.animations['WALK_RIGHT'].frames):
            self.assertIs(left, right)
        self.assertEqual(originals, {path: hashlib.sha256(path.read_bytes()).digest()
                                     for path in originals})
        window = CharacterWindow(skin)
        window._proximity.timer.stop()
        try:
            for key in VISUAL_KEYS:
                window._animation.select(key)
                for frame in skin.animations[key].frames:
                    self.assertIs(window._animation.frame, frame)
                    rendered = visible_bounds(window.grab().toImage())
                    # Smooth filtering can round a faint outer alpha pixel to zero.
                    expected = QImage(144, 160, QImage.Format.Format_ARGB32_Premultiplied)
                    expected.fill(Qt.transparent)
                    painter = QPainter(expected)
                    painter.drawPixmap((144 - frame.width()) // 2,
                                       160 - 8 - frame.height(), frame)
                    painter.end()
                    self.assertEqual(rendered, visible_bounds(expected))
                    window._animation._advance_frame()
        finally:
            window.close()
            window.deleteLater()

    def test_smooth_scales_original_directly_and_default_is_pixel(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = root / 'test'
            folder.mkdir()
            image = QImage(603, 405, QImage.Format.Format_ARGB32)
            image.fill(Qt.transparent)
            painter = QPainter(image)
            for x in range(11, 590):
                painter.fillRect(x, 13, 1, 379, QColor('black' if x % 2 else 'white'))
            painter.end()
            image.save(str(folder / 'frame.png'))
            manifest = {'id': 'test', 'display_name': 'Test',
                        'visuals': {key: 'frame.png' for key in VISUAL_KEYS}}
            path = folder / 'skin.json'
            path.write_text(json.dumps(manifest))
            default = Skin.load('test', root=root)
            self.assertEqual(default.scale_mode, 'pixel')
            manifest['rendering'] = {'scale_mode': 'pixel'}
            path.write_text(json.dumps(manifest))
            pixel = Skin.load('test', root=root)
            self.assertEqual(pixel.scale_mode, 'pixel')
            self.assertEqual(pixel.visual('IDLE').toImage(), default.visual('IDLE').toImage())
            manifest['rendering'] = {'scale_mode': 'smooth'}
            path.write_text(json.dumps(manifest))
            with patch('skin.prepare_image', side_effect=AssertionError('preprocessing forbidden')):
                skin = Skin.load('test', root=root)
            frame = skin.visual('IDLE')
            original = QPixmap.fromImage(image.copy(visible_bounds(image)))
            expected = original.scaled(frame.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            nearest = original.scaled(frame.size(), Qt.KeepAspectRatio, Qt.FastTransformation)
            self.assertEqual(frame.toImage(), expected.toImage())
            self.assertNotEqual(frame.toImage(), nearest.toImage())
            for key in VISUAL_KEYS:
                self.assertIs(frame, skin.visual(key))
            for invalid in ({'scale_mode': 'unknown'}, None):
                manifest['rendering'] = invalid
                path.write_text(json.dumps(manifest))
                with self.assertRaisesRegex(ValueError, 'rendering'):
                    Skin.load('test', root=root)

    def test_padding_shared_scale_and_transparent_image(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = root / 'test'
            folder.mkdir()
            manifest = {'id': 'test', 'display_name': 'Test', 'visuals': {
                'IDLE': 'idle.png', 'WALK_LEFT': 'walk.png', 'WALK_RIGHT': 'walk.png',
                'SLEEP': 'idle.png', 'WORK': 'idle.png', 'REACT': 'idle.png'}}
            (folder / 'skin.json').write_text(json.dumps(manifest), encoding='utf-8')
            for name, canvas, bounds in (
                ('idle.png', QSize(80, 80), QRect(30, 45, 10, 20)),
                ('walk.png', QSize(100, 100), QRect(5, 3, 20, 40)),
            ):
                image = QImage(canvas, QImage.Format.Format_ARGB32)
                image.fill(Qt.GlobalColor.transparent)
                painter = QPainter(image)
                painter.fillRect(bounds, QColor('#123456'))
                painter.end()
                self.assertEqual(visible_bounds(image), bounds)
                image.save(str(folder / name))
            skin = Skin.load('test', root=root)
            # Both states get factor 3.2, despite unrelated canvas sizes/padding.
            self.assertEqual(skin.visual('IDLE').size(), QSize(32, 64))
            self.assertEqual(skin.visual('WALK_LEFT').size(), QSize(64, 128))
            rendered = skin.visual('IDLE').toImage()
            self.assertEqual(rendered.pixelColor(0, 0), QColor('#123456'))
            manifest['animations'] = {
                'IDLE': {'frames': ['idle.png'], 'frame_duration_ms': 400},
                'WALK_LEFT': {'frames': ['idle.png', 'walk.png'], 'frame_duration_ms': 180},
                'WALK_RIGHT': {'frames': ['idle.png', 'walk.png'], 'frame_duration_ms': 180},
                'SLEEP': {'frames': ['idle.png'], 'frame_duration_ms': 600},
                'WORK': {'frames': ['idle.png'], 'frame_duration_ms': 500},
                'REACT': {'frames': ['idle.png'], 'frame_duration_ms': 300},
            }
            del manifest['visuals']
            (folder / 'skin.json').write_text(json.dumps(manifest), encoding='utf-8')
            animated = Skin.load('test', root=root)
            self.assertEqual(animated.visual('IDLE').size(), QSize(32, 64))
            self.assertEqual(animated.animations['WALK_LEFT'].frames[1].size(), QSize(64, 128))
            empty = QImage(10, 10, QImage.Format.Format_ARGB32)
            empty.fill(Qt.GlobalColor.transparent)
            self.assertTrue(visible_bounds(empty).isEmpty())
            empty.save(str(folder / 'idle.png'))
            with self.assertRaisesRegex(ValueError, 'fully transparent'):
                Skin.load('test', root=root)

    def test_invalid_manifest_and_missing_image(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = root / 'test'
            folder.mkdir()
            manifest = folder / 'skin.json'
            for content in ('{', '{}', json.dumps({
                'id': 'test', 'display_name': 'Test',
                'visuals': {key: 'missing.png' for key in ('IDLE', 'WALK_LEFT', 'WALK_RIGHT')},
            })):
                manifest.write_text(content, encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'Invalid skin'):
                    Skin.load('test', QSize(128, 144), root)
        with self.assertRaisesRegex(ValueError, 'Unknown skin'):
            Skin.load('../invalid')

    def test_invalid_cli_is_clear_and_has_no_traceback(self):
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parents[1] / 'main.py'),
             '--skin', 'invalid'],
            cwd=tempfile.gettempdir(),
            env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
            capture_output=True, text=True, timeout=5,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn('invalid choice', result.stderr)
        for skin_id in discover_skins():
            self.assertIn(skin_id, result.stderr)
        self.assertNotIn('Traceback', result.stderr)
