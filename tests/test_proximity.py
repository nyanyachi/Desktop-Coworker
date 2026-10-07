import unittest

from PySide6.QtCore import QPoint, QRect
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from proximity import ProximityMonitor


class ProximityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_entry_no_repeat_live_geometry_and_drag_rearm(self):
        point = [QPoint(-1000, -1000)]
        geometry = [QRect(100, 100, 144, 160)]
        monitor = ProximityMonitor(lambda: geometry[0], cursor_position=lambda: point[0])
        monitor.timer.stop()
        spy = QSignalSpy(monitor.entered)
        self.assertEqual(monitor.timer.interval(), 250)
        point[0] = QPoint(20, 20)  # Inclusive edge of the 80-pixel margin.
        monitor.sample()
        self.assertEqual(spy.count(), 1)
        monitor.sample()
        self.assertEqual(spy.count(), 1)
        monitor.suspend()
        point[0] = QPoint(-1000, -1000)
        monitor.sample()
        point[0] = QPoint(100, 100)
        monitor.sample()
        self.assertEqual(spy.count(), 1)
        monitor.resume()
        monitor.sample()
        self.assertEqual(spy.count(), 1)
        point[0] = QPoint(19, 20)
        monitor.sample()
        point[0] = QPoint(20, 20)
        monitor.sample()
        self.assertEqual(spy.count(), 2)
        geometry[0] = QRect(-500, -500, 144, 160)
        monitor.sample()
        point[0] = QPoint(-500, -500)
        monitor.sample()
        self.assertEqual(spy.count(), 3)
        monitor.deleteLater()
