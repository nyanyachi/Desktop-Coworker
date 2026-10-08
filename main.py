"""A small, transparent desktop character window."""

import sys
import argparse
import random
import time
from contextlib import contextmanager
from enum import Enum, auto

from PySide6.QtCore import QMetaObject, QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QMouseEvent, QPainter
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QWidget

from skin import DEFAULT_SKIN, Skin, discover_skins, prepare_skin_directory
from animation import AnimationPlayer
from activity import ActivityMonitor
from proximity import ProximityMonitor


__version__ = "0.1.1-beta.1"


def clamp_position(position: QPoint, size, available: QRect) -> QPoint:
    """Keep the entire window inside the screen's usable area."""
    max_x = max(available.left(), available.right() - size.width() + 1)
    max_y = max(available.top(), available.bottom() - size.height() + 1)
    return QPoint(
        min(max(position.x(), available.left()), max_x),
        min(max(position.y(), available.top()), max_y),
    )


class BehaviorState(Enum):
    IDLE = auto()
    WALK = auto()
    SLEEP = auto()
    WORK = auto()
    REACT = auto()


class CharacterWindow(QWidget):
    IDLE_DURATION_MS = (8_000, 16_000)
    WALK_DURATION_MS = (2_000, 4_000)
    AWAKE_DURATION_MS = (60_000, 120_000)
    SLEEP_DURATION_MS = (10_000, 20_000)
    WORK_DURATION_MS = (15_000, 30_000)
    WORK_COOLDOWN_MS = (30_000, 60_000)
    REACT_DURATION_MS = (1_500, 3_000)
    REACT_COOLDOWN_MS = (5_000, 10_000)
    MOVEMENT_INTERVAL_MS = 40
    WALK_STEP_PX = 1  # 25 pixels per second at the nominal timer interval.

    def __init__(self, skin=None, activity_monitor=None):
        super().__init__()
        self.setWindowTitle("Desktop Coworker")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(144, 160)
        self.skin = skin if skin is not None else Skin.load()
        self._animation = AnimationPlayer(self.skin, self)
        self._animation.frame_changed.connect(self.update)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._drag_offset = None
        self._context_menu = QMenu(self)
        quit_action = self._context_menu.addAction('Quit Desktop Coworker')
        quit_action.triggered.connect(QApplication.instance().quit)

        self._current_screen = QApplication.primaryScreen()
        available = self._current_screen.availableGeometry()
        start = QPoint(
            available.right() - self.width() - 24 + 1,
            available.bottom() - self.height() - 24 + 1,
        )
        self.move(clamp_position(start, self.size(), available))

        self._direction = 1
        self._state_timer = QTimer(self)
        self._state_timer.setSingleShot(True)
        self._state_timer.timeout.connect(self._advance_state)
        self._movement_timer = QTimer(self)
        self._movement_timer.setInterval(self.MOVEMENT_INTERVAL_MS)
        self._movement_timer.timeout.connect(self._walk_step)
        self._awake_timer = QTimer(self)
        self._awake_timer.setSingleShot(True)
        self._awake_timer.timeout.connect(self._sleep_due)
        self._sleep_pending = False
        self._wake_pending = False
        self._work_end_pending = False
        self._work_allowed_at = 0.0
        self._react_pending = False
        self._react_end_pending = False
        self._react_allowed_at = 0.0
        self._start_awake_period()
        self._enter_state(BehaviorState.IDLE)
        self._activity = activity_monitor if activity_monitor is not None else ActivityMonitor(self)
        self._activity.sampled.connect(self._maybe_work)
        self._proximity = ProximityMonitor(self.frameGeometry, self)
        self._proximity.entered.connect(self._proximity_entered)

    def _proximity_entered(self):
        if (self._drag_offset is not None or self._sleep_pending
                or time.monotonic() < self._react_allowed_at):
            return
        if self.state == BehaviorState.IDLE:
            self._enter_state(BehaviorState.REACT)
        elif self.state == BehaviorState.WALK:
            self._react_pending = True

    def _work_eligible(self):
        return self._activity.is_eligible and time.monotonic() >= self._work_allowed_at

    def _maybe_work(self):
        if (self.state == BehaviorState.IDLE and self._drag_offset is None
                and not self._sleep_pending and self._work_eligible()):
            self._enter_state(BehaviorState.WORK)

    def _start_awake_period(self):
        self._sleep_pending = False
        self._wake_pending = False
        self._awake_timer.start(random.randint(*self.AWAKE_DURATION_MS))

    def _sleep_due(self):
        self._awake_timer.stop()
        self._sleep_pending = True
        if self.state == BehaviorState.IDLE and self._drag_offset is None:
            self._enter_state(BehaviorState.SLEEP)

    def _enter_state(self, state: BehaviorState):
        self._state_timer.stop()
        self._movement_timer.stop()
        self.state = state
        if self._drag_offset is not None:
            return
        if state == BehaviorState.IDLE:
            duration = random.randint(*self.IDLE_DURATION_MS)
        elif state == BehaviorState.WALK:
            self._direction = random.choice((-1, 1))
            duration = random.randint(*self.WALK_DURATION_MS)
            self._movement_timer.start()
        elif state == BehaviorState.WORK:
            self._work_end_pending = False
            duration = random.randint(*self.WORK_DURATION_MS)
        elif state == BehaviorState.REACT:
            self._react_pending = False
            self._react_end_pending = False
            duration = random.randint(*self.REACT_DURATION_MS)
        else:
            self._awake_timer.stop()
            self._sleep_pending = False
            self._wake_pending = False
            duration = random.randint(*self.SLEEP_DURATION_MS)
        if state in (BehaviorState.SLEEP, BehaviorState.WORK):
            self._react_pending = False
        self._state_timer.start(duration)
        self._animation.select(('WALK_LEFT' if self._direction < 0 else 'WALK_RIGHT')
                               if state == BehaviorState.WALK else state.name)

    def _advance_state(self):
        if self._drag_offset is not None:
            if self.state == BehaviorState.SLEEP:
                self._wake_pending = True
            elif self.state == BehaviorState.WORK:
                self._work_end_pending = True
            elif self.state == BehaviorState.REACT:
                self._react_end_pending = True
            return
        if self.state == BehaviorState.SLEEP:
            self._start_awake_period()
            self._enter_state(BehaviorState.IDLE)
        elif self.state == BehaviorState.WORK:
            self._work_end_pending = False
            self._work_allowed_at = time.monotonic() + random.randint(*self.WORK_COOLDOWN_MS) / 1000
            self._enter_state(BehaviorState.SLEEP if self._sleep_pending else BehaviorState.IDLE)
        elif self.state == BehaviorState.REACT:
            self._react_end_pending = False
            self._react_allowed_at = time.monotonic() + random.randint(*self.REACT_COOLDOWN_MS) / 1000
            self._enter_state(BehaviorState.SLEEP if self._sleep_pending else BehaviorState.IDLE)
        elif self._sleep_pending:
            self._enter_state(BehaviorState.SLEEP)
        elif self._react_pending and time.monotonic() >= self._react_allowed_at:
            self._enter_state(BehaviorState.REACT)
        elif self._work_eligible():
            self._enter_state(BehaviorState.WORK)
        else:
            next_state = (BehaviorState.WALK if self.state == BehaviorState.IDLE
                          else BehaviorState.IDLE)
            self._enter_state(next_state)

    def _living_screen(self):
        """Use explicit ownership, falling back if a monitor was disconnected."""
        if self._current_screen not in QApplication.screens():
            self._current_screen = QApplication.primaryScreen()
        return self._current_screen

    def _drop_screen(self, pointer):
        """Prefer the release cursor, then window center, then current/primary."""
        return (QApplication.screenAt(pointer)
                or QApplication.screenAt(self.frameGeometry().center())
                or self._living_screen())

    def _walk_step(self):
        if self._drag_offset is not None or self.state != BehaviorState.WALK:
            return
        screen = self._living_screen()
        if screen is None:
            return
        available = screen.availableGeometry()
        desired = self.pos() + QPoint(self._direction * self.WALK_STEP_PX, 0)
        position = clamp_position(desired, self.size(), available)
        self.move(position)
        right_limit = available.right() - self.width() + 1
        if ((self._direction < 0 and position.x() <= available.left())
                or (self._direction > 0 and position.x() >= right_limit)):
            self._advance_state()

    def paintEvent(self, event):
        painter = QPainter(self)
        image = self._animation.frame
        painter.drawPixmap((self.width() - image.width()) // 2,
                           self.height() - 8 - image.height(), image)

    def contextMenuEvent(self, event):
        self._context_menu.popup(event.globalPos())
        event.accept()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
            self._proximity.suspend()
            self._react_pending = False
            if self.state not in (BehaviorState.SLEEP, BehaviorState.WORK, BehaviorState.REACT):
                self._state_timer.stop()
            self._movement_timer.stop()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_offset is not None:
            pointer = event.globalPosition().toPoint()
            position = pointer - self._drag_offset
            self.move(position)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._drag_offset is not None:
                self._current_screen = self._drop_screen(event.globalPosition().toPoint())
                if self._current_screen is not None:
                    self.move(clamp_position(self.pos(), self.size(),
                                             self._current_screen.availableGeometry()))
            self._drag_offset = None
            self._proximity.resume()
            if self.state == BehaviorState.REACT:
                if self._react_end_pending:
                    self._advance_state()
            elif self.state == BehaviorState.WORK:
                if self._work_end_pending:
                    self._advance_state()
            elif self.state == BehaviorState.SLEEP:
                if self._wake_pending:
                    self._advance_state()
            else:
                self._enter_state(BehaviorState.SLEEP if self._sleep_pending else BehaviorState.IDLE)
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
        else:
            super().mouseReleaseEvent(event)


