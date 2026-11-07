# Study navigation consolidation — 3D Lab

## Fixed
The former `/phonovision-3d` route only showed a spectral relief with a WAV upload. Microphone recording, browser/local speech recognition, sphere geometry, pitch shifting and glTF export lived on `/acoustic-studio`, which was confusing.

Now:
- `/phonovision-3d`: **primary full Acoustic Studio**, including recording and all advanced controls.
- `/acoustic-studio`: backward-compatible alias to the same page.
- `/spectral-relief`: preserved original spectrum surface, with animation and PNG export.
- `/canvas`: free-form language graph.
- `/board`: Trello-style word/syllable/sentence board.
- `/`: classic lexicon, mnemonics and translation.

All five HTML pages now expose the same navigation links. Existing board and scene data are untouched.

## Windows verification
```powershell
cd "$HOME\Desktop\study"
git pull --ff-only origin docs/study-architecture-v0.1
cd prototype
.\.venv\Scripts\python.exe -m unittest discover -v
.\.venv\Scripts\python.exe web_app.py
```
Open `http://127.0.0.1:8766/phonovision-3d`, refresh with Ctrl+F5, verify microphone record/stop, upload, ASR, pitch and glTF controls. Check `/spectral-relief` still renders the previous spectrum and all navigation links work.

The browser must grant microphone permission. Some browsers may block microphone access in insecure non-local contexts; localhost is generally treated as a secure context. The server remains bound to 127.0.0.1. No physical Windows acceptance has been completed by this change alone.
