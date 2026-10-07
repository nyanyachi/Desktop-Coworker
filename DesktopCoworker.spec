# PyInstaller onefile/windowed build. Assets remain pristine inside the EXE seed.
import ast
import os
import sys
from pathlib import Path

# Do not collect unrelated DLLs from developer tools (e.g. Poppler ICU on PATH).
# PyInstaller's normal Qt hooks add the project's own PySide6 DLL directory.
windows = Path(os.environ['SystemRoot'])
os.environ['PATH'] = os.pathsep.join((str(Path(sys.executable).parent), sys.base_prefix,
                                    str(windows / 'System32'), str(windows)))
root = Path(SPECPATH)
module = ast.parse((root / 'main.py').read_text(encoding='utf-8'))
version = next(ast.literal_eval(node.value) for node in module.body
               if isinstance(node, ast.Assign)
               and any(isinstance(target, ast.Name) and target.id == '__version__'
                       for target in node.targets))
assets = root / 'Asset' / 'Template'
datas = [(str(path), str(Path('Asset/Template') / path.relative_to(assets).parent))
         for path in sorted(assets.rglob('*'))
         if path.is_file() and '.runtime' not in path.parts
         and path.suffix.lower() in ('.png', '.json')]
a = Analysis([str(root / 'main.py')], pathex=[str(root)], binaries=[], datas=datas,
             hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[],
             excludes=['pytest', 'unittest', 'tkinter'], noarchive=False)
pyz = PYZ(a.pure)
if os.environ.get('DESKTOP_COWORKER_ONEDIR') == '1':
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True,
              name=f'DesktopCoworker-v{version}', debug=False,
              bootloader_ignore_signals=False, strip=False, upx=False, console=False)
    collection = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False,
                         name=f'DesktopCoworker-v{version}')
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [],
              name=f'DesktopCoworker-v{version}', debug=False,
              bootloader_ignore_signals=False, strip=False, upx=False,
              console=False, disable_windowed_traceback=False)
