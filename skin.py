"""Load and cache skin animation frames independently of desktop behavior."""

import json
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QImage, QPixmap

from runtime_assets import prepare_image


APPLICATION_DIR = (Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False)
                   else Path(__file__).resolve().parent)
SKIN_ROOT = APPLICATION_DIR / 'Asset' / 'starter_candidates'
DEFAULT_SKIN = 'template'
VISUAL_KEYS = ('IDLE', 'WALK_LEFT', 'WALK_RIGHT', 'SLEEP', 'WORK', 'REACT')


def prepare_skin_directory():
    """Seed an editable Template beside the EXE once, without replacing user files."""
    if not getattr(sys, 'frozen', False):
        return
    assets = SKIN_ROOT.parent
    target = assets / 'Template'
    if target.is_dir():
        return
    bundled = Path(__file__).resolve().parent / 'Asset' / 'Template'
    assets.mkdir(parents=True, exist_ok=True)
    # Publish only a complete copy; failed extraction must not leave a partial skin.
    with tempfile.TemporaryDirectory(prefix='.template-', dir=assets) as temporary:
        staged = Path(temporary) / 'Template'
        shutil.copytree(bundled, staged, ignore=shutil.ignore_patterns('.runtime', '__pycache__', '*.pyc'))
        try:
            staged.rename(target)
        except FileExistsError:
            if not target.is_dir():
                raise


def _skin_folders(root):
    manifests = list(root.glob('*/skin.json'))
    if root == SKIN_ROOT:
        manifests.extend(root.parent.glob('*/skin.json'))
    return {path.parent.name.lower(): path.parent for path in manifests}


def discover_skins(root=SKIN_ROOT):
    return sorted(_skin_folders(root))


def visible_bounds(image):
    """Find all nonzero-alpha pixels, once at load time."""
    if image.isNull():
        return QRect()
    left, top = image.width(), image.height()
    right = bottom = -1
    alpha = image.convertToFormat(QImage.Format.Format_Alpha8)
    data = bytes(alpha.constBits())
    stride = alpha.bytesPerLine()
    for y in range(image.height()):
        row = data[y * stride:y * stride + image.width()]
        trimmed = row.strip(b'\x00')
        if trimmed:
            left = min(left, len(row) - len(row.lstrip(b'\x00')))
            right = max(right, len(row.rstrip(b'\x00')) - 1)
            top, bottom = min(top, y), y
    return QRect(left, top, right - left + 1, bottom - top + 1) if right >= 0 else QRect()


@dataclass(frozen=True)
class Animation:
    frames: tuple
    frame_duration_ms: int


