"""The landing pose is visual-only and does not reset behavior deadlines."""
import unittest
from unittest.mock import patch
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from main import BehaviorState, CharacterWindow
from skin import Skin


class LandingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.skin = Skin.load()

    def setUp(self):
        self.w = CharacterWindow(self.skin)
        self.w._activity.timer.stop()
        self.w._proximity.timer.stop()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()
        self.app.processEvents()

    def land(self):
        QTest.mousePress(self.w, Qt.LeftButton, pos=QPoint(72, 80))
        self.w._set_drag_visual('grabbed')
        self.w._drag_offset = None
        self.w._drag_origin = None
        self.w._finish_fall()
        self.w._finish_rebound()

    def test_400ms_skin_work_pose_and_no_state_reset(self):
        for state in BehaviorState:
            with self.subTest(state=state):
                self.w._enter_state(state)
                key = self.w._animation.key
                timer_id = self.w._state_timer.timerId()
                self.land()
                self.assertTrue(self.w._landing)
                self.assertFalse(self.w._fall_timer.isActive())
                self.assertIsNone(self.w._drag_visual)
                self.assertFalse(self.w._drag_animation_timer.isActive())
                self.assertTrue(self.w._landing_timer.isSingleShot())
                self.assertEqual(self.w._landing_timer.interval(), 400)
                self.assertEqual(self.w.state, state)
                if state in (BehaviorState.SLEEP, BehaviorState.WORK, BehaviorState.REACT):
                    self.assertEqual(self.w._state_timer.timerId(), timer_id)
                with patch('main.QPainter') as painter:
                    self.w.paintEvent(None)
                    self.assertIs(painter.return_value.drawPixmap.call_args.args[2],
                                  self.w.skin.visual('WORK'))
                with patch.object(self.w, '_enter_state', side_effect=AssertionError('State reset')):
                    self.w._landing_timer.timeout.emit()
                self.assertFalse(self.w._landing)
                self.assertFalse(self.w._landing_timer.isActive())
                self.assertEqual(self.w.state, state)
                self.assertEqual(self.w._animation.key, key)
                self.assertTrue(self.w._state_timer.isActive())
                self.assertEqual(self.w._movement_timer.isActive(), state == BehaviorState.WALK)

    def test_deadline_expiry_is_deferred_until_pose_ends(self):
        for state in (BehaviorState.SLEEP, BehaviorState.WORK, BehaviorState.REACT):
            self.w._enter_state(state)
            self.land()
            self.w._advance_state()
            self.assertEqual(self.w.state, state)
            self.assertTrue(self.w._landing)
            self.w._landing_timer.timeout.emit()
            self.assertEqual(self.w.state, BehaviorState.IDLE)
            self.assertFalse(self.w._landing)

    def test_activity_sleep_and_proximity_wait_for_pose(self):
        self.land()
        self.w._activity.is_eligible = True
        self.w._maybe_work()
        self.w._proximity_entered()
        self.w._sleep_due()
        self.assertEqual(self.w.state, BehaviorState.IDLE)
        self.w._landing_timer.timeout.emit()
        self.assertEqual(self.w.state, BehaviorState.SLEEP)

    def test_regrab_cancels_pose_and_stale_timeout(self):
        self.w._enter_state(BehaviorState.SLEEP)
        timer_id = self.w._state_timer.timerId()
        self.land()
        QTest.mousePress(self.w, Qt.LeftButton, pos=QPoint(72, 80))
        self.assertFalse(self.w._landing)
        self.assertFalse(self.w._landing_timer.isActive())
        self.assertIsNotNone(self.w._drag_offset)
        self.w._landing_timer.timeout.emit()
        self.assertIsNotNone(self.w._drag_offset)
        self.assertEqual(self.w.state, BehaviorState.SLEEP)
        self.assertEqual(self.w._state_timer.timerId(), timer_id)
        QTest.mouseRelease(self.w, Qt.LeftButton, pos=QPoint(72, 80))
