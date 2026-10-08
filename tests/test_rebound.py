"""One cosmetic landing arc, followed by the unchanged 400 ms pose."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from main import BehaviorState, CharacterWindow
from skin import Skin


class ReboundTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.skin = Skin.load()

    def setUp(self):
        self.w = CharacterWindow(self.skin)
        self.w._activity.timer.stop()
        self.w._proximity.timer.stop()
        self.area = QRect(-1500, -1000, 1000, 900)
        self.screen = SimpleNamespace(availableGeometry=lambda: self.area)
        self.w._current_screen = self.screen
        p = patch('main.QApplication.screens', return_value=[self.screen])
        p.start()
        self.addCleanup(p.stop)
        self.floor = self.area.bottom() - self.w.height() + 1
        self.w.move(self.area.left() + 100, self.floor)

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()
        self.app.processEvents()

    def start(self):
        QTest.mousePress(self.w, Qt.LeftButton, pos=QPoint(72, 80))
        self.w._drag_offset = self.w._drag_origin = None
        self.w._set_drag_visual('grabbed')
        self.w._finish_fall()

    def step(self, fraction):
        with patch('main.time.monotonic', return_value=self.w._rebound_started + 0.220 * fraction):
            self.w._fall_step()

    def test_start_peak_exact_floor_and_single_arc(self):
        self.start()
        self.assertTrue(self.w._rebounding)
        self.assertTrue(self.w._fall_timer.isActive())
        self.assertFalse(self.w._falling)
        self.assertFalse(self.w._landing_timer.isActive())
        self.assertIsNone(self.w._drag_visual)
        x = self.w.x()
        with patch('main.QApplication.screenAt', side_effect=AssertionError('No monitor switching')):
            self.step(0)
            self.assertEqual(self.w.y(), self.floor)
            self.step(0.5)
            self.assertEqual(self.w.y(), self.floor - 9)
            with patch('main.QPainter') as painter:
                self.w.paintEvent(None)
                self.assertIs(painter.return_value.drawPixmap.call_args.args[2], self.skin.visual('WORK'))
            self.step(1.01)
        self.assertEqual(self.w.pos(), QPoint(x, self.floor))
        self.assertIs(self.w._current_screen, self.screen)
        self.assertFalse(self.w._rebounding)
        self.assertFalse(self.w._fall_timer.isActive())
        self.assertTrue(self.w._landing_timer.isActive())
        self.assertEqual(self.w._landing_timer.interval(), 400)
        self.w._fall_step()
        self.assertEqual(self.w.pos(), QPoint(x, self.floor))
        self.w._landing_timer.timeout.emit()
        self.assertFalse(self.w._landing)

    def test_regrab_cancels_motion_from_current_position(self):
        self.start()
        self.step(0.5)
        pos = self.w.pos()
        QTest.mousePress(self.w, Qt.LeftButton, pos=QPoint(72, 80))
        self.assertFalse(self.w._rebounding)
        self.assertFalse(self.w._landing)
        self.assertFalse(self.w._fall_timer.isActive())
        self.assertFalse(self.w._landing_timer.isActive())
        self.assertIsNotNone(self.w._drag_offset)
        self.step(1.1)
        self.w._landing_timer.timeout.emit()
        self.assertEqual(self.w.pos(), pos)
        self.assertIsNotNone(self.w._drag_offset)

    def test_state_and_deadline_preserved_through_rebound_and_pose(self):
        self.w._enter_state(BehaviorState.SLEEP)
        timer_id = self.w._state_timer.timerId()
        self.start()
        self.step(0.5)
        self.assertEqual(self.w.state, BehaviorState.SLEEP)
        self.assertEqual(self.w._state_timer.timerId(), timer_id)
        self.step(1.1)
        self.w._landing_timer.timeout.emit()
        self.assertEqual(self.w.state, BehaviorState.SLEEP)
        self.assertEqual(self.w._animation.key, 'SLEEP')
        self.assertEqual(self.w._state_timer.timerId(), timer_id)

    def test_expiry_waits_for_rebound_and_full_pose(self):
        self.w._enter_state(BehaviorState.WORK)
        self.start()
        self.w._advance_state()
        self.w._landing_timer.timeout.emit()  # Stale callback cannot end the rebound.
        self.assertTrue(self.w._rebounding)
        self.assertEqual(self.w.state, BehaviorState.WORK)
        self.step(1.1)
        self.assertEqual(self.w.state, BehaviorState.WORK)
        self.assertTrue(self.w._landing_timer.isActive())
        self.w._landing_timer.timeout.emit()
        self.assertEqual(self.w.state, BehaviorState.IDLE)
        self.assertFalse(self.w._landing)