class Skin:
    def __init__(self, skin_id, display_name, animations, scale_mode='pixel', drag_visuals=None):
        self.id = skin_id
        self.display_name = display_name
        self.animations = animations
        self.scale_mode = scale_mode
        self.drag_visuals = drag_visuals if drag_visuals is not None else {}

    @classmethod
    def load(cls, skin_id=DEFAULT_SKIN, size=QSize(128, 128), root=SKIN_ROOT):
        if skin_id not in discover_skins(root):
            raise ValueError(f"Unknown skin {skin_id!r}. Available: {', '.join(discover_skins(root))}")
        folder = _skin_folders(root)[skin_id]
        try:
            manifest = json.loads((folder / 'skin.json').read_text(encoding='utf-8'))
            if manifest['id'] != skin_id:
                raise ValueError('Manifest id must match its folder name')
            display_name = manifest['display_name']
            if not isinstance(display_name, str) or not display_name.strip():
                raise ValueError('display_name must be a nonempty string')
            rendering = manifest.get('rendering', {})
            if not isinstance(rendering, dict):
                raise ValueError('rendering must be an object')
            scale_mode = rendering.get('scale_mode', 'pixel')
            if scale_mode not in ('pixel', 'smooth'):
                raise ValueError('rendering.scale_mode must be pixel or smooth')
            transformation = (Qt.TransformationMode.SmoothTransformation if scale_mode == 'smooth'
                              else Qt.TransformationMode.FastTransformation)
            sources = {}
            paths = {}
            durations = {}
            for key in VISUAL_KEYS:
                try:
                    if 'animations' in manifest:
                        definition = manifest['animations'][key]
                        frames = definition['frames']
                        duration = definition['frame_duration_ms']
                    else:
                        frames = [manifest['visuals'][key]]
                        duration = 400
                    if not isinstance(frames, list) or not frames:
                        raise ValueError('frames must be a nonempty list')
                    if type(duration) is not int or duration <= 0 or duration > 2_147_483_647:
                        raise ValueError('frame_duration_ms must be a positive Qt timer integer')
                    durations[key] = duration
                    paths[key] = []
                    for filename in frames:
                        if not isinstance(filename, str) or not filename:
                            raise ValueError('frame paths must be nonempty strings')
                        path = (folder / filename).resolve()
                        if not path.is_relative_to(folder.resolve()):
                            raise ValueError('Visual paths must stay inside the skin folder')
                        if path not in sources:
                            # Illustrations must reach the final size directly from the original.
                            image = (QImage(str(path)) if scale_mode == 'smooth'
                                     else prepare_image(path, folder))
                            if image.isNull():
                                raise ValueError(f'Cannot load image: {path}')
                            bounds = visible_bounds(image)
                            if bounds.isEmpty():
                                raise ValueError(f'Image is fully transparent: {path}')
                            sources[path] = QPixmap.fromImage(image.copy(bounds))
                        paths[key].append(path)
                except (OSError, ValueError, KeyError, TypeError) as error:
                    raise ValueError(f'{key}: {error}') from error
            # One factor across all states avoids normalizing each pose separately.
            factor = min(size.width() / max(image.width() for image in sources.values()),
                         size.height() / max(image.height() for image in sources.values()))
            cache = {}
            for path, image in sources.items():
                target = QSize(max(1, round(image.width() * factor)),
                               max(1, round(image.height() * factor)))
                cache[path] = image.scaled(target, Qt.AspectRatioMode.KeepAspectRatio,
                                          transformation)
            animations = {key: Animation(tuple(cache[path] for path in sequence), durations[key])
                          for key, sequence in paths.items()}
            # Interaction artwork never participates in the normal shared scale.
            definitions = manifest.get('drag_visuals', {})
            if not isinstance(definitions, dict):
                raise ValueError('drag_visuals must be an object')
            drag_visuals = {}
            drag_cache = {}
            for mode, definition in definitions.items():
                if mode not in ('grabbed', 'cry'):
                    raise ValueError(f'Unknown drag visual: {mode}')
                if isinstance(definition, str):
                    frames, duration = [definition], 300
                elif isinstance(definition, dict):
                    frames = definition['frames']
                    duration = definition['frame_duration_ms']
                else:
                    raise ValueError('Drag visuals must be paths or animation objects')
                if not isinstance(frames, list) or not frames:
                    raise ValueError('Drag frames must be a nonempty list')
                if type(duration) is not int or not 0 < duration <= 2_147_483_647:
                    raise ValueError('Drag frame_duration_ms must be a positive Qt timer integer')
                sequence = []
                for filename in frames:
                    if not isinstance(filename, str) or not filename:
                        raise ValueError('Drag visual paths must be nonempty strings')
                    path = (folder / filename).resolve()
                    if not path.is_relative_to(folder.resolve()):
                        raise ValueError('Drag visual paths must stay inside the skin folder')
                    if path not in drag_cache:
                        image = (QImage(str(path)) if scale_mode == 'smooth'
                                 else prepare_image(path, folder))
                        if image.isNull():
                            raise ValueError(f'Cannot load drag image: {path}')
                        bounds = visible_bounds(image)
                        if bounds.isEmpty():
                            raise ValueError(f'Drag image is fully transparent: {path}')
                        drag_cache[path] = QPixmap.fromImage(image.copy(bounds)).scaled(
                            size, Qt.AspectRatioMode.KeepAspectRatio, transformation)
                    sequence.append(drag_cache[path])
                drag_visuals[mode] = Animation(tuple(sequence), duration)
            return cls(skin_id, display_name, animations, scale_mode, drag_visuals)
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise ValueError(f'Invalid skin {skin_id!r}: {error}') from error

    def visual(self, key):
        """First-frame access for callers using the original static-skin API."""
        return self.animations[key].frames[0]
