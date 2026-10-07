"""Low-frequency cursor entry detection; no hooks or position history."""

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QCursor


class ProximityMonitor(QObject):
    entered = Signal()
    POLL_INTERVAL_MS = 250
    MARGIN_PX = 80

    def __init__(self, geometry, parent=None, cursor_position=QCursor.pos):
        super().__init__(parent)
        self._geometry = geometry
        self._cursor_position = cursor_position
        self._suspended = False
        self._was_near = self._is_near()
        self.timer = QTimer(self)
        self.timer.setInterval(self.POLL_INTERVAL_MS)
        self.timer.timeout.connect(self.sample)
        self.timer.start()

    def _is_near(self):
        margin = self.MARGIN_PX
        return self._geometry().adjusted(-margin, -margin, margin, margin).contains(
            self._cursor_position())

    def sample(self):
        if self._suspended:
            return
        near = self._is_near()
        entered = near and not self._was_near
        self._was_near = near
        if entered:
            self.entered.emit()

    def suspend(self):
        self._suspended = True

    def resume(self):
        self._suspended = False
        # Require a sampled leave before another entry after dragging.
        self._was_near = True
