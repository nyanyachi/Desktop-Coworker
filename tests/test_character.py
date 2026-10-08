import unittest
from unittest.mock import patch

from PySide6.QtCore import QPoint, QRect, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from main import BehaviorState, CharacterWindow, clamp_position
from skin import Skin, discover_skins
from activity import ActivityMonitor


class CharacterTests(unittest.TestCase):
    # Behavior coverage uses the available bundled skin, not a character-specific subclass.
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.monitor = ActivityMonitor(query=lambda: float('inf'))
        self.window = CharacterWindow(Skin.load(discover_skins()[0]), self.monitor)
        self.window._proximity.timer.stop()
        self.window.show()
        self.app.processEvents()


    def tearDown(self):
        self.monitor.timer.stop()
        self.monitor.deleteLater()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_window_and_idle(self):
        w = self.window
        self.assertTrue(w.isVisible())
        self.assertTrue(w.windowFlags() & Qt.FramelessWindowHint)
        self.assertTrue(w.windowFlags() & Qt.WindowStaysOnTopHint)
        self.assertTrue(w.testAttribute(Qt.WA_TranslucentBackground))
        image = w.grab().toImage()
        self.assertEqual(image.pixelColor(0, 0).alpha(), 0)
        self.assertTrue(any(image.pixelColor(x, y).alpha() > 0
                            for x in range(image.width()) for y in range(image.height())))
        self.assertEqual(w.state, BehaviorState.IDLE)
        self.assertTrue(w._state_timer.isSingleShot())
        self.assertFalse(w._movement_timer.isActive())
        self.assertTrue(8000 <= w._state_timer.interval() <= 16000)
        original = w.pos()
        QTest.qWait(100)
        self.assertEqual(w.pos(), original)

    def test_walk_both_directions_and_edges(self):
        w = self.window
        area = w.screen().availableGeometry()
        for direction in (-1, 1):
            with self.subTest(direction=direction):
                w.move(area.center() - QPoint(w.width() // 2, w.height() // 2))
                with patch('main.random.choice', return_value=direction):
                    w._enter_state(BehaviorState.WALK)
                self.assertTrue(2000 <= w._state_timer.interval() <= 4000)
                self.assertTrue(w._movement_timer.isActive())
                original = w.pos()
                w._walk_step()
                self.assertEqual(w.pos(), original + QPoint(direction, 0))
                edge = area.left() if direction < 0 else area.right() - w.width() + 1
                w.move(edge - direction, w.y())
                w._walk_step()
                self.assertEqual(w.x(), edge)
                self.assertTrue(area.contains(w.geometry()))
                self.assertEqual(w.state, BehaviorState.IDLE)
                self.assertFalse(w._movement_timer.isActive())

    def test_automatic_repeated_transitions(self):
        w = self.window
        area = w.screen().availableGeometry()
        w.move(area.center() - QPoint(w.width() // 2, w.height() // 2))
        # Shorten only test durations; exercise real Qt timeout connections.
        with patch.object(w, 'IDLE_DURATION_MS', (30, 30)), \
                patch.object(w, 'WALK_DURATION_MS', (80, 80)):
            w._enter_state(BehaviorState.IDLE)
            for _ in range(3):
                for expected in (BehaviorState.WALK, BehaviorState.IDLE):
                    for _ in range(100):
                        if w.state == expected:
                            break
                        QTest.qWait(5)
                    self.assertEqual(w.state, expected)

    def test_drag_pauses_and_release_restarts_idle(self):
        w = self.window
        for state in (BehaviorState.IDLE, BehaviorState.WALK):
            w._enter_state(state)
            QTest.mousePress(w, Qt.LeftButton, pos=QPoint(72, 80))
            self.assertIsNotNone(w._drag_offset)
            self.assertFalse(w._state_timer.isActive())
            self.assertFalse(w._movement_timer.isActive())
            original = w.pos()
            w._walk_step()
            w._advance_state()
            QTest.qWait(100)
            self.assertEqual(w.pos(), original)
            QTest.mouseMove(w, QPoint(90, 90))
            self.assertNotEqual(w.pos(), original)
            QTest.mouseRelease(w, Qt.LeftButton, pos=QPoint(90, 90))
            self.assertTrue(w._living_screen().availableGeometry().contains(w.geometry()))
            self.assertIsNone(w._drag_offset)
            self.assertEqual(w.state, BehaviorState.IDLE)
            self.assertTrue(w._state_timer.isActive())
            self.assertFalse(w._movement_timer.isActive())

    def test_clamp_all_edges_including_negative_screen_coordinates(self):
        for area in (QRect(0, 0, 1920, 1040), QRect(-1920, -200, 1920, 1080)):
            for x in (-10000, area.center().x(), 10000):
                for y in (-10000, area.center().y(), 10000):
                    position = clamp_position(QPoint(x, y), self.window.size(), area)
                    self.assertTrue(area.contains(QRect(position, self.window.size())))

    def test_sleep_waits_for_walk_and_wakes_to_fresh_idle(self):
        w = self.window
        self.assertTrue(60000 <= w._awake_timer.interval() <= 120000)
        w._enter_state(BehaviorState.WALK)
        w._sleep_due()
        self.assertEqual(w.state, BehaviorState.WALK)
        self.assertTrue(w._movement_timer.isActive())
        w._advance_state()
        self.assertEqual(w.state, BehaviorState.SLEEP)
        self.assertEqual(w._animation.key, 'SLEEP')
        self.assertEqual(w._animation.frame_index, 0)
        self.assertFalse(w._animation.timer.isActive())
        self.assertFalse(w._movement_timer.isActive())
        self.assertFalse(w._awake_timer.isActive())
        self.assertTrue(10000 <= w._state_timer.interval() <= 20000)
        position = w.pos()
        w._walk_step()
        QTest.qWait(30)
        self.assertEqual(w.pos(), position)
        w._advance_state()
        self.assertEqual(w.state, BehaviorState.IDLE)
        self.assertEqual(w._animation.key, 'IDLE')
        self.assertTrue(w._awake_timer.isActive())
        self.assertFalse(w._sleep_pending)

    def test_repeated_work_sleep_cycles_reuse_timers(self):
        w = self.window
        count = len(w.findChildren(QTimer))
        for _ in range(4):
            w._enter_state(BehaviorState.WORK)
            w._sleep_due()
            w._advance_state()
            self.assertEqual(w.state, BehaviorState.SLEEP)
            w._advance_state()
            self.assertEqual(w.state, BehaviorState.IDLE)
            self.assertTrue(w._awake_timer.isActive())
            self.assertTrue(w._state_timer.isActive())
            self.assertFalse(w._movement_timer.isActive())
            self.assertEqual(len(w.findChildren(QTimer)), count)
        self.assertEqual(w._animation.key, 'IDLE')
        self.assertTrue(w._awake_timer.isActive())
        self.assertFalse(w._sleep_pending)

    def test_work_safe_entry_cooldown_and_sleep_priority(self):
        w = self.window
        self.monitor.is_eligible = True
        w._enter_state(BehaviorState.WALK)
        w._maybe_work()
        self.assertEqual(w.state, BehaviorState.WALK)
        w._advance_state()
        self.assertEqual(w.state, BehaviorState.WORK)
        self.assertEqual(w._animation.key, 'WORK')
        self.assertFalse(w._animation.timer.isActive())
        self.assertFalse(w._movement_timer.isActive())
        self.assertTrue(15000 <= w._state_timer.interval() <= 30000)
        position = w.pos()
        w._walk_step()
        self.assertEqual(w.pos(), position)
        with patch('main.time.monotonic', return_value=100):
            w._advance_state()
            self.assertEqual(w.state, BehaviorState.IDLE)
            self.assertTrue(130 <= w._work_allowed_at <= 160)
            w._maybe_work()
            self.assertEqual(w.state, BehaviorState.IDLE)
        with patch('main.time.monotonic', return_value=200):
            w._maybe_work()
            self.assertEqual(w.state, BehaviorState.WORK)
        w._sleep_due()
        self.assertEqual(w.state, BehaviorState.WORK)
        w._advance_state()
        self.assertEqual(w.state, BehaviorState.SLEEP)
        w._maybe_work()
        self.assertEqual(w.state, BehaviorState.SLEEP)
        w._advance_state()
        self.assertEqual(w.state, BehaviorState.IDLE)

    def test_work_drag_keeps_duration_and_defers_completion(self):
        w = self.window
        w._enter_state(BehaviorState.WORK)
        deadline = w._state_timer.remainingTime()
        QTest.mousePress(w, Qt.LeftButton, pos=QPoint(72, 80))
        QTest.mouseMove(w, QPoint(90, 90))
        QTest.mouseRelease(w, Qt.LeftButton, pos=QPoint(90, 90))
        self.assertEqual(w.state, BehaviorState.WORK)
        self.assertTrue(0 < w._state_timer.remainingTime() <= deadline)
        QTest.mousePress(w, Qt.LeftButton, pos=QPoint(72, 80))
        w._state_timer.start(10)
        for _ in range(100):
            if w._work_end_pending:
                break
            QTest.qWait(5)
        self.assertTrue(w._work_end_pending)
        self.assertEqual(w.state, BehaviorState.WORK)
        QTest.mouseRelease(w, Qt.LeftButton, pos=QPoint(72, 80))
        self.assertEqual(w.state, BehaviorState.IDLE)

    def test_react_pending_priority_cooldown_and_ignored_states(self):
        w = self.window
        self.monitor.is_eligible = True
        w._enter_state(BehaviorState.WALK)
        w._proximity_entered()
        w._proximity_entered()
        self.assertEqual(w.state, BehaviorState.WALK)
        self.assertTrue(w._react_pending)
        w._advance_state()
        self.assertEqual(w.state, BehaviorState.REACT)
        self.assertFalse(w._react_pending)
        self.assertEqual(w._animation.key, 'REACT')
        self.assertFalse(w._movement_timer.isActive())
        self.assertTrue(1500 <= w._state_timer.interval() <= 3000)
        with patch('main.time.monotonic', return_value=100):
            w._advance_state()
            self.assertEqual(w.state, BehaviorState.IDLE)
            self.assertTrue(105 <= w._react_allowed_at <= 110)
            w._proximity_entered()
            self.assertEqual(w.state, BehaviorState.IDLE)
        with patch('main.time.monotonic', return_value=200):
            w._proximity_entered()
            self.assertEqual(w.state, BehaviorState.REACT)
            w._sleep_due()
            self.assertEqual(w.state, BehaviorState.REACT)
            w._advance_state()
            self.assertEqual(w.state, BehaviorState.SLEEP)
        for state in (BehaviorState.WORK, BehaviorState.SLEEP):
            w._enter_state(state)
            deadline = w._state_timer.remainingTime()
            w._react_allowed_at = 0
            w._proximity_entered()
            self.assertEqual(w.state, state)
            self.assertFalse(w._react_pending)
            self.assertTrue(0 < w._state_timer.remainingTime() <= deadline)
        w._enter_state(BehaviorState.WALK)
        w._proximity_entered()
        w._sleep_due()
        w._advance_state()
        self.assertEqual(w.state, BehaviorState.SLEEP)
        self.assertFalse(w._react_pending)

    def test_react_drag_deferral_and_no_release_reaction(self):
        w = self.window
        w._proximity_entered()
        self.assertEqual(w.state, BehaviorState.REACT)
        QTest.mousePress(w, Qt.LeftButton, pos=QPoint(72, 80))
        w._state_timer.start(10)
        for _ in range(100):
            if w._react_end_pending:
                break
            QTest.qWait(5)
        self.assertTrue(w._react_end_pending)
        self.assertEqual(w.state, BehaviorState.REACT)
        QTest.mouseMove(w, QPoint(90, 90))
        QTest.mouseRelease(w, Qt.LeftButton, pos=QPoint(90, 90))
        self.assertEqual(w.state, BehaviorState.IDLE)
        w._react_allowed_at = 0
        point = [w.frameGeometry().center()]
        w._proximity._cursor_position = lambda: point[0]
        w._proximity.sample()
        self.assertEqual(w.state, BehaviorState.IDLE)
        point[0] = QPoint(-10000, -10000)
        w._proximity.sample()
        point[0] = w.frameGeometry().center()
        w._proximity.sample()
        self.assertEqual(w.state, BehaviorState.REACT)
        QTest.mousePress(w, Qt.LeftButton, pos=QPoint(72, 80))
        w._proximity_entered()
        self.assertEqual(w.state, BehaviorState.REACT)
        QTest.mouseRelease(w, Qt.LeftButton, pos=QPoint(72, 80))

    def test_sleep_drag_keeps_deadline_and_defers_expired_wake(self):
        w = self.window
        w._enter_state(BehaviorState.SLEEP)
        remaining = w._state_timer.remainingTime()
        QTest.mousePress(w, Qt.LeftButton, pos=QPoint(72, 80))
        QTest.mouseMove(w, QPoint(90, 90))
        QTest.mouseRelease(w, Qt.LeftButton, pos=QPoint(90, 90))
        self.assertEqual(w.state, BehaviorState.SLEEP)
        self.assertTrue(0 < w._state_timer.remainingTime() <= remaining)
        QTest.mousePress(w, Qt.LeftButton, pos=QPoint(72, 80))
        w._state_timer.start(10)
        for _ in range(100):
            if w._wake_pending:
                break
            QTest.qWait(5)
        self.assertTrue(w._wake_pending)
        self.assertEqual(w.state, BehaviorState.SLEEP)
        QTest.mouseRelease(w, Qt.LeftButton, pos=QPoint(72, 80))
        self.assertEqual(w.state, BehaviorState.IDLE)
        self.assertTrue(w._awake_timer.isActive())

    def test_awake_expiry_during_drag_and_repeated_timer_cycles(self):
        w = self.window
        QTest.mousePress(w, Qt.LeftButton, pos=QPoint(72, 80))
        w._sleep_due()
        self.assertEqual(w.state, BehaviorState.IDLE)
        QTest.mouseRelease(w, Qt.LeftButton, pos=QPoint(72, 80))
        self.assertEqual(w.state, BehaviorState.SLEEP)
        count = len(w.findChildren(QTimer))
        with patch.object(w, 'AWAKE_DURATION_MS', (20, 20)), \
                patch.object(w, 'SLEEP_DURATION_MS', (20, 20)):
            for _ in range(3):
                w._advance_state()
                for _ in range(100):
                    if w.state == BehaviorState.SLEEP:
                        break
                    QTest.qWait(5)
                self.assertEqual(w.state, BehaviorState.SLEEP)
                self.assertEqual(len(w.findChildren(QTimer)), count)
                self.assertFalse(w._awake_timer.isActive())
                self.assertTrue(w._state_timer.isActive())



if __name__ == '__main__':
    unittest.main()
