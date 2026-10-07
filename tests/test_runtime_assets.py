import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QImage, QPainter

import runtime_assets
from runtime_assets import prepare_image, webp_supported
from skin import visible_bounds


class RuntimeAssetTests(unittest.TestCase):
    def test_frozen_build_prepares_in_memory_without_resource_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            source = folder / 'image.png'
            image = QImage(600, 400, QImage.Format.Format_ARGB32)
            image.fill(QColor(30, 40, 50, 91))
            self.assertTrue(image.save(str(source)))
            original = source.read_bytes()
            with patch.object(runtime_assets.sys, 'frozen', True, create=True), \
                    patch.object(Path, 'mkdir', side_effect=AssertionError('resource write')), \
                    patch('runtime_assets._write_image', side_effect=AssertionError('resource write')):
                output = prepare_image(source.resolve(), folder)
            self.assertEqual(output, image.scaled(256, 256, Qt.KeepAspectRatio, Qt.FastTransformation))
            self.assertFalse((folder / '.runtime').exists())
            self.assertEqual(source.read_bytes(), original)

    def test_large_image_cache_invalidation_and_original_preservation(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            source = folder / 'idle' / 'idle.png'
            source.parent.mkdir()
            original = QImage(1200, 800, QImage.Format.Format_ARGB32)
            original.fill(Qt.transparent)
            painter = QPainter(original)
            painter.fillRect(QRect(300, 200, 600, 400), QColor(23, 83, 149, 91))
            painter.end()
            self.assertTrue(original.save(str(source)))
            digest = hashlib.sha256(source.read_bytes()).digest()
            prepared = prepare_image(source.resolve(), folder)
            expected = original.scaled(256, 256, Qt.KeepAspectRatio, Qt.FastTransformation)
            self.assertEqual(prepared.size(), expected.size())
            self.assertLessEqual(max(prepared.width(), prepared.height()), 256)
            self.assertEqual(prepared.pixelColor(0, 0).alpha(), 0)
            self.assertEqual(prepared.pixelColor(128, 85), expected.pixelColor(128, 85))
            metadata = folder / '.runtime/idle/idle.png.cache.json'
            settings = json.loads(metadata.read_text())
            cached = folder / ('.runtime/idle/idle.' + settings['format'])
            timestamp = cached.stat().st_mtime_ns
            with patch('runtime_assets._write_image', side_effect=AssertionError('cache regenerated')):
                self.assertEqual(prepare_image(source.resolve(), folder), prepared)
            self.assertEqual(cached.stat().st_mtime_ns, timestamp)
            self.assertEqual(hashlib.sha256(source.read_bytes()).digest(), digest)
            # A newer source must regenerate even if its content is unchanged.
            os.utime(source, ns=(source.stat().st_atime_ns, timestamp + 1_000_000))
            with patch('runtime_assets._write_image', wraps=runtime_assets._write_image) as write:
                prepare_image(source.resolve(), folder)
                self.assertTrue(write.called)
            with patch('runtime_assets.CACHE_VERSION', 2), \
                    patch('runtime_assets._write_image', wraps=runtime_assets._write_image) as write:
                prepare_image(source.resolve(), folder)
                self.assertTrue(write.called)
            cached.write_bytes(b'broken')
            prepare_image(source.resolve(), folder)
            self.assertFalse(QImage(str(cached)).isNull())

    def test_png_fallback_small_image_and_writer_failure(self):
        for available in (False, True):
            with tempfile.TemporaryDirectory() as temporary:
                folder = Path(temporary)
                source = folder / 'image.png'
                image = QImage(17, 11, QImage.Format.Format_ARGB32)
                image.fill(QColor(30, 40, 50, 255))
                image.save(str(source))
                writer = runtime_assets._write_image
                def write(path, frame, format_name):
                    return False if format_name == 'webp' else writer(path, frame, format_name)
                with patch('runtime_assets.webp_supported', return_value=available), \
                        patch('runtime_assets._write_image', side_effect=write):
                    output = prepare_image(source.resolve(), folder)
                self.assertEqual(output, image)
                self.assertTrue((folder / '.runtime/image.png').is_file())

    def test_alpha_bounds_exact_including_low_alpha_and_row_padding(self):
        for format_name in (QImage.Format.Format_ARGB32, QImage.Format.Format_RGBA8888,
                            QImage.Format.Format_ARGB32_Premultiplied):
            image = QImage(7, 9, format_name)
            image.fill(Qt.transparent)
            image.setPixelColor(1, 2, QColor(0, 0, 0, 1))
            image.setPixelColor(5, 7, QColor(0, 0, 0, 255))
            self.assertEqual(visible_bounds(image), QRect(1, 2, 5, 6))
            image.fill(Qt.transparent)
            self.assertTrue(visible_bounds(image).isEmpty())
        opaque = QImage(7, 9, QImage.Format.Format_RGB32)
        opaque.fill(Qt.black)
        self.assertEqual(visible_bounds(opaque), QRect(0, 0, 7, 9))
        self.assertTrue(visible_bounds(QImage()).isEmpty())

    def test_available_webp_codec(self):
        self.assertIsInstance(webp_supported(), bool)
