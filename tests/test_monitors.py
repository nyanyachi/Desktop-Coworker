"""Focused logical-coordinate monitor ownership and drag checks."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QSize, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from main import BehaviorState, CharacterWindow, clamp_position


class MonitorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = CharacterWindow()
        self.window._activity.timer.stop()
        self.window._proximity.timer.stop()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_arbitrary_monitor_clamping(self):
        for area in (QRect(-1920, 0, 1920, 1040), QRect(-800, -1200, 800, 1160),
                     QRect(1600, 200, 2560, 1400), QRect(0, 1080, 1024, 728)):
            for point in (area.topLeft() - QPoint(200, 200), area.center(),
                          area.bottomRight() + QPoint(200, 200)):
                with self.subTest(area=area, point=point):
                    result = clamp_position(point, QSize(144, 160), area)
                    self.assertTrue(area.contains(QRect(result, QSize(144, 160))))

    def test_release_selection_and_gap_fallback(self):
        w = self.window
        target, current, primary = object(), object(), object()
        w._current_screen = current
        pointer = QPoint(-900, -500)
        with patch('main.QApplication.screenAt', side_effect=[target]) as lookup:
            self.assertIs(w._drop_screen(pointer), target)
            lookup.assert_called_once_with(pointer)
        with patch('main.QApplication.screenAt', side_effect=[None, target]) as lookup:
            self.assertIs(w._drop_screen(pointer), target)
            self.assertEqual(lookup.call_args.args, (w.frameGeometry().center(),))
        with patch('main.QApplication.screenAt', return_value=None), \
                patch('main.QApplication.screens', return_value=[current]):
            self.assertIs(w._drop_screen(pointer), current)
        with patch('main.QApplication.screens', return_value=[primary]), \
                patch('main.QApplication.primaryScreen', return_value=primary):
            self.assertIs(w._living_screen(), primary)
            self.assertIs(w._current_screen, primary)

    def test_cross_monitor_drag_release_and_walk(self):
        w = self.window
        area = QRect(-1400, -1000, 1200, 900)
        target = SimpleNamespace(availableGeometry=lambda: area)
        for state in BehaviorState:
            with self.subTest(state=state):
                w._enter_state(state)
                timer_id = w._state_timer.timerId()
                press = QMouseEvent(QEvent.MouseButtonPress, QPointF(72, 80),
                                    QPointF(w.pos() + QPoint(72, 80)),
                                    Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
                w.mousePressEvent(press)
                lift = QMouseEvent(QEvent.MouseMove, QPointF(72, 80),
                                   QPointF(w._drag_origin + QPoint(0, -100)),
                                   Qt.NoButton, Qt.LeftButton, Qt.NoModifier)
                w.mouseMoveEvent(lift)
                self.assertEqual(w._drag_visual, 'grabbed')
                pointer = area.topLeft() + QPoint(10, 10)
                move = QMouseEvent(QEvent.MouseMove, QPointF(72, 80), QPointF(pointer),
                                   Qt.NoButton, Qt.LeftButton, Qt.NoModifier)
                w.mouseMoveEvent(move)
                self.assertEqual(w.pos(), pointer - QPoint(72, 80))
                self.assertFalse(area.contains(w.geometry()))  # Free during drag.
                before = w.pos()
                w._walk_step()
                self.assertEqual(w.pos(), before)
                release = QMouseEvent(QEvent.MouseButtonRelease, QPointF(72, 80),
                                      QPointF(pointer), Qt.LeftButton,
                                      Qt.NoButton, Qt.NoModifier)
                with patch('main.QApplication.screenAt', return_value=target), \
                        patch('main.QApplication.screens', return_value=[target]):
                    w.mouseReleaseEvent(release)
                    if w._falling:
                        with patch('main.QApplication.screens', return_value=[target]), \
                                patch('main.time.monotonic', return_value=w._fall_last_tick + 10):
                            w._fall_step()
                    if w._rebounding:
                        w._finish_rebound()
                    if w._landing:
                        w._landing_timer.timeout.emit()
                self.assertIsNone(w._drag_visual)
                self.assertIs(w._current_screen, target)
                self.assertTrue(area.contains(w.geometry()))
                if state in (BehaviorState.WORK, BehaviorState.SLEEP, BehaviorState.REACT):
                    self.assertEqual(w.state, state)
                    self.assertEqual(w._state_timer.timerId(), timer_id)
        with patch('main.QApplication.screens', return_value=[target]):
            for direction in (-1, 1):
                w._enter_state(BehaviorState.WALK)
                w._direction = direction
                edge = area.left() if direction < 0 else area.right() - w.width() + 1
                w.move(edge - direction, area.top() + 20)
                w._walk_step()
                self.assertEqual(w.x(), edge)
                self.assertTrue(area.contains(w.geometry()))
                self.assertEqual(w.state, BehaviorState.IDLE)
