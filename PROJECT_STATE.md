# Desktop Coworker — Project State

## Release Status

**Desktop Coworker v0.1.0 release candidate.** Version source:
`main.__version__ = "0.1.0"`. Template is the only bundled/default skin.
A Windows x64 PyInstaller onefile/windowed EXE has been built at
`dist/DesktopCoworker-v0.1.0.exe` (58,832,669 bytes). No ZIP or GitHub release
has been created. Another-PC validation remains pending.

## MVP Goal

A lightweight desktop companion, not a full game. Validate: “Would the user
want to leave this character running all day?”

## Implemented Behavior States

- **IDLE:** stationary; initial state and normal return state.
- **WALK:** randomly chooses left/right, moves horizontally, stops at duration
  expiry or a usable-screen edge.
- **WORK:** stationary sitting pose after sustained recent computer activity;
  session completion starts a cooldown.
- **SLEEP:** stationary dedicated sleep pose after a randomized awake period;
  waking enters IDLE and schedules a fresh awake period.
- **REACT:** brief stationary dedicated reaction pose on cursor proximity entry;
  completion starts a cooldown.

## Current Timing / Threshold Values

Ranges are randomized; cooldowns begin when the corresponding session ends.

| Value | Current implementation |
|---|---|
| IDLE duration | 8–16 seconds |
| WALK duration | 2–4 seconds |
| WALK step / update | 1 pixel every 40 ms; nominally 25 pixels/second |
| Awake period before sleep is due | 60–120 seconds |
| SLEEP duration | 10–20 seconds |
| Activity sampling | 1,000 ms |
| Recent-input window | Last input at most 3 seconds ago |
| WORK sustained activity | 5 seconds of consecutive recent samples |
| Activity sampling gap reset | Gap greater than 2.5 seconds restarts sustained observation |
| WORK duration / cooldown | 15–30 seconds / 30–60 seconds |
| REACT duration / cooldown | 1.5–3 seconds / 5–10 seconds |
| Proximity sampling | 250 ms |
| Proximity margin | 80 pixels outside each side of the current window rectangle |

## State Priority / Transition Rules

- Normal awake lifecycle alternates IDLE and WALK; activity/proximity may enter
  WORK/REACT immediately from IDLE when permitted.
- WALK is not interrupted by WORK, REACT, or the sleep deadline. At completion
  (including an edge): **due SLEEP → pending REACT → eligible WORK → IDLE**.
- WORK requires sustained activity and an expired cooldown. Eligibility is
  checked on activity samples and safe transitions; isolated input is insufficient.
- Proximity queues at most one REACT during WALK. It remains pending even if
  the cursor leaves; dragging or entering WORK/SLEEP discards it.
- WORK/SLEEP ignore proximity. Entries during REACT or its cooldown are not queued.
- WORK and REACT count as awake time. Sleep due during either waits for session
  completion, then wins; otherwise each returns to IDLE, never directly to WALK.
- SLEEP is never interrupted by WORK/REACT. Waking always enters IDLE first.
- One-shot behavior/awake timers and monotonic cooldown deadlines are reused;
  no behavior busy loop or frame counting is used.

## Architecture

- `main.py`: `BehaviorState`, `CharacterWindow`, transitions/deadlines, movement,
  dragging/clamping, rendering cached frames, CLI, version constant, Quit menu
  and Windows console shutdown.
- `skin.py`: manifest discovery/validation, image loading, alpha cropping,
  shared skin scale, cached `Animation` frame sequences.
- `runtime_assets.py`: prepares and reuses derived images under each skin's
  `.runtime/` directory; source artwork and manifest paths remain untouched.
- `animation.py`: `AnimationPlayer`; semantic selection resets to frame 0,
  multi-frame sequences loop, single-frame sequences stop the animation timer.
- `activity.py`: Windows `GetLastInputInfo`/`GetTickCount` via ctypes, coarse
  idle seconds and sustained-activity eligibility. Unsupported platforms and
  failed input queries return inactive. No hooks or input contents are collected.
- `proximity.py`: `ProximityMonitor`; `QCursor.pos()` and current window geometry
  yield entry events. No mouse hooks or position history.
- `Asset/Template/skin.json`: bundled skin definition and PNG assets; additional
  skins can also be discovered under `Asset/starter_candidates/`.
- `tests/`: activity, proximity, behavior, skin, animation, and console-shutdown tests.
- `requirements.txt`: PySide6 only (`>=6.7,<7`); Python application.

## Rendering / Window

One fixed **144 × 160** PySide6 QWidget, translucent, frameless, always-on-top,
with the Tool flag. No full-screen overlay; other applications remain interactive
outside this small window. Starts 24 pixels from the primary usable area's
bottom/right edges, clamped to fit.

