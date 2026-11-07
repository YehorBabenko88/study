# Canvas UX — issue #9

Base: `docs/study-architecture-v0.1`, `fdb540ffe63b4019cd95375b6806b0c8f455db29`.
Branch: `agent-c/canvas-ux-drafts`. No merge or deployment.

## Interaction

- Hold the left button on a card to move it. Split view paints both a floating preview and the moving source card. Escape, pointer cancellation and window blur cancel without a history entry.
- Drop an image card or a Lab image on a card to attach it. Hit testing uses painted DOM bounds and stacking order at the current scale. The source card and underlying files remain available. Completion is announced in the canvas status.
- Reorder gallery images by dragging a thumbnail, or use its left/right buttons. The × button removes that gallery reference only. Undo/Redo restores order, attachments, movement and removed links.
- “Предпросмотр композиции” opens an accessible modal without changing the board. “Объединить образы и связи” retains its legacy immediate creation behavior.
- Wheel pans; Shift+wheel pans horizontally; Ctrl/Meta+wheel zooms around the pointer. The header zoom buttons and “По центру” remain available. Fit measures offscreen cards before selecting a scale (20–300%).
- Tab to a card, Enter/Space selects it, arrows move it 10 units, Shift+arrows 50, Delete removes it. On the focused board, arrows pan, +/- zoom, Home fits. Ctrl/Meta+Z and Shift+Ctrl/Meta+Z undo/redo outside text inputs. Buttons provide link removal and transfer between panels, including the Lab sphere and current reference.

## Draft safety

Drafts are local to this browser and origin, not a cloud backup. JSON contains the board, title, asset references and viewport, never embedded image copies. A 450ms debounce and pagehide/visibility flush save committed edits. Existing server-save behavior is preserved.

Each server board has a separate key, `study.canvas.draft.v1:<board-id>`. Unsaved boards use `new`; explicitly recovered copies use a tab-selected unique slot. A pending draft blocks autosave until the user restores it, restores a new copy, or continues with the current board. Restoration never writes the server automatically.

The reader checks version, cardinality, IDs, types, coordinates, relations, gallery limits and viewport before applying a draft. Malformed/unknown versions remain untouched and can be downloaded. A previous version is saved before replacement, and the current in-memory board is backed up before recovery. Quota/storage failures are displayed and preserve the last good draft. Competing tabs pause autosave on a storage revision conflict. LocalStorage is not a transactional multi-user database; simultaneous writes within the same event-loop interval remain a limitation. Clearing browser storage removes local drafts; explicit server saves remain necessary for durable copies.

## Validation

Windows, Python 3.12.3, Playwright 1.64.1, Chromium 156 (headless), local server on `127.0.0.1:8879`.

```powershell
cd prototype
python -m pip install -r requirements.txt playwright
python -m playwright install chromium
python web_app.py
# In another shell; use 8766 with the standard server:
$env:STUDY_E2E_URL='http://127.0.0.1:8766'
python -m unittest discover -v
```

Full run: **117 tests, 0 failures/errors, 1 optional dependency skip**. All **5 original browser tests** and **18 new Playwright cases** passed. New cases cover exact bounds at scale .7/high DPI, both image-drop paths, actual thumbnail dragging, keyboard alternatives, movement/history, link removal/history, preview non-mutation, server gallery persistence, reload recovery, copy recovery, malformed JSON, competing tabs, quota failure and a 390×844 viewport. Regression tests failed before the respective fixes, including reviewer-found embedded attachment and offscreen Fit defects.

Desktop, mobile and preview screenshots were inspected using real uploaded PNGs. No JavaScript page errors were observed. Tests use synthetic gallery IDs where pixels are irrelevant; visual inspection and sphere-transfer tests use actual assets. Physical mouse/trackpad hardware, screen readers, Firefox/WebKit and external ComfyUI generation were not exercised. No CI workflow was present in the base; remote check status is reported separately in the PR.

## Integration

The route `/canvas-ux.js` in `web_app.py` is required for the new script. Preserve it when combining with API/security work. No schema migrations or existing asset deletions are included. Other agents own PDF OCR backend and shared CSRF bootstrap; coordinated follow-up wiring must preserve these routes and mutation headers.
