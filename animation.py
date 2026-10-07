"""Timer-driven playback of cached frames, separate from behavior."""

from PySide6.QtCore import QObject, QTimer, Signal


class AnimationPlayer(QObject):
    frame_changed = Signal()

    def __init__(self, skin, parent=None):
        super().__init__(parent)
        self.skin = skin
        self.key = None
        self.frame_index = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._advance_frame)

    def select(self, key):
        if key == self.key:
            return
        self.timer.stop()
        self.key = key
        self.frame_index = 0
        animation = self.skin.animations[key]
        if len(animation.frames) > 1:
            self.timer.start(animation.frame_duration_ms)
        self.frame_changed.emit()

    def _advance_frame(self):
        frames = self.skin.animations[self.key].frames
        self.frame_index = (self.frame_index + 1) % len(frames)
        self.frame_changed.emit()

    @property
    def frame(self):
        return self.skin.animations[self.key].frames[self.frame_index]
