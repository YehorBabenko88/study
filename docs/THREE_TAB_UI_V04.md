# Study simplified three-tab navigation — v0.4

## User-facing architecture
1. **Начало** (`/`): choose a book-page image for local OCR, record voice, or load a browser-supported audio file. Review/edit text, name a project and save to the shared speech project store; continue to the free canvas.
2. **Свободная доска** (`/canvas`): all word/syllable/letter/sentence/image/action graph construction, OCR text, speech projects and mnemonic images.
3. **3D Lab** (`/phonovision-3d`): microphone recording, playback, speech recognition, acoustic sphere, sound transformations, glTF export, and an expandable spectral relief panel. The relief is embedded from the existing renderer, not yet refactored into a single shared audio engine.

All three pages use the same sticky top navigation and active tab highlight. Legacy pages are no longer in the primary navigation, but their code/data are preserved for migration:
- `/legacy-study` old lexicon and mnemonic interface
- `/legacy-board` old card board
- `/legacy-spectral-relief` spectral renderer embedded in 3D Lab
- `/acoustic-studio` alias of 3D Lab

## Limits and caveats
The user requested unlimited recording and file sizes. **No browser/server can safely promise unbounded input.** This checkpoint keeps bounded processing: browser audio import 50 MB, in-memory audio preview/recording up to 8 seconds, local shared WAV <=2 MB, image OCR <=8 MB. A later streaming/chunked pipeline, disk quotas, cancellation and resumable uploads are required for large books and lengthy recordings. No limit was silently removed.

OCR requires Tesseract and language data. Browser audio formats depend on installed codecs. Speech recognition is optional; text can be manually corrected. The start screen does not automatically recognize audio upon recording. The user can open it in 3D Lab for transcription and advanced acoustic analysis.

Existing SQLite and asset folders remain unchanged. Do not delete legacy files or databases before migration tests.

## Windows smoke test
```powershell
cd "$HOME\Desktop\study"
git pull --ff-only origin docs/study-architecture-v0.1
cd prototype
.\.venv\Scripts\python.exe -m unittest discover -v
.\.venv\Scripts\python.exe web_app.py
```
Open `/`, `/canvas`, `/phonovision-3d`; verify identical navigation and active highlights. Record from home, save project, confirm automatic handoff to free canvas. Check 3D Lab expandable spectral relief and existing microphone controls. Verify old scenes and boards remain accessible. Physical Windows/browser acceptance pending.
