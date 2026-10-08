# Desktop Coworker v0.1.1

A small desktop companion for Windows. This MVP asks: would you want to leave
this character running all day? It is a lightweight companion, not a full game.
Template is the only bundled skin and the default.

- **Idle:** rests between short walks.
- **Walk:** moves slowly left or right, staying inside the usable desktop.
- **Work:** sits after sustained recent computer activity, with a cooldown.
- **Sleep:** rests periodically, then wakes to idle.
- **React:** briefly reacts when the cursor enters its proximity zone.

The transparent, frameless character stays above normal windows. Left-drag to
move it between monitors; autonomous walking stays on the current monitor.
Lifting shows GRABBED; a horizontal pull shows CRY. Lifted release falls to the
monitor floor, with one small rebound and a brief sitting pose. Re-grabbing
cancels the motion; automatic movement stops during dragging. Right-click the character
and select **Quit Desktop Coworker** to exit. Development launches also support
Ctrl+C in the launching terminal.

## Run the Windows EXE

Download `DesktopCoworker-v0.1.1.exe` to a writable folder such as Downloads or
Desktop and double-click it. No Python installation or console is needed.
First launch creates `Asset/Template/` beside the EXE from bundled source artwork.
Later launches preserve existing files. Keep the EXE and its `Asset/` folder
together when moving an existing setup. Existing Template folders are preserved
on upgrade; back up and rename `Asset/Template/` before launching if you want
the updated bundled Template artwork and drag animations. A protected/read-only location produces
an error asking you to move the EXE to a writable folder.

Right-click the character and select **Quit Desktop Coworker** to exit.

## Run from source (Windows PowerShell)

Python 3.12 is the validated development version.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
# Optional explicit selection:
.\.venv\Scripts\python.exe main.py --skin template
```

Source assets resolve relative to the source modules. Packaged skins resolve
from `Asset/` beside the EXE. Neither depends on the current working directory.

## Custom skins

A skin is a folder containing a `skin.json` manifest and local images in
`idle/`, `walk/`, `sit/`, `sleep/`, and `react/`. Both pixel art and smooth
illustrations are supported. See [CUSTOM_SKINS.md](CUSTOM_SKINS.md) for the
structure and manifest example. There is no skin selector UI; use `--skin <id>`.
Behavior remains independent of the character artwork.

## Privacy and limitations

Windows-only MVP. Activity detection reads coarse last-input timing, and proximity
checks the current cursor position. No typed text, click history, application
names, window titles, clipboard contents, or global input hooks are collected.

- No settings, tray icon, saved position, sound, click reactions, or installer.
- Basic monitor fallback; advanced live display/taskbar-change recovery is not handled.
- Both walk directions share artwork; pose/facing variation is intentional.
- The small window must fit the usable screen; transparent areas inside it are
  not guaranteed to pass clicks through.
- Native Windows visual QA and local packaged EXE testing have been completed.
- Another-PC testing and long-running/all-day stability testing remain pending.

## Build the Windows x64 EXE

Use Windows x64 Python 3.12 and the project virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\build.ps1
```

The PyInstaller onefile/windowed spec reads the version from `main.__version__`;
the output is `dist/DesktopCoworker-v0.1.1.exe`. No release ZIP is needed.

## Development checks

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -m compileall -q main.py skin.py animation.py activity.py proximity.py runtime_assets.py tests
Remove-Item Env:QT_QPA_PLATFORM
```

Manual Windows checks: confirm transparency/always-on-top, drag toward every
edge, observe all five states and walk playback, then quit through the context
menu. Also test Ctrl+C from a console launch. Automated checks do not replace
native desktop and extended-use testing.

See [RELEASE_PREPARATION.md](RELEASE_PREPARATION.md) for source/release contents
and packaging requirements. `main.__version__` is the application version source.

## License

- Source code: [MIT License](LICENSE).
- Bundled assets: see [ASSET_LICENSE.md](ASSET_LICENSE.md).
