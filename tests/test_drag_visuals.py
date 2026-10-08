"""Drag-only visual overrides and optional skin metadata."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from main import BehaviorState, CharacterWindow
from skin import Skin


class DragVisualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.skin = Skin.load()

    def setUp(self):
        self.window = CharacterWindow(self.skin)
        self.window._activity.timer.stop()
        self.window._proximity.timer.stop()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def press(self):
        QTest.mousePress(self.window, Qt.LeftButton, pos=QPoint(72, 80))

    def release(self):
        QTest.mouseRelease(self.window, Qt.LeftButton, pos=QPoint(72, 80))
        if self.window._falling:
            with patch('main.time.monotonic', return_value=self.window._fall_last_tick + 10):
                self.window._fall_step()
        if self.window._rebounding:
            self.window._finish_rebound()
        if self.window._landing:
            self.window._landing_timer.timeout.emit()

    def test_direction_thresholds_and_original_origin(self):
        w = self.window
        self.press()
        origin = QPoint(w._drag_origin)
        for dx, dy, mode in ((5, -5, None), (39, 0, None), (0, -39, None),
                             (0, -40, 'grabbed'), (-40, 0, 'cry'), (40, 0, 'cry'),
                             (60, -80, 'grabbed'), (40, -40, 'grabbed'),
                             (81, -80, 'grabbed'), (-200, -40, 'grabbed'),
                             (200, -41, 'grabbed'), (200, -39, 'cry'),
                             (200, -80, None), (0, -80, 'grabbed'),
                             (0, -39, None), (0, 80, None), (40, 40, None),
                             (0, 0, None)):
            with self.subTest(dx=dx, dy=dy):
                w._select_drag_visual(origin + QPoint(dx, dy))
                self.assertEqual(w._drag_visual, mode)
                self.assertEqual(w._drag_origin, origin)
        self.release()

    def test_mode_changes_only_repaint_and_never_reload(self):
        w = self.window
        self.press()
        with patch.object(w, 'update') as repaint, \
                patch('skin.QImage', side_effect=AssertionError('No image decoding')), \
                patch('skin.prepare_image', side_effect=AssertionError('No image preparation')):
            for _ in range(100):
                w._select_drag_visual(w._drag_origin + QPoint(0, -80))
                w._animation_changed()
            self.assertEqual(repaint.call_count, 1)
            w._select_drag_visual(w._drag_origin + QPoint(100, 0))
            self.assertEqual(repaint.call_count, 2)
        self.release()
        self.assertIsNone(w._drag_visual)
        self.assertIsNone(w._drag_origin)
        self.press()
        w._select_drag_visual(w._drag_origin + QPoint(200, -80))
        self.assertIsNone(w._drag_visual)  # Release does not retain grabbed mode.
        self.release()

    def test_underlying_state_deadline_and_release_restoration(self):
        w = self.window
        for state in BehaviorState:
            with self.subTest(state=state):
                w._enter_state(state)
                timer_id = w._state_timer.timerId()
                key = w._animation.key
                self.press()
                w._select_drag_visual(w._drag_origin + QPoint(0, -80))
                self.assertEqual(w._drag_visual, 'grabbed')
                self.assertEqual(w.state, state)
                self.assertEqual(w._animation.key, key)
                if state in (BehaviorState.SLEEP, BehaviorState.WORK, BehaviorState.REACT):
                    self.assertEqual(w._state_timer.timerId(), timer_id)
                self.release()
                self.assertIsNone(w._drag_visual)
                expected = state  # A lifted drop restores the paused lifecycle after landing.
                self.assertEqual(w.state, expected)
                self.assertEqual(w._animation.key, key)

    def test_deferred_expiry_clears_override_and_restores_resulting_state(self):
        w = self.window
        for state in (BehaviorState.SLEEP, BehaviorState.WORK, BehaviorState.REACT):
            w._enter_state(state)
            self.press()
            w._select_drag_visual(w._drag_origin + QPoint(90, 0))
            w._advance_state()
            self.assertEqual(w.state, state)
            self.release()
            self.assertIsNone(w._drag_visual)
            self.assertEqual(w.state, BehaviorState.IDLE)
            self.assertEqual(w._animation.key, 'IDLE')

    def test_right_click_has_no_drag_override(self):
        QTest.mouseClick(self.window, Qt.RightButton, pos=QPoint(72, 80))
        self.assertIsNone(self.window._drag_origin)
        self.assertIsNone(self.window._drag_visual)
        self.assertIsNone(self.window._drag_offset)

    def test_optional_visuals_and_independent_scaling(self):
        source = Path(__file__).resolve().parents[1] / 'Asset/Template'
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / 'template'
            shutil.copytree(source, folder, ignore=shutil.ignore_patterns('.runtime'))
            path = folder / 'skin.json'
            manifest = json.loads(path.read_text())
            with_visuals = Skin.load('template', root=Path(temporary))
            manifest.pop('drag_visuals')
            path.write_text(json.dumps(manifest))
            without = Skin.load('template', root=Path(temporary))
            self.assertEqual(without.drag_visuals, {})
            for key, animation in without.animations.items():
                for a, b in zip(animation.frames, with_visuals.animations[key].frames):
                    self.assertEqual(a.toImage(), b.toImage())
            for animation in with_visuals.drag_visuals.values():
                self.assertEqual(len(animation.frames), 2)
                for frame in animation.frames:
                    self.assertFalse(frame.isNull())
                    self.assertTrue(frame.hasAlphaChannel())
                    self.assertLessEqual(frame.width(), 128)
                    self.assertLessEqual(frame.height(), 128)
            self.window.skin = without
            self.press()
            self.window._select_drag_visual(self.window._drag_origin + QPoint(0, -80))
            self.assertIsNone(self.window._drag_visual)
            self.release()

    def test_drag_animation_steps_loops_and_stops_on_release(self):
        w = self.window
        self.press()
        w._select_drag_visual(w._drag_origin + QPoint(0, -80))
        self.assertEqual(w._drag_frame_index, 0)
        self.assertTrue(w._drag_animation_timer.isActive())
        self.assertEqual(w._drag_animation_timer.interval(), 700)
        timer_id = w._drag_animation_timer.timerId()
        w._drag_animation_timer.timeout.emit()
        self.assertEqual(w._drag_frame_index, 1)
        w._select_drag_visual(w._drag_origin + QPoint(200, -80))
        self.assertEqual(w._drag_visual, 'grabbed')
        self.assertEqual(w._drag_frame_index, 1)  # Mouse moves do not restart playback.
        self.assertEqual(w._drag_animation_timer.timerId(), timer_id)
        w._drag_animation_timer.timeout.emit()
        self.assertEqual(w._drag_frame_index, 0)
        w._select_drag_visual(w._drag_origin + QPoint(100, 0))
        self.assertEqual(w._drag_visual, 'cry')
        self.assertEqual(w._drag_frame_index, 0)
        self.assertTrue(w._drag_animation_timer.isActive())
        self.release()
        self.assertFalse(w._drag_animation_timer.isActive())
        self.assertIsNone(w._drag_visual)
        w._advance_drag_frame()  # A stale timeout after release is harmless.
        self.assertEqual(w._drag_frame_index, 0)

    def test_legacy_and_single_frame_drag_loading_stays_static(self):
        source = Path(__file__).resolve().parents[1] / 'Asset/Template'
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / 'template'
            shutil.copytree(source, folder, ignore=shutil.ignore_patterns('.runtime'))
            path = folder / 'skin.json'
            manifest = json.loads(path.read_text())
            manifest['drag_visuals'] = {
                'grabbed': 'drag/grabbed_01.png',
                'cry': {'frames': ['drag/cry_01.png'], 'frame_duration_ms': 500}}
            path.write_text(json.dumps(manifest))
            skin = Skin.load('template', root=Path(temporary))
            self.window.skin = skin
            self.press()
            for point, mode in ((QPoint(0, -80), 'grabbed'), (QPoint(100, 0), 'cry')):
                self.window._select_drag_visual(self.window._drag_origin + point)
                self.assertEqual(self.window._drag_visual, mode)
                self.assertEqual(len(skin.drag_visuals[mode].frames), 1)
                self.assertFalse(self.window._drag_animation_timer.isActive())
            self.release()
