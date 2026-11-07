# Infinite Canvas v0.2 — interaction and integration checkpoint

Implemented in Draft PR #1:
- Free pan/zoom, typed word/syllable/sentence/note/image nodes, directed edges and manual syllable splitting.
- Multi-paragraph text input, up to 500 tokens per operation to reduce browser stalls.
- Undo/redo snapshot history (40 operations); Ctrl+Z/Ctrl+Shift+Z outside text inputs.
- Corrected selection so dragging a card does not destroy the captured pointer target.
- A larger, bounded 4 MB board-save request body instead of the old 16 KB limit.
- Attach an existing mnemonic scene as an image node; show its saved PNG or fall back to SVG.
- Validate UUID scene references and reject non-finite node coordinates on the server.
- Existing SQLite boards and mnemonic scenes remain separate and reusable.

## Smoke checks on Windows
```powershell
cd "$HOME\Desktop\study"
git pull --ff-only origin docs/study-architecture-v0.1
cd prototype
.\.venv\Scripts\python.exe -m unittest discover -v
.\.venv\Scripts\python.exe web_app.py
```
Open `http://127.0.0.1:8766/canvas`. Create and drag nodes; connect two; undo and redo; paste a paragraph; attach an existing mnemonic; save and reopen. Verify image PNG/SVG fallback and original Study `/` still work.

## Important unfinished work
This is not yet a production-ready large-document canvas: DOM nodes are not virtualized, so thousands of simultaneous cards can be slow. No auto-layout, semantic grouping, visual edge editing, full keyboard navigation, AR/VR, collaborative synchronization, actual image generation or grammatical parsing. No automatic corpus ingestion has been run, and the lexicon remains empty until the user imports licensed dumps. The Argos installation log shows no installed language packs; an explicit pivot installer exists but has not been run. No physical Windows acceptance of this checkpoint has been reported.

Next gates: browser E2E tests (Playwright), virtualized rendering, robust import/export and backups, sense-aware morphology, source-audited dictionary acquisition, translation model validation, and a production database migration. Do not declare the full mission complete.
