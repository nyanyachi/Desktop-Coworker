"""First-run extraction keeps bundled resources separate from editable assets."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import skin
import main


class PackagedSkinTests(unittest.TestCase):
    def test_source_launch_never_extracts(self):
        with patch.object(skin.sys, 'frozen', False, create=True), \
                patch('skin.shutil.copytree', side_effect=AssertionError('source extraction')):
            skin.prepare_skin_directory()

    def test_first_run_extracts_once_and_discovers_external_custom_skin(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            bundle = base / 'bundle'
            seed = bundle / 'Asset' / 'Template'
            seed.mkdir(parents=True)
            (seed / 'skin.json').write_text('{"id": "template"}')
            (seed / '.runtime').mkdir()
            (seed / '.runtime' / 'ignored.png').write_bytes(b'cache')
            external = base / 'portable' / 'Asset'
            with patch.object(skin.sys, 'frozen', True, create=True), \
                    patch.object(skin, '__file__', str(bundle / 'skin.py')), \
                    patch.object(skin, 'SKIN_ROOT', external / 'starter_candidates'):
                skin.prepare_skin_directory()
                manifest = external / 'Template' / 'skin.json'
                self.assertEqual(manifest.read_text(), '{"id": "template"}')
                self.assertFalse((external / 'Template' / '.runtime').exists())
                manifest.write_text('user modified')
                with patch('skin.shutil.copytree', side_effect=AssertionError('overwrite')):
                    skin.prepare_skin_directory()
                self.assertEqual(manifest.read_text(), 'user modified')
                custom = external / 'MySkin'
                custom.mkdir()
                (custom / 'skin.json').write_text(json.dumps({'id': 'myskin'}))
                self.assertEqual(skin.discover_skins(skin.SKIN_ROOT), ['myskin', 'template'])

    def test_failed_extraction_does_not_publish_partial_template(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'Asset' / 'starter_candidates'
            with patch.object(skin.sys, 'frozen', True, create=True), \
                    patch.object(skin, 'SKIN_ROOT', root), \
                    patch('skin.shutil.copytree', side_effect=PermissionError('denied')):
                with self.assertRaises(PermissionError):
                    skin.prepare_skin_directory()
            self.assertFalse((root.parent / 'Template').exists())
            self.assertEqual(list(root.parent.iterdir()), [])

    def test_unwritable_assets_report_a_user_facing_error(self):
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        with patch('main.prepare_skin_directory', side_effect=PermissionError('denied')), \
                patch('main.QApplication', return_value=app), \
                patch('main.QMessageBox.critical') as message:
            self.assertEqual(main.main([]), 1)
        self.assertIn('writable folder', message.call_args.args[2])
