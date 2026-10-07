import sys
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from activity import ActivityMonitor, seconds_since_last_input


class ActivityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_isolated_input_sustained_activity_and_sampling_gap(self):
        now = [0.0]
        idle = [0.0]
        monitor = ActivityMonitor(query=lambda: idle[0], clock=lambda: now[0])
        try:
            self.assertEqual(monitor.timer.interval(), 1000)
            for second in range(11):
                now[0] = second
                idle[0] = second  # Only one initial input.
                monitor.sample()
                self.assertFalse(monitor.is_eligible)
            for second in range(11, 17):
                now[0] = second
                idle[0] = 1
                monitor.sample()
                self.assertEqual(monitor.is_eligible, second >= 16)
            self.assertTrue(monitor.is_eligible)
            idle[0] = 4
            monitor.sample()
            self.assertFalse(monitor.is_eligible)
            idle[0] = 0
            monitor.sample()
            now[0] += 60
            monitor.sample()
            self.assertFalse(monitor.is_eligible)
        finally:
            monitor.timer.stop()
            monitor.deleteLater()

    def test_unsupported_platform_is_inactive(self):
        with patch('activity.sys.platform', 'unsupported'):
            self.assertEqual(seconds_since_last_input(), float('inf'))

    @unittest.skipUnless(sys.platform == 'win32', 'Windows input query')
    def test_real_windows_query(self):
        self.assertGreaterEqual(seconds_since_last_input(), 0)
