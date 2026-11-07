# PhonoVision Acoustic Studio — experimental checkpoint v0.1

Route: `http://127.0.0.1:8766/acoustic-studio`.

## Implemented
- Browser microphone recording via `getUserMedia` with explicit browser permission, limited to 8 seconds.
- Load an existing audio file through browser `decodeAudioData` (MP3, WAV, M4A, OGG support depends on browser codecs; **not arbitrary codecs or bit depths**). Analyze first 8 seconds; reject files over 25 MB.
- Local mono Float32 samples, simple browser-side spectral analysis, and a sphere-like pseudo-3D rendering with selectable sphere/flower/star/vase/bell shapes, adjustable deformation and colors.
- Manual letter/phoneme time markers. These markers are **not forced alignment**; letters cannot be inferred from spectra alone.
- Playback of original samples and modified playback rate, low-pass cutoff, gain. Export original WAV and an approximate offline resampled/filtered modified WAV. Speed and pitch change together; this is **not independent pitch shifting or formant preservation**.
- Export PNG and `study.phonovision.project` version 1 JSON containing geometry, user markers and text. Audio is **not included** in JSON; export WAV separately.
- Optional browser SpeechRecognition if supported, after explicit confirmation because browser recognition can transmit audio to a third-party service. It listens to the microphone separately and is **not transcription of the loaded file**. If unavailable, user can enter transcript manually.
- Local audio processing stays in the browser for file/microphone recording and synthesis; no server-side speech-to-text or image-to-audio inversion.

## Scientific and technical boundaries
- The spectrum-derived shape is a **visual metaphor** and a parameterized projection, not a unique physical reconstruction of speech.
- A PNG or a sphere surface alone is insufficient to recover original speech: STFT magnitude loses phase, and rendering further compresses data. Reversibility requires preserving PCM audio, or a suitable invertible representation with phase.
- No phoneme boundary model, speech alignment, WebGL mesh, true 3D export, ASR offline model, diffusion image-to-sound, phase-vocoder pitch shifting or inverse spectrogram synthesis yet.
- Recording uses ScriptProcessorNode for prototype browser compatibility; replace with AudioWorklet for production.
- Acoustic Studio does not automatically upload or store microphone data in the Study database. Saving files uses browser downloads.
- Prototype audio limit 8 seconds for interactive analysis, despite longer files being accepted for decode; users should split longer material.

## Windows smoke test
```powershell
cd "$HOME\Desktop\study"
git pull --ff-only origin docs/study-architecture-v0.1
cd prototype
.\.venv\Scripts\python.exe -m unittest discover -v
.\.venv\Scripts\python.exe web_app.py
```
Open `/acoustic-studio` in Chromium on localhost. Confirm microphone permission, record a short word, listen to original, change playback parameters, listen again, export both WAVs, add manually labelled boundaries, export and reopen project JSON, export sphere PNG and drag it to `/canvas`. Browser E2E and native Windows verification are pending.

## Next gates
1. AudioWorklet capture and robust sample rate handling.
2. Local speech recognition with opt-in downloaded Whisper or Vosk models.
3. Word/phoneme forced alignment using text and audio; distinguish graphemes from phonemes.
4. Store audio and visual geometry with explicit provenance, reversible DSP metadata, and stable node links.
5. WebGL/Three.js 3D mesh with glTF export, visual object morphing and timeline.
6. Full automated E2E tests and measured recall experiments.
