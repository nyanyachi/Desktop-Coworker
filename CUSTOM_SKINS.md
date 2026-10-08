# Custom skins — Desktop Coworker v0.1.1

Place a skin folder directly under `Asset/` beside Template (legacy
`Asset/starter_candidates/` is also discovered). Its lowercase folder name must
match its manifest `id`. Paths inside the manifest are relative to the skin folder
and must not escape it. Launch from source with `python main.py --skin my_skin`.
For the onefile EXE, first launch creates an editable `Asset/Template/` beside
`DesktopCoworker-v0.1.1.exe`. Add `Asset/my_skin/` in that external directory,
then select it using `DesktopCoworker-v0.1.1.exe --skin my_skin` (or a Windows
shortcut with those arguments). Double-click without arguments always uses
Template. Existing Template files are never replaced automatically. Do not edit
PyInstaller's temporary extraction directory. No skin selector UI or installer
is implemented.

```text
Asset/my_skin/
    idle/idle_01.png
    walk/walk_01.png
    walk/walk_02.png
    walk/walk_03.png
    walk/walk_04.png
    sit/sit_01.png
    sleep/sleep_01.png
    react/react_01.png
    skin.json
```

Example `skin.json` (frame counts are flexible):

```json
{
  "id": "my_skin",
  "display_name": "My Skin",
  "rendering": {"scale_mode": "smooth"},
  "animations": {
    "IDLE": {"frames": ["idle/idle_01.png"], "frame_duration_ms": 400},
    "WALK_LEFT": {"frames": ["walk/walk_01.png", "walk/walk_02.png", "walk/walk_03.png", "walk/walk_04.png"], "frame_duration_ms": 180},
    "WALK_RIGHT": {"frames": ["walk/walk_01.png", "walk/walk_02.png", "walk/walk_03.png", "walk/walk_04.png"], "frame_duration_ms": 180},
    "WORK": {"frames": ["sit/sit_01.png"], "frame_duration_ms": 500},
    "SLEEP": {"frames": ["sleep/sleep_01.png"], "frame_duration_ms": 600},
    "REACT": {"frames": ["react/react_01.png"], "frame_duration_ms": 300}
  }
}
```

All six semantic animation keys are required. Each needs a nonempty ordered frame
list and positive integer `frame_duration_ms`. Single-frame sequences are static;
multiple frames loop. Animation timing does not change behavior-state duration.
The two walk directions can share frames; no automatic flipping is implemented.

`rendering.scale_mode` is optional: `pixel` is the default (nearest-neighbor),
while `smooth` scales original illustrations directly with smooth filtering.
Template uses `smooth`. Use transparent PNGs with visible content; fully
transparent or unreadable frames fail validation.

Optional `drag_visuals` maps `grabbed` and/or `cry` to a skin-relative image path
(static, backward-compatible) or an animation object:

```json
"drag_visuals": {
  "grabbed": {"frames": ["drag/grabbed_01.png", "drag/grabbed_02.png"], "frame_duration_ms": 700},
  "cry": "drag/cry_01.png"
}
```

Animation objects require a nonempty `frames` list and positive integer
`frame_duration_ms`. Multiple cached frames loop only while that drag pose is
active; one frame stays static without a running timer. Template uses two frames
per pose at 700 ms per frame. Mode changes restart playback; normal/CRY release stops it. GRABBED playback
continues during the fall and stops at landing.

Omit the section or either key to retain the normal appearance for that gesture.
Declared images must be readable and have visible content. They use the skin's
rendering mode, are alpha-cropped and individually fitted into 128 x 128, and
are cached separately. They never affect the normal animation scale. Drag poses
are temporary visual overrides, not behavior states; normal/CRY release removes
them, while a GRABBED release retains the visual until landing.

All normal animation frames share one scale fitting visible content into 128 x 128.
Transparent outer padding is cropped in memory. Frames are horizontally centered
and bottom-aligned with an 8-pixel margin in a 144 x 160 window. Final frames are
cached for playback; originals are never modified. Avoid inconsistent pose sizes
if you want a stable apparent character size.

Source pixel skins may generate ignored `.runtime/` files. Frozen builds do not
write generated caches into bundled resources; processed frames stay in memory.
