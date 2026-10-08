"""Final-QA coverage for transition boundaries and owned resource lifetime."""

import unittest
from contextlib import ExitStack
from unittest.mock import patch

import shiboken6
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from main import BehaviorState, CharacterWindow
from skin import Skin, discover_skins


class FinalQATests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_window(self, skin_id):
        w = CharacterWindow(Skin.load(skin_id))
        w._activity.timer.stop()
        w._proximity.timer.stop()
        w._activity.is_eligible = False
        return w

    def destroy_window(self, w):
        w.close()
        w.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_screen_edge_uses_sleep_react_work_priority(self):
        for skin_id in discover_skins():
            w = self.make_window(skin_id)
            try:
                area = w.screen().availableGeometry()
                for direction in (-1, 1):
                    for expected in (BehaviorState.SLEEP, BehaviorState.REACT,
                                     BehaviorState.WORK, BehaviorState.IDLE):
                        with self.subTest(skin=skin_id, direction=direction, state=expected):
                            w._react_allowed_at = w._work_allowed_at = 0
                            w._sleep_pending = False
                            w._react_pending = False
                            w._activity.is_eligible = expected != BehaviorState.IDLE
                            with patch('main.random.choice', return_value=direction):
                                w._enter_state(BehaviorState.WALK)
                            if expected in (BehaviorState.SLEEP, BehaviorState.REACT):
                                w._proximity_entered()
                            if expected == BehaviorState.SLEEP:
                                w._sleep_due()
                            edge = area.left() if direction < 0 else area.right() - w.width() + 1
                            w.move(edge, area.top())
                            w._walk_step()
                            self.assertEqual(w.state, expected)
                            self.assertFalse(w._movement_timer.isActive())
                            self.assertTrue(area.contains(w.geometry()))
            finally:
                self.destroy_window(w)

    def test_repeated_cycles_reuse_resources_and_destruction_cleans_children(self):
        for skin_id in discover_skins():
            w = self.make_window(skin_id)
            timers = w.findChildren(QTimer)
            self.assertEqual(len(timers), 9)  # Includes drag animation and inactive fall timers.
            frame_keys = {key: tuple(frame.cacheKey() for frame in animation.frames)
                          for key, animation in w.skin.animations.items()}
            try:
                for _ in range(500):
                    w._react_allowed_at = 0
                    w._enter_state(BehaviorState.WALK)
                    w._proximity_entered()
                    w._advance_state()
                    self.assertEqual(w.state, BehaviorState.REACT)
                    w._sleep_due()
                    w._advance_state()
                    self.assertEqual(w.state, BehaviorState.SLEEP)
                    w._advance_state()
                    self.assertEqual(w.state, BehaviorState.IDLE)
                    w._enter_state(BehaviorState.WORK)
                    w._advance_state()
                    self.assertEqual(w.state, BehaviorState.IDLE)
                self.assertEqual(w.findChildren(QTimer), timers)
                self.assertEqual({key: tuple(frame.cacheKey() for frame in animation.frames)
                                  for key, animation in w.skin.animations.items()}, frame_keys)
            finally:
                self.destroy_window(w)
            self.assertTrue(all(not shiboken6.isValid(timer) for timer in timers))
            self.assertFalse(shiboken6.isValid(w._activity))
            self.assertFalse(shiboken6.isValid(w._proximity))

    def test_template_playback_drag_cycles_never_reprocess_sources(self):
        w = self.make_window('template')
        w.show()
        self.app.processEvents()
        notifications = []
        w._animation.frame_changed.connect(lambda: notifications.append(w._animation.key))
        try:
            with ExitStack() as guards:
                for name in ('skin.QImage', 'skin.visible_bounds', 'skin.prepare_image',
                             'skin.QPixmap', 'skin.Skin.load'):
                    guards.enter_context(patch(name, side_effect=AssertionError('image reprocessing')))
                for _ in range(100):
                    for state in BehaviorState:
                        w._enter_state(state)
                        self.assertEqual(w._animation.timer.isActive(), state == BehaviorState.WALK)
                        before = len(notifications)
                        w._animation.select(w._animation.key)
                        self.assertEqual(len(notifications), before)
                        QTest.mousePress(w, Qt.LeftButton, pos=QPoint(72, 80))
                        self.assertFalse(w._movement_timer.isActive())
                        w._advance_state()  # Expiry while dragging is deferred.
                        QTest.mouseRelease(w, Qt.LeftButton, pos=QPoint(72, 80))
                        self.assertEqual(w.state, BehaviorState.IDLE)
                        self.assertFalse(w._movement_timer.isActive())
                        self.assertFalse(w._animation.timer.isActive())
                    w._enter_state(BehaviorState.WALK)
                    for index in (1, 2, 3, 0):
                        w._animation._advance_frame()
                        self.assertEqual(w._animation.frame_index, index)
                        w.grab()
        finally:
            self.destroy_window(w)
