# Desktop Coworker v0.1.0 packaging

The distributable is one Windows x64 GUI executable, not a ZIP or onedir release.
Version source: `main.__version__`. Build configuration derives the artifact name
from that value.

## Reproduce the build

On Windows x64 with Python 3.12:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
$env:QT_QPA_PLATFORM = 'offscreen'
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -m compileall -q main.py skin.py runtime_assets.py animation.py activity.py proximity.py tests
Remove-Item Env:QT_QPA_PLATFORM
.\build.ps1
```

`DesktopCoworker.spec` uses PyInstaller onefile/windowed, no UPX, and bundles only
Template's manifest and original PNGs as first-run resources. Qt/Python runtime
libraries and plugins are collected by PyInstaller's hooks. Build dependencies
are pinned in `requirements-build.txt`; runtime dependencies stay separate.
Output: `dist/DesktopCoworker-v0.1.0.exe`. Build intermediates remain under ignored
`build/`. This is a reproducible configuration, not a claim of byte-identical builds.

## Resource and custom-skin contract

Bundled source artwork resides inside the EXE and is read through the frozen
module resource path. Runtime skin discovery uses `Asset/` beside `sys.executable`,
independent of the working directory. If external `Asset/Template/` is absent,
startup stages a complete copy before publishing it. Existing directories are
preserved, including user edits. Failed extraction shows a writable-folder error
and leaves no partial Template directory. No administrator privileges are needed
in a normal writable folder.

Users can add `Asset/<skin-folder>/skin.json` and images, then select the lowercase
skin ID with `--skin <id>` or a Windows shortcut. Template is the default on a
normal double-click. See `CUSTOM_SKINS.md`. Frozen builds keep generated frames
in memory and do not write `.runtime/` caches inside the bundled extraction area.

## Source repository and release contents

Keep the six application modules, `tests/`, Template's manifest/eight source PNGs,
README/custom-skin/release/project-state documents, `requirements.txt`,
`requirements-build.txt`, `DesktopCoworker.spec`, `build.ps1`, and `.gitignore`.
Ignore virtual environments, caches, logs, stackdumps and generated build output.

Publish only `DesktopCoworker-v0.1.0.exe` as the requested binary artifact. It must
not require a ZIP, a source checkout or a pre-created Asset directory. Do not
attach `.venv`, tests, project-state files, raw build trees or caches. On first run,
the application creates editable assets beside the downloaded EXE.

## Qt DLL packaging fix

Build PATH is restricted in the spec to the project Python environment and
Windows directories before dependency analysis. Normal PySide6 hooks supply
Qt DLL/plugin paths. This prevents unrelated developer tools from supplying
same-named incompatible DLLs: the failing build had collected Poppler's ICU 78
`icuuc.dll`, which lacked 20 unversioned ICU symbols required by Qt6Core. The
Windows system ICU exports all 20; it is an OS dependency, not copied manually.
All PySide6/shiboken packages matched at 6.11.2 and Qt files matched their wheels.
MSVC runtime files were bundled; no missing MSVC export was identified as the cause.

Use `.\build.ps1 -Onedir` for a clean diagnostic build under `build/onedir/`.
Use `.\build.ps1` for the final windowed onefile EXE under `dist/`. The script
clears PyInstaller analysis caches; remove stale build/dist output before a full
rebuild when diagnosing dependencies. No system or unrelated Qt DLLs are copied.

## Release validation

Use PROJECT_STATE.md for actual local build/smoke-test results. Another Windows PC
without Python still needs validation: direct launch, first-run extraction,
all states, transparency, dragging, right-click Quit, custom skins, second-run
preservation and a different working directory. Native CPU/GPU and all-day usage
also remain to be measured. No GitHub release has been created; next steps are
external-PC testing and authorized source commit/push/tag/release publication.
