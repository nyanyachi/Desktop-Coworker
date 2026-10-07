"""Exercise real Windows console events without interrupting the test runner."""

import os
from pathlib import Path
import subprocess
import sys
import unittest


@unittest.skipUnless(sys.platform == 'win32', 'Windows console handling')
class ShutdownTests(unittest.TestCase):
    def test_ctrl_c_exits_idle_walk_and_drag_without_traceback(self):
        for mode in ('idle', 'walk', 'drag', 'sleep', 'work', 'react'):
            with self.subTest(mode=mode):
                code = f'''
import ctypes
from contextlib import contextmanager
import main
from skin import discover_skins
from PySide6.QtCore import QPoint, QTimer

# The tool host may ignore Ctrl+C; that flag is inherited by child processes.
ctypes.windll.kernel32.SetConsoleCtrlHandler(None, False)

original = main.CharacterWindow.__init__
def initialize(self, *args, **kwargs):
    original(self, *args, **kwargs)
    if {mode!r} == 'walk':
        self._enter_state(main.BehaviorState.WALK)
    elif {mode!r} == 'sleep':
        self._enter_state(main.BehaviorState.SLEEP)
    elif {mode!r} == 'work':
        self._enter_state(main.BehaviorState.WORK)
    elif {mode!r} == 'react':
        self._enter_state(main.BehaviorState.REACT)
    elif {mode!r} == 'drag':
        self._drag_offset = QPoint(50, 50)
        self._state_timer.stop()
        self._movement_timer.stop()
main.CharacterWindow.__init__ = initialize

def interrupt():
    # Broadcast only within this child's separate console.
    if not ctypes.windll.kernel32.GenerateConsoleCtrlEvent(0, 0):
        raise ctypes.WinError()

# Send the event only after the real native handler has been installed.
original_shutdown = main.console_shutdown
@contextmanager
def shutdown(app):
    with original_shutdown(app):
        QTimer.singleShot(100, interrupt)
        yield
main.console_shutdown = shutdown
result = main.main(['--skin', discover_skins()[0]])
print('clean exit', result)
raise SystemExit(result)
'''
                startup = subprocess.STARTUPINFO()
                startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startup.wShowWindow = subprocess.SW_HIDE
                result = subprocess.run(
                    [sys.executable, '-c', code],
                    cwd=Path(__file__).resolve().parents[1],
                    env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
                    creationflags=subprocess.CREATE_NEW_CONSOLE,
                    startupinfo=startup,
                    capture_output=True, text=True, timeout=5,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('clean exit 0', result.stdout)
                self.assertNotIn('KeyboardInterrupt', result.stderr)
                self.assertNotIn('Traceback', result.stderr)


if __name__ == '__main__':
    unittest.main()
