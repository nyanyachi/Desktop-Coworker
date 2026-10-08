"""Short-lived falling uses one monitor and existing deferred state semantics."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from main import BehaviorState, CharacterWindow
from skin import Skin


class GravityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.skin = Skin.load()

    def setUp(self):
        self.w = CharacterWindow(self.skin)
        self.w._activity.timer.stop()
        self.w._proximity.timer.stop()
        self.area = QRect(-1600, -900, 1200, 800)
        self.screen = SimpleNamespace(availableGeometry=lambda: self.area)
        self.w._current_screen = self.screen
        self.screens = patch('main.QApplication.screens', return_value=[self.screen])
        self.primary = patch('main.QApplication.primaryScreen', return_value=self.screen)
        self.at = patch('main.QApplication.screenAt', return_value=self.screen)
        for p in (self.screens, self.primary, self.at):
            p.start()
            self.addCleanup(p.stop)
        self.w.move(self.area.left() + 200, self.area.top() + 200)

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()
        self.app.processEvents()

    def drop(self, delta=QPoint(0, -80)):
        QTest.mousePress(self.w, Qt.LeftButton, pos=QPoint(72, 80))
        self.w._select_drag_visual(self.w._drag_origin + delta)
        self.w.move(self.w.pos() + delta)
        QTest.mouseRelease(self.w, Qt.LeftButton, pos=QPoint(72, 80))

    def tick(self, seconds):
        with patch('main.time.monotonic', return_value=self.w._fall_last_tick + seconds):
            self.w._fall_step()
        if self.w._rebounding:
            self.w._finish_rebound()
        if self.w._landing:
            self.w._landing_timer.timeout.emit()

    def test_only_grabbed_release_falls_and_keeps_animation(self):
        self.assertFalse(self.w._fall_timer.isActive())
        for delta in (QPoint(5, -5), QPoint(100, 0)):
            self.drop(delta)
            self.assertFalse(self.w._falling)
            self.assertFalse(self.w._fall_timer.isActive())
            self.assertIsNone(self.w._drag_visual)
        self.drop()
        self.assertTrue(self.w._falling)
        self.assertTrue(self.w._fall_timer.isActive())
        self.assertEqual(self.w._fall_timer.interval(), 16)
        self.assertEqual(self.w._drag_visual, 'grabbed')
        self.assertEqual(self.w._drag_animation_timer.interval(), 700)
        self.assertTrue(self.w._drag_animation_timer.isActive())
        self.assertEqual(self.w._fall_velocity, 0)
        self.assertIsNone(self.w._drag_offset)

    def test_acceleration_speed_cap_and_no_upward_motion(self):
        self.area = QRect(-1600, -900, 1200, 20000)
        self.drop()
        previous_y, previous_speed = self.w.y(), 0
        for dt in (0.01, 0.05, 0.1, 0.5, 1.0):
            self.tick(dt)
            self.assertGreaterEqual(self.w.y(), previous_y)
            self.assertGreater(self.w._fall_velocity, previous_speed)
            self.assertLessEqual(self.w._fall_velocity, 1200)
            previous_y, previous_speed = self.w.y(), self.w._fall_velocity
        self.assertEqual(self.w._fall_velocity, 1200)

    def test_negative_monitor_floor_overshoot_and_x_clamp(self):
        self.drop()
        self.w.move(self.area.left() - 100, self.w.y())
        with patch('main.QApplication.screenAt', side_effect=AssertionError('No target switching')):
            self.tick(10)
        self.assertEqual(self.w.pos(), QPoint(self.area.left(), self.area.bottom() - self.w.height() + 1))
        self.assertTrue(self.area.contains(self.w.geometry()))
        self.assertIs(self.w._current_screen, self.screen)
        self.assertFalse(self.w._falling)
        self.assertFalse(self.w._fall_timer.isActive())
        self.assertIsNone(self.w._drag_visual)
        self.assertFalse(self.w._drag_animation_timer.isActive())
        self.assertEqual(self.w.state, BehaviorState.IDLE)
        self.w._fall_step()  # Stale timer callbacks are harmless.

    def test_x_preserved_and_release_monitor_used_not_monitor_below(self):
        target_area = QRect(-800, -1600, 700, 900)
        target = SimpleNamespace(availableGeometry=lambda: target_area)
        below = SimpleNamespace(availableGeometry=lambda: QRect(-800, -700, 700, 900))
        self.w.move(target_area.left() + 100, target_area.top() + 300)
        with patch('main.QApplication.screens', return_value=[self.screen, target, below]), \
                patch('main.QApplication.screenAt', return_value=target):
            self.drop()
            x = self.w.x()
            self.assertTrue(self.w._falling)
            self.assertIs(self.w._current_screen, target)
            with patch('main.QApplication.screenAt', side_effect=AssertionError('Fall stays on release monitor')):
                self.tick(10)
            self.assertEqual(self.w.x(), x)
            self.assertEqual(self.w.y(), target_area.bottom() - self.w.height() + 1)
            self.assertIs(self.w._current_screen, target)

    def test_already_on_floor_and_short_fall(self):
        floor = self.area.bottom() - self.w.height() + 1
        self.w.move(self.w.x(), floor)
        self.w._set_drag_visual('grabbed')
        self.w._start_fall()
        self.assertFalse(self.w._falling)
        self.assertTrue(self.w._rebounding)
        self.assertIsNone(self.w._drag_visual)
        self.w._finish_rebound()
        self.w._landing_timer.timeout.emit()
        self.w.move(self.w.x(), floor - 1)
        self.w._set_drag_visual('grabbed')
        self.w._start_fall()
        self.tick(0.1)
        self.assertEqual(self.w.y(), floor)
        self.assertFalse(self.w._falling)

    def test_monitor_removed_falls_back_to_primary(self):
        self.drop()
        self.w._current_screen = object()
        self.tick(10)
        self.assertIs(self.w._current_screen, self.screen)
        self.assertEqual(self.w.y(), self.area.bottom() - self.w.height() + 1)

    def test_state_deadlines_preserved_and_expiry_deferred(self):
        for state in (BehaviorState.SLEEP, BehaviorState.WORK, BehaviorState.REACT):
            for expires in (False, True):
                with self.subTest(state=state, expires=expires):
                    self.w._enter_state(state)
                    timer_id = self.w._state_timer.timerId()
                    self.w.move(self.area.left() + 200, self.area.top() + 200)
                    self.drop()
                    self.assertEqual(self.w.state, state)
                    self.assertEqual(self.w._state_timer.timerId(), timer_id)
                    self.w._activity.is_eligible = True
                    self.w._maybe_work()
                    self.w._proximity_entered()
                    self.assertEqual(self.w.state, state)
                    if expires:
                        self.w._advance_state()
                        self.assertEqual(self.w.state, state)
                    self.tick(10)
                    expected = BehaviorState.IDLE if expires else state
                    self.assertEqual(self.w.state, expected)
                    self.assertEqual(self.w._animation.key, expected.name)
                    if not expires:
                        self.assertEqual(self.w._state_timer.timerId(), timer_id)
                    self.w._activity.is_eligible = False

    def test_awake_deadline_and_walk_wait_for_landing(self):
        self.w._enter_state(BehaviorState.WALK)
        self.drop()
        self.assertFalse(self.w._movement_timer.isActive())
        original = self.w.pos()
        self.w._walk_step()
        self.w._sleep_due()
        self.assertEqual(self.w.pos(), original)
        self.assertEqual(self.w.state, BehaviorState.WALK)
        self.tick(10)
        self.assertEqual(self.w.state, BehaviorState.SLEEP)

    def test_regrabbing_cancels_fall_without_stale_motion(self):
        self.drop()
        self.tick(0.1)
        position = self.w.pos()
        QTest.mousePress(self.w, Qt.LeftButton, pos=QPoint(72, 80))
        self.assertFalse(self.w._falling)
        self.assertFalse(self.w._fall_timer.isActive())
        self.assertIsNotNone(self.w._drag_offset)
        self.assertIsNone(self.w._drag_visual)
        self.w._fall_step()
        self.assertEqual(self.w.pos(), position)
        QTest.mouseRelease(self.w, Qt.LeftButton, pos=QPoint(72, 80))
        self.assertFalse(self.w._falling)

    def test_activity_and_proximity_cannot_interrupt_idle_fall(self):
        self.drop()
        self.w._activity.is_eligible = True
        self.w._maybe_work()
        self.w._proximity_entered()
        self.assertEqual(self.w.state, BehaviorState.IDLE)
        self.assertFalse(self.w._react_pending)
        self.w._sleep_due()
        self.w._advance_state()
        self.assertEqual(self.w.state, BehaviorState.IDLE)
        self.assertEqual(self.w._drag_visual, 'grabbed')
        self.tick(10)
        self.assertEqual(self.w.state, BehaviorState.SLEEP)
