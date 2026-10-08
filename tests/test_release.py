"""Release version and launches outside the source working directory."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from main import __version__


class ReleaseTests(unittest.TestCase):
    def test_release_version(self):
        self.assertEqual(__version__, '0.1.1')

    def test_default_and_explicit_launch_from_another_directory(self):
        root = Path(__file__).resolve().parents[1]
        code = f'''
import sys
sys.path.insert(0, {str(root)!r})
import main
from PySide6.QtCore import QTimer
original = main.CharacterWindow.show
def show(self):
    assert self.skin.id == 'template'
    assert self.skin.scale_mode == 'smooth'
    assert self.state == main.BehaviorState.IDLE
    original(self)
    QTimer.singleShot(100, self._context_menu.actions()[0].trigger)
main.CharacterWindow.show = show
assert main.main() == 0
print('Template launched and quit')
'''
        with tempfile.TemporaryDirectory() as temporary:
            for args in ([], ['--skin', 'template']):
                with self.subTest(args=args):
                    result = subprocess.run(
                        [sys.executable, '-c', code, *args], cwd=temporary,
                        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
                        capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn('Template launched and quit', result.stdout)
                    self.assertNotIn('Traceback', result.stderr)
