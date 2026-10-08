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


__version__ = "0.1.1"


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
    REBOUND_HEIGHT_PX = 9
    REBOUND_DURATION_MS = 220
    LANDING_POSE_MS = 400
    FALL_TICK_MS = 16
    GRAVITY_PX_PER_SEC2 = 1800
    MAX_FALL_SPEED_PX_PER_SEC = 1200
    MOVEMENT_INTERVAL_MS = 40
    LIFT_THRESHOLD = 40  # Logical Qt pixels from the original press point.
    PULL_THRESHOLD = 40
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
        self._animation.frame_changed.connect(self._animation_changed)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._drag_offset = None
        self._rebounding = False
        self._rebound_started = 0.0
        self._landing = False
        self._drag_state_remaining = 1
        self._landing_timer = QTimer(self)
        self._landing_timer.setSingleShot(True)
        self._landing_timer.timeout.connect(self._finish_landing)
        self._falling = False
        self._fall_velocity = 0.0
        self._fall_y = 0.0
        self._fall_last_tick = 0.0
        self._fall_timer = QTimer(self)
        self._fall_timer.setInterval(self.FALL_TICK_MS)
        self._fall_timer.timeout.connect(self._fall_step)
        self._drag_origin = None
        self._drag_visual = None
        self._drag_frame_index = 0
        self._drag_animation_timer = QTimer(self)
        self._drag_animation_timer.timeout.connect(self._advance_drag_frame)
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
        if (self._drag_offset is not None or self._falling or self._landing or self._sleep_pending
                or time.monotonic() < self._react_allowed_at):
            return
        if self.state == BehaviorState.IDLE:
            self._enter_state(BehaviorState.REACT)
        elif self.state == BehaviorState.WALK:
            self._react_pending = True

    def _work_eligible(self):
        return self._activity.is_eligible and time.monotonic() >= self._work_allowed_at

    def _maybe_work(self):
        if (self.state == BehaviorState.IDLE and self._drag_offset is None and not self._falling and not self._landing
                and not self._sleep_pending and self._work_eligible()):
            self._enter_state(BehaviorState.WORK)

    def _start_awake_period(self):
        self._sleep_pending = False
        self._wake_pending = False
        self._awake_timer.start(random.randint(*self.AWAKE_DURATION_MS))

    def _sleep_due(self):
        self._awake_timer.stop()
        self._sleep_pending = True
        if self.state == BehaviorState.IDLE and self._drag_offset is None and not self._falling and not self._landing:
            self._enter_state(BehaviorState.SLEEP)

    def _enter_state(self, state: BehaviorState):
        self._state_timer.stop()
        self._movement_timer.stop()
        self.state = state
        if self._drag_offset is not None or self._falling or self._landing:
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
        if self._drag_offset is not None or self._falling or self._landing:
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
        if self._drag_offset is not None or self._falling or self._landing or self.state != BehaviorState.WALK:
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

    def _animation_changed(self):
        if self._drag_visual is None and not self._landing:
            self.update()

    def _select_drag_visual(self, pointer):
        displacement = pointer - self._drag_origin
        dx, dy = displacement.x(), displacement.y()
        mode = None
        if dy <= -self.LIFT_THRESHOLD and (
                self._drag_visual == 'grabbed' or abs(dy) >= abs(dx)):
            mode = 'grabbed'
        elif (dy > -self.LIFT_THRESHOLD and abs(dx) >= self.PULL_THRESHOLD
              and abs(dx) > abs(dy)):
            mode = 'cry'
        if mode not in self.skin.drag_visuals:
            mode = None
        self._set_drag_visual(mode)

    def _set_drag_visual(self, mode):
        if mode != self._drag_visual:
            self._drag_animation_timer.stop()
            self._drag_visual = mode
            self._drag_frame_index = 0
            if mode is not None:
                animation = self.skin.drag_visuals[mode]
                if len(animation.frames) > 1:
                    self._drag_animation_timer.start(animation.frame_duration_ms)
            self.update()

    def _advance_drag_frame(self):
        if self._drag_visual is None:
            return
        frames = self.skin.drag_visuals[self._drag_visual].frames
        self._drag_frame_index = (self._drag_frame_index + 1) % len(frames)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        image = (self.skin.visual('WORK') if self._landing else
                 self.skin.drag_visuals[self._drag_visual].frames[self._drag_frame_index]
                 if self._drag_visual is not None
                 else self._animation.frame)
        painter.drawPixmap((self.width() - image.width()) // 2,
                           self.height() - 8 - image.height(), image)

    def contextMenuEvent(self, event):
        self._context_menu.popup(event.globalPos())
        event.accept()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._landing:
                if self._rebounding:
                    self._fall_timer.stop()
                    self._rebounding = False
                self._landing_timer.stop()
                self._landing = False
                self.update()
            if self._falling:
                self._fall_timer.stop()
                self._falling = False
                self._fall_velocity = 0.0
                self._set_drag_visual(None)
            self._drag_origin = event.globalPosition().toPoint()
            self._drag_offset = self._drag_origin - self.pos()
            self._proximity.suspend()
            self._react_pending = False
            if self.state not in (BehaviorState.SLEEP, BehaviorState.WORK, BehaviorState.REACT):
                if self._state_timer.isActive():
                    self._drag_state_remaining = self._state_timer.remainingTime()
                self._state_timer.stop()
            self._movement_timer.stop()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_offset is not None:
            pointer = event.globalPosition().toPoint()
            self._select_drag_visual(pointer)
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
            self._drag_origin = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            if self._drag_visual == 'grabbed':
                self._start_fall()
            else:
                self._resume_after_drag()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def _start_fall(self):
        self._falling = True
        self._movement_timer.stop()
        self._fall_velocity = 0.0
        self._fall_y = float(self.y())
        self._fall_last_tick = time.monotonic()
        screen = self._living_screen()
        if screen is None or self.y() >= max(
                screen.availableGeometry().top(),
                screen.availableGeometry().bottom() - self.height() + 1):
            self._finish_fall()
        else:
            self._fall_timer.start()

    def _fall_step(self):
        if self._rebounding:
            self._rebound_step()
            return
        if not self._falling:
            return
        screen = self._living_screen()
        if screen is None:
            self._finish_fall()
            return
        available = screen.availableGeometry()
        floor = max(available.top(), available.bottom() - self.height() + 1)
        now = time.monotonic()
        elapsed = max(0.0, now - self._fall_last_tick)
        self._fall_last_tick = now
        self._fall_velocity = min(self.MAX_FALL_SPEED_PX_PER_SEC,
                                  self._fall_velocity + self.GRAVITY_PX_PER_SEC2 * elapsed)
        self._fall_y = min(float(floor), self._fall_y + self._fall_velocity * elapsed)
        self.move(clamp_position(QPoint(self.x(), round(self._fall_y)), self.size(), available))
        if self.y() >= floor:
            self._finish_fall()

    def _finish_fall(self):
        self._fall_timer.stop()
        self._falling = False
        self._fall_velocity = 0.0
        self._set_drag_visual(None)
        self._landing = True
        self.update()
        self._rebounding = True
        self._rebound_started = time.monotonic()
        self._fall_timer.start()  # Reuse the motion timer only for this short cosmetic arc.

    def _rebound_step(self):
        if not self._rebounding:
            return
        screen = self._living_screen()
        if screen is None:
            self._finish_rebound()
            return
        area = screen.availableGeometry()
        floor = max(area.top(), area.bottom() - self.height() + 1)
        progress = min(1.0, max(0.0, (time.monotonic() - self._rebound_started)
                                * 1000 / self.REBOUND_DURATION_MS))
        offset = 4 * self.REBOUND_HEIGHT_PX * progress * (1 - progress)
        self.move(clamp_position(QPoint(self.x(), floor - round(offset)), self.size(), area))
        if progress >= 1.0:
            self._finish_rebound()

    def _finish_rebound(self):
        self._fall_timer.stop()
        self._rebounding = False
        self._landing_timer.start(self.LANDING_POSE_MS)

    def _finish_landing(self):
        if not self._landing or self._rebounding:
            return
        self._landing_timer.stop()
        self._landing = False
        self.update()
        if self.state in (BehaviorState.IDLE, BehaviorState.WALK):
            self._proximity.resume()
            if self._sleep_pending:
                self._advance_state()
            else:
                # Resume the paused lifecycle without selecting/resetting a state.
                self._state_timer.start(max(1, self._drag_state_remaining))
                if self.state == BehaviorState.WALK:
                    self._movement_timer.start()
        else:
            self._resume_after_drag()

    def _resume_after_drag(self):
        """Resume the same deferred-expiry rules after release or landing."""
        self._set_drag_visual(None)
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
