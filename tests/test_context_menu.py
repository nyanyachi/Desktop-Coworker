"""Small context-menu interaction and real event-loop shutdown checks."""
import os
from pathlib import Path
import subprocess
import sys
import unittest

import shiboken6
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, Qt, QTimer
from PySide6.QtGui import QContextMenuEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from main import BehaviorState, CharacterWindow
from skin import Skin


class ContextMenuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_right_click_only_opens_menu_and_left_drag_still_works(self):
        w = CharacterWindow(Skin.load('template'))
        w._activity.timer.stop()
        w._proximity.timer.stop()
        w.show()
        self.app.processEvents()
        try:
            self.assertEqual([a.text() for a in w._context_menu.actions()],
                             ['Quit Desktop Coworker'])
            for state in BehaviorState:
                w._enter_state(state)
                timers = [(t, t.isActive(), t.timerId()) for t in w.findChildren(QTimer)]
                position = w.pos()
                QTest.mouseClick(w, Qt.RightButton, pos=QPoint(72, 80))
                event = QContextMenuEvent(QContextMenuEvent.Mouse, QPoint(72, 80),
                                          w.mapToGlobal(QPoint(72, 80)))
                QApplication.sendEvent(w, event)
                self.assertTrue(w._context_menu.isVisible())
                self.assertIsNone(w._drag_offset)
                self.assertEqual(w.state, state)
                self.assertEqual(w.pos(), position)
                self.assertFalse(w._react_pending)
                self.assertEqual([(t, t.isActive(), t.timerId()) for t, _, _ in timers], timers)
                w._context_menu.hide()
            w._enter_state(BehaviorState.WALK)
            QTest.mousePress(w, Qt.LeftButton, pos=QPoint(72, 80))
            self.assertIsNotNone(w._drag_offset)
            self.assertFalse(w._movement_timer.isActive())
            QTest.mouseRelease(w, Qt.LeftButton, pos=QPoint(72, 80))
            self.assertEqual(w.state, BehaviorState.IDLE)
        finally:
            w.close()
            w.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.assertFalse(shiboken6.isValid(w))

    def test_quit_action_exits_event_loop_and_destroys_owned_resources(self):
        for state in ('IDLE', 'WALK', 'WORK', 'SLEEP', 'REACT', 'FALL', 'LANDING', 'REBOUND'):
            with self.subTest(state=state):
                code = f'''
from contextlib import contextmanager
import shiboken6
import main
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
owned = []
original = main.CharacterWindow.__init__
def initialize(self, *args, **kwargs):
    original(self, *args, **kwargs)
    self._enter_state(main.BehaviorState.{'IDLE' if state in ('FALL', 'LANDING', 'REBOUND') else state})
    if {state == 'FALL'}:
        self.move(self.x(), self.screen().availableGeometry().top())
        self._set_drag_visual('grabbed')
        self._start_fall()
        assert self._fall_timer.isActive()
    if {state in ('LANDING', 'REBOUND')}:
        self._set_drag_visual('grabbed')
        self._finish_fall()
        if {state == 'LANDING'}:
            self._finish_rebound()
            assert self._landing_timer.isActive()
        else:
            assert self._rebounding and self._fall_timer.isActive()
    owned.extend([self, self._animation, self._activity, self._proximity,
                  self._context_menu, *self.findChildren(QTimer)])
    QTimer.singleShot(50, self._context_menu.actions()[0].trigger)
main.CharacterWindow.__init__ = initialize
shutdown_exited = []
original_shutdown = main.console_shutdown
@contextmanager
def shutdown(app):
    with original_shutdown(app):
        yield
    shutdown_exited.append(True)
main.console_shutdown = shutdown
assert main.main(['--skin', 'template']) == 0
assert shutdown_exited == [True]
assert all(not shiboken6.isValid(obj) for obj in owned)
print('clean menu shutdown')
'''
                result = subprocess.run(
                    [sys.executable, '-c', code],
                    cwd=Path(__file__).resolve().parents[1],
                    env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
                    capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('clean menu shutdown', result.stdout)
                self.assertNotIn('Traceback', result.stderr)