@contextmanager
def console_shutdown(app):
    """Let Windows console Ctrl+C wake Qt without Python signal polling."""
    if sys.platform != "win32":
        yield
        return

    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    # A pythonw launch has no console and needs no console handler.
    if not kernel32.GetConsoleCP():
        yield
        return

    handler_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)
    set_handler = kernel32.SetConsoleCtrlHandler
    set_handler.argtypes = (handler_type, wintypes.BOOL)
    set_handler.restype = wintypes.BOOL

    @handler_type
    def handle_control(event):
        if event in (0, 1):  # CTRL_C_EVENT / CTRL_BREAK_EVENT
            QMetaObject.invokeMethod(app, "quit", Qt.ConnectionType.QueuedConnection)
            return True  # Consume the event before Python raises KeyboardInterrupt.
        return False

    if not set_handler(handle_control, True):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        yield  # Keep the native callback alive until the event loop has exited.
    finally:
        set_handler(handle_control, False)


def main(argv=None):
    try:
        prepare_skin_directory()
    except OSError as error:
        app = QApplication(sys.argv)
        QMessageBox.critical(None, 'Desktop Coworker',
                             'Cannot create Asset/Template beside Desktop Coworker.\n'
                             'Move the EXE to a writable folder such as Desktop or Downloads '
                             'and try again.\n\n' + str(error))
        return 1
    parser = argparse.ArgumentParser(description='Desktop Coworker')
    parser.add_argument('--skin', default=DEFAULT_SKIN, choices=discover_skins())
    args = parser.parse_args(argv)
    app = QApplication(sys.argv)
    try:
        skin = Skin.load(args.skin)
    except ValueError as error:
        if getattr(sys, 'frozen', False):
            QMessageBox.critical(None, 'Desktop Coworker', str(error))
            return 1
        parser.error(str(error))
    window = CharacterWindow(skin)
    app.aboutToQuit.connect(window.deleteLater)
    window.show()
    with console_shutdown(app):
        return app.exec()


if __name__ == "__main__":
    sys.exit(main())
