"""Coarse input recency only: no hooks, input contents, or window inspection."""

import ctypes
import sys
import time
from functools import lru_cache

from PySide6.QtCore import QObject, QTimer, Signal


@lru_cache(maxsize=1)
def _windows_query():
    from ctypes import wintypes

    class LastInputInfo(ctypes.Structure):
        _fields_ = [('cbSize', wintypes.UINT), ('dwTime', wintypes.DWORD)]

    user32 = ctypes.WinDLL('user32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    query = user32.GetLastInputInfo
    query.argtypes = (ctypes.POINTER(LastInputInfo),)
    query.restype = wintypes.BOOL
    ticks = kernel32.GetTickCount
    ticks.argtypes = ()
    ticks.restype = wintypes.DWORD

    def seconds():
        info = LastInputInfo()
        info.cbSize = ctypes.sizeof(info)
        if not query(ctypes.byref(info)):
            return float('inf')  # A failed sample is safely inactive.
        return ((ticks() - info.dwTime) & 0xFFFFFFFF) / 1000

    return seconds


def seconds_since_last_input():
    if sys.platform != 'win32':
        return float('inf')
    return _windows_query()()


class ActivityMonitor(QObject):
    sampled = Signal()
    POLL_INTERVAL_MS = 1000
    RECENT_SECONDS = 3
    SUSTAINED_SECONDS = 5

    def __init__(self, parent=None, query=seconds_since_last_input, clock=time.monotonic):
        super().__init__(parent)
        self._query = query
        self._clock = clock
        self._recent_since = None
        self._last_sample = None
        self.is_eligible = False
        self.timer = QTimer(self)
        self.timer.setInterval(self.POLL_INTERVAL_MS)
        self.timer.timeout.connect(self.sample)
        self.timer.start()

    def sample(self):
        now = self._clock()
        recent = self._query() <= self.RECENT_SECONDS
        # A long event-loop/system pause does not count as observed activity.
        gap = self._last_sample is not None and now - self._last_sample > 2.5
        if not recent:
            self._recent_since = None
        elif self._recent_since is None or gap:
            self._recent_since = now
        self._last_sample = now
        self.is_eligible = (recent and self._recent_since is not None
                            and now - self._recent_since >= self.SUSTAINED_SECONDS)
        self.sampled.emit()
