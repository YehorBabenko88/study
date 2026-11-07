# Shared Speech Projects — Study cross-tab integration

## Workflow
1. Open `/phonovision-3d`. Record or load audio, then enter/review the transcription (browser speech recognition and local Whisper are optional).
2. Press **Сохранить для всех вкладок**. This explicitly stores metadata (transcript, language, manual or model-proposed time markers) in `study_local.sqlite3` and the original 16-bit PCM WAV in `prototype/speech_audio/<UUID>.wav`.
3. Open `/board`. Pick the project, listen, load the text, and click **Разложить на слова**. Each word is a clickable card for the existing mnemonic workflow.
4. Open `/canvas`. Pick the same project, listen, and click **Создать граф предложения**. This creates a sentence node and draggable word nodes with `part_of` and `sequence` links. The nodes refer to the original speech project UUID.
5. Classic Study `/` and the spectral relief `/spectral-relief` can also browse the shared transcription and audio.

## Scientific honesty
- Splitting transcript on whitespace is **not** verified linguistic segmentation or forced alignment.
- Timestamp arrays from browser/local ASR may not align with token positions; any time markers are hints only.
- No automatic phoneme segmentation has been verified. Existing manual sound/syllable controls remain.
- Audio is saved **only when user clicks Save**, not automatically on microphone capture. Browser recognition may use cloud processing; local Whisper requires explicitly installed local model.
- Existing mnemonic scenes, dictionaries, translations, SVG/PNG and learning features are unchanged.

## Storage
Metadata and audio must be backed up together. This is a local single-user prototype with no account security. WAV must be <=2 MB, 16-bit PCM, 8–48 kHz, up to 8 seconds. The browser saves mono WAV from the recording buffer. Recordings longer than this are not persisted as shared projects.

## Windows check
```powershell
cd "$HOME\Desktop\study"
git pull --ff-only origin docs/study-architecture-v0.1
cd prototype
.\.venv\Scripts\python.exe -m unittest discover -v
.\.venv\Scripts\python.exe web_app.py
```
Test record → transcribe/edit text → Save → board → split → canvas → graph → save board → reopen. Browser E2E verification is not yet confirmed.
