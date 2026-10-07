"""Prevent PATH-provided third-party DLLs from contaminating PyInstaller builds."""
import ast
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


class BuildConfigurationTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == 'win32', 'Windows build configuration')
    def test_spec_removes_unrelated_dll_search_paths_before_analysis(self):
        spec = Path(__file__).resolve().parents[1] / 'DesktopCoworker.spec'
        module = ast.parse(spec.read_text())
        boundary = next(index for index, node in enumerate(module.body)
                        if isinstance(node, ast.Assign)
                        and any(isinstance(target, ast.Name) and target.id == 'root'
                                for target in node.targets))
        setup = ast.Module(body=module.body[:boundary], type_ignores=[])
        with patch.dict(os.environ, {'PATH': r'C:\Unrelated\Poppler;C:\Unrelated\Qt'}):
            exec(compile(setup, str(spec), 'exec'), {})
            entries = os.environ['PATH'].split(os.pathsep)
            self.assertFalse(any('Unrelated' in entry for entry in entries))
            self.assertIn(str(Path(os.environ['SystemRoot']) / 'System32'), entries)
            self.assertIn(sys.base_prefix, entries)
            self.assertIn(str(Path(sys.executable).parent), entries)
