"""Small derived image cache; source manifests and artwork stay untouched."""

import json
import sys
from functools import lru_cache

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QSaveFile, Qt
from PySide6.QtGui import QColor, QImage, QImageReader, QImageWriter


MAX_DIMENSION = 256
CACHE_VERSION = 1


@lru_cache(maxsize=1)
def webp_supported():
    if (b'webp' not in QImageWriter.supportedImageFormats()
            or b'webp' not in QImageReader.supportedImageFormats()):
        return False
    probe = QImage(3, 2, QImage.Format.Format_ARGB32)
    probe.fill(Qt.GlobalColor.transparent)
    probe.setPixelColor(0, 0, QColor(17, 83, 209, 255))
    probe.setPixelColor(1, 1, QColor(133, 27, 91, 71))
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    writer = QImageWriter(buffer, b'webp')
    writer.setQuality(100)  # Qt WebP's lossless mode.
    if not writer.write(probe):
        return False
    buffer.close()
    decoded = QImage.fromData(data)
    return (not decoded.isNull() and decoded.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
            == probe.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied))


def _write_image(path, image, format_name):
    output = QSaveFile(str(path))
    if not output.open(QIODevice.OpenModeFlag.WriteOnly):
        return False
    writer = QImageWriter(output, format_name.encode('ascii'))
    if format_name == 'webp':
        writer.setQuality(100)
    if not writer.write(image):
        output.cancelWriting()
        return False
    return output.commit()


def prepare_image(source, folder):
    """Read valid runtime data or prepare it once; return an optimized QImage."""
    relative = source.relative_to(folder.resolve())
    base = folder / '.runtime' / relative
    metadata = base.with_suffix(base.suffix + '.cache.json')
    stat = source.stat()
    signature = {'version': CACHE_VERSION, 'max_dimension': MAX_DIMENSION,
                 'transformation': 'fast', 'quality': 100,
                 'source_mtime_ns': stat.st_mtime_ns, 'source_size': stat.st_size}
    try:
        saved = json.loads(metadata.read_text(encoding='utf-8'))
        if saved['signature'] == signature and saved['format'] in ('webp', 'png'):
            cached = base.with_suffix('.' + saved['format'])
            if cached.stat().st_mtime_ns >= stat.st_mtime_ns:
                image = QImage(str(cached))
                if not image.isNull() and max(image.width(), image.height()) <= MAX_DIMENSION:
                    return image
    except (OSError, ValueError, KeyError, TypeError):
        pass

    image = QImage(str(source))
    if image.isNull():
        raise ValueError(f'Cannot load image: {source}')
    if max(image.width(), image.height()) > MAX_DIMENSION:
        image = image.scaled(MAX_DIMENSION, MAX_DIMENSION, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.FastTransformation)
    if getattr(sys, 'frozen', False):
        return image  # Bundled resources may be read-only; cache final frames in memory.
    try:
        base.parent.mkdir(parents=True, exist_ok=True)
        formats = ('webp', 'png') if webp_supported() else ('png',)
        for format_name in formats:
            cached = base.with_suffix('.' + format_name)
            if _write_image(cached, image, format_name):
                decoded = QImage(str(cached))
                if not decoded.isNull():
                    metadata.write_text(json.dumps({'signature': signature, 'format': format_name}),
                                        encoding='utf-8')
                    return decoded
    except OSError:
        pass  # Read-only skins can still use optimized frames in memory.
    return image