Pixel-mode source images are prepared once as runtime canvases with a maximum
dimension of **256 pixels**, preserving aspect ratio/transparency with
`FastTransformation`; smaller images are never upscaled during preparation.
Lossless WebP is preferred after a Qt encode/decode check, with optimized PNG
fallback. `.runtime/` mirrors source subdirectories and is ignored by Git.
Per-image metadata records generation version/settings, source size and nanosecond
mtime. Missing/stale/corrupt caches or changed settings regenerate only that image.
Read-only source skin directories use prepared images in memory without persistence.
Frozen builds (`sys.frozen`) never write generated runtime caches into resources;
pixel preparation stays in memory. Smooth Template already has no disk writes.
Source resources resolve relative to `skin.py`; frozen skin discovery uses
external `Asset/` beside the EXE. First launch stages/copies bundled Template
there only if absent; existing user files are preserved. Failure to create the
external folder produces a writable-folder error. Neither path uses the CWD.

Optional manifest `rendering.scale_mode` accepts `pixel` (default) or `smooth`.
Pixel-mode custom skins use `FastTransformation`. Template uses `smooth`: original
full-resolution images bypass the 256-pixel runtime cache, are alpha-cropped,
and scale directly once to the final size with `SmoothTransformation`. Final
pixmaps are cached in memory for playback; originals are decoded again on startup.
This avoids losing illustration details in an intermediate nearest-neighbor resize.

At load time, alpha greater than zero determines visible bounds on selected images;
Qt Alpha8 conversion plus direct byte-row operations replaces the slow Python
`pixelColor()` nested scan, including exact low-alpha and fully transparent handling.
Transparent
padding is cropped in memory. One factor across **all referenced frames** fits
maximum visible width/height within **128 × 128**. Aspect ratio is preserved;
The configured transformation preserves pixel edges or smooth illustration details. Frames are centered horizontally
and bottom-aligned with an **8-pixel margin**. Original artwork is unchanged;
playback swaps cached pixmaps without file reads, cropping, or scaling per frame.
Fully transparent or broken frames produce clear startup errors.

## Skins

The only bundled/default skin is **`template`**. Select with `--skin`;
invalid IDs fail with a usage error. Paths resolve relative to the application.
Manifests define `id`, `display_name`, and `animations` entries with ordered
`frames` and positive integer `frame_duration_ms`. Required semantic keys are
IDLE, WALK_LEFT, WALK_RIGHT, WORK, SLEEP, REACT. Legacy `visuals` single-image
mapping is supported with all six keys (400 ms metadata per static visual).

Template prototype skin added at `Asset/Template/skin.json` with ID `template`;
manual Windows visual verification is pending. Discovery supports skin folders
directly under `Asset/` as well as `Asset/starter_candidates/`, using lowercase
folder IDs. Behavior remains character-independent.
Template smooth rendering and offscreen CLI launch/render/Qt shutdown pass;
all eight source PNG hashes remain unchanged. Existing Template runtime files are
ignored in smooth mode; manual Windows visual verification remains pending.

All current manifests use:

| Semantic animation | Assets relative to skin folder | Frame duration |
|---|---|---|
| IDLE | `idle/idle_01.png` | 400 ms |
| WALK_LEFT / WALK_RIGHT | `walk/walk_01.png` through `walk_04.png` | 180 ms |
| WORK | `sit/sit_01.png` (sitting fallback for work) | 500 ms |
| SLEEP | `sleep/sleep_01.png` | 600 ms |
| REACT | `react/react_01.png` | 300 ms |

Only WALK has multiple frames. Left/right share the sequence; there is no flipping.
**Behavior must remain character-independent:** no skin IDs, asset paths, frame
counts, animation timings, or character-specific offsets in behavior logic.

## Interaction

Left-button dragging clamps the whole window to the current screen's available
geometry and suppresses autonomous movement. IDLE/WALK release returns to fresh
IDLE unless sleep is due. WORK/SLEEP/REACT retain their deadlines during dragging;
expiry is deferred until release. Dragging does not wake sleeping characters.

Right-click opens a context menu with one action, **Quit Desktop Coworker**.
It does not initiate dragging or change behavior state. The action calls Qt's
application quit path, providing user-accessible shutdown for packaged builds
without a console. Normal behavior timers continue while the menu is open.
On application shutdown the window is scheduled for deletion, destroying its
owned menu, movement/animation/state/awake timers and activity/proximity monitors;
the existing console-handler context unregisters the handler after the loop exits.

