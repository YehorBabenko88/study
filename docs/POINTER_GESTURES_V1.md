# Study gesture interaction checkpoint — left mouse transfers and unlink

## Behavior
- In `/workspace`, press and hold the **left mouse button directly on a word/syllable/sentence/image card** in the free canvas. Move across the pane divider into 3D Lab and release in its composition area. The card's text is appended to the image prompt; existing image references are carried where available. No special drag handle is required.
- In 3D Lab, press the left button on the **sound sphere**, saved image preview, or ComfyUI output. Drag onto an existing card in the free canvas to attach the image to that card. Dropping onto empty canvas creates an image card. The server normalizes images as local PNG assets.
- The parent `/workspace` uses a transparent pointer overlay to capture movement across the two same-origin iframes and routes the drop to the correct child. A drag does not remove the source card; it transfers a copy/association.
- To detach a card from its graph neighbors, pull it quickly **away from connected nodes**. The experimental gesture requires >145 world units, <320 ms, >0.65 units/ms and an increase in distance to at least one neighbor >75 units. All edges touching that node are removed; the node itself is preserved. Undo restores links.
- Ordinary slow dragging moves cards and retains links. Click without movement should not reposition the card.
- Outside split view, ordinary single-canvas dragging still works.

## Tests
- `test_gesture_contracts.py`: static wiring/validation.
- `test_browser_gestures.py`: opt-in Playwright Chromium E2E for drag between panes, sphere-to-card, toggle and outward unlink logic. Requires running Study and Chromium Playwright installation; tests have not been executed on the user's Windows desktop.
- JavaScript syntax checked for canvas, Acoustic Studio and workspace.

## Run
```powershell
cd "$HOME\Desktop\study"
git pull --ff-only origin docs/study-architecture-v0.1
cd prototype
.\.venv\Scripts\python.exe -m unittest discover -v
.\.venv\Scripts\python.exe web_app.py
```
For optional real browser tests, in a separate PowerShell window:
```powershell
cd "$HOME\Desktop\study\prototype"
.\.venv\Scripts\python.exe -m pip install playwright
.\.venv\Scripts\python.exe -m playwright install chromium
$env:STUDY_E2E_URL="http://127.0.0.1:8766"
.\.venv\Scripts\python.exe -m unittest test_browser_gestures -v
```

## Limitations
- Pointer overlay works within the same-origin split workspace. Browser drag behavior needs physical Chromium acceptance.
- Image attachment is currently one primary asset per card; adding another replaces that card's asset reference. Future versions can support a layered gallery.
- Fling thresholds are provisional; calibrate on mouse/trackpad and screen scaling. No animation or haptic feedback yet.
- Current canvas uses approximate node hitboxes and off-screen culling, not exact DOM collision geometry.
- Avoid using fling to remove links on a production project until Undo/Redo and persistence are verified on Windows.