Proximity requires outside-to-inside entry; starting/staying nearby does not react.
Dragging suspends detection and clears pending REACT. After release, a sampled
leave and re-entry are required. Windows Ctrl+C/Ctrl+Break is consumed by a native
console handler that queues Qt quit; no KeyboardInterrupt traceback or shutdown
polling timer is needed. Alt+F4 also closes the focused window.

## Current Validation

The test suite now targets the sole bundled Template skin. Behavior and animation
checks use discovered skins; generic loader/render-mode/cache tests use temporary
synthetic images/manifests rather than deleted bundled assets. Template checks
cover all six semantic keys, four walk frames, shared scaling, smooth rendering,
frame caching, source preservation and bottom alignment. Pixel default/explicit
modes and runtime cache generation/reuse/invalidation remain tested independently.

Right-click state/timer preservation, left dragging, no-console Quit in all five
states, owned-resource destruction, and real Windows Ctrl+C including dragging
are covered. Mixed-cycle QA checks 500 rounds with stable timer identities/frame
keys; Template adds 500 drag/deferred-expiry cases with no image reprocessing.
All **43 tests pass**, including first-run extraction and build-PATH isolation;
syntax compilation passes.
Default and explicit Template launches from a different working directory quit
cleanly through the menu action. Frozen pixel-preparation tests confirm no writes
to resource directories; source PNGs and rendering remain unchanged. The duplicate
character-specific behavior class was removed; the remaining state-machine cases
run against a discovered bundled skin. The approved default-skin constant now
selects `template`; no other production behavior, timings or rendering changed.

Native Windows menu appearance, Template visual quality, GPU/compositor usage,
and all-day stability still require manual testing. Short offscreen checks do
not establish long-running native performance. Ctrl+C before handler registration
during startup uses Python's default handling.

## Packaged QtCore Fix / Local Smoke Test

Versions: Python 3.12.0 x64, PyInstaller 6.22.3, hooks 2026.8;
PySide6, Essentials, Addons and shiboken6 all match at 6.11.2.
The failed bundle contained Poppler ICU 78 from the host PATH. Its `icuuc.dll`
lacked 20 unversioned ICU functions imported by Qt6Core; Windows system ICU
exports all 20. Qt/PySide/shiboken files matched their installed wheels, so no
package-version repair was needed. Bundled MSVC runtimes were not the cause.

`DesktopCoworker.spec` now restricts dependency-analysis PATH to the project
Python environment and Windows directories. Standard PySide6 hooks collect Qt
DLLs/plugins. Completely cleaned build/dist and PyInstaller analysis caches;
validated temporary onedir first (`build.ps1 -Onedir`), then final onefile.
No application behavior/state/rendering/timing code changed for this DLL fix.

Both builds launch without the QtCore error. User confirmed visible rendering
and Quit closing the window. The final onefile was copied alone into
`build/clean-machine-smoke/`, launched with a different empty CWD and no development
Python/Qt paths, and created nine byte-identical external Template files.
A second `--help` invocation exited 0 and preserved all asset hashes/mtimes.
Archive checks: x64 GUI subsystem, matching wheel Qt files, qwindows/qwebp
plugins and app-local MSVC runtime files present; incompatible ICU absent.

GUI process disappearance was not verified: test process IDs remained after the
user-reported window closure and were explicitly cleaned up. Do not interpret
this as a full normal-shutdown pass. Native animation/dragging and GUI process
exit need final manual confirmation, plus another-PC/no-Python validation.
The exact DLL startup failure is resolved; no separate VC++ installation was
needed locally. Windows system ICU/UCRT remain OS dependencies.

## Known Limitations / Not Yet Implemented

- Windows-targeted MVP; unsupported systems have no activity-driven WORK and
  the custom console shutdown handler is Windows-only.
- No advanced multi-monitor/display-change recovery; usable screen must fit
  the window. Qt timer delays under load make movement speed nominal.
- Prototype walk artwork varies in pose size/facing; no manual correction,
  directional flipping, blending, or independent directional sequences.
- No alpha hit-testing/pixel-perfect click-through, click reactions, petting,
  wake-on-click, cursor following, sound, bubbles, or notifications.
- No settings/tray UI, persistence, installer, productivity tracking, app-specific
  behavior, key logging, global hooks, needs/stats, or day/night system.
- All-day usefulness and timing comfort still require extended manual use.

## Last Completed Task

QtCore packaging DLL bug fix; onedir and onefile local launches verified.

## Next Phase

Finish native GUI process-exit/animation/drag QA and test the final EXE on another
Windows PC, then authorized GitHub v0.1.0 source/tag/release publication. Preserve
current behavior/timings.
Continue native visual QA and long-running real-world usage testing.
See `RELEASE_PREPARATION.md` for source/ZIP contents and packaging requirements;
`CUSTOM_SKINS.md` documents the manifest and render modes.
