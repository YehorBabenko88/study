# Study Scientific Acoustic Engine — P1 implementation checkpoint

## Added
- Local, **opt-in** faster-whisper transcription adapter using an existing model directory only; word timestamps, not phoneme boundaries.
- Local, **opt-in** WhisperX alignment adapter using an existing alignment model directory; returns character alignment, not scientifically verified phone boundaries.
- Independent pitch shifting using optional librosa phase-vocoder/resampling, exporting PCM WAV at approximately original duration.
- Real triangular parametric 3D mesh exported as self-contained glTF 2.0 JSON, with sound-energy radial displacement, shape presets, and a user-specified 9-value radius profile.
- Acoustic Studio UI buttons for local ASR, local alignment, pitch shifting, glTF export and object label.

## Installation and privacy
The existing Study server runs on 127.0.0.1 only. Install optional packages in the existing Python 3.12 venv **only after reviewing dependencies**:
```powershell
cd "$HOME\Desktop\study\prototype"
.\.venv\Scripts\python.exe -m pip install faster-whisper librosa
```
WhisperX is a separate, heavier optional environment: follow its upstream Windows compatibility and installation instructions. Model weights may have separate licenses and can be large. **Never download model weights implicitly.** Download/review them yourself, then configure:
```powershell
$env:STUDY_WHISPER_MODEL_DIR="C:\StudyModels\whisper-local"
$env:STUDY_ALIGN_MODEL_DIR="C:\StudyModels\align-local"
```
Paths above are examples, not created folders. The WhisperX adapter is experimental and requires a compatible aligner, which varies by language. Models are loaded on request and can be slow. A missing package or model returns an unavailable status. Model quality is not established.

## Scientific limits
- ASR words are statistical estimates; word timestamps are not phoneme boundaries.
- WhisperX character-level alignments are model predictions; letters and phonemes differ, especially in German. To achieve *phoneme* labels, add a G2P/IPA layer and a phonetic alignment model, then validate against hand-labelled recordings.
- Librosa pitch_shift alters pitch while approximately preserving duration, but phase vocoders introduce artifacts and can shift formants; it is not a perfect voice-preserving transformation.
- Exported glTF is a real 3D triangle mesh, but the shape is **parametric**, not a generative reconstruction of an arbitrary named object. The noun is metadata. For arbitrary user-specified objects, use a separately consented and licensed text-to-3D model, or import a user-owned 3D mesh and deform it. Neither is currently implemented.
- Geometry alone does not encode phase and cannot reconstruct original speech. Original WAV must be retained for reversibility.
- Audio and models remain local except the existing separately consented browser SpeechRecognition option.
- No claims of validated mnemonic efficacy.

## Windows smoke test
Update draft branch, run unit tests, start `web_app.py`, open `/acoustic-studio`. Record Tasse, export original WAV; install librosa and export independent pitch-shift WAV; configure a reviewed local ASR model and test local transcription; if a compatible alignment model is installed, test character alignment. Export glTF and open in a glTF viewer such as Blender. Tests and physical Windows acceptance are pending.

## Next gates
- Browser E2E and native Windows CI.
- Production AudioWorklet microphone capture and streaming; secure local job queue for slow inference.
- G2P/IPA phoneme aligner with confidence and human review.
- Real WebGL preview and import/deform arbitrary user-owned glTF models; optional text-to-3D provider.
- DSP roundtrip tests on phonetic corpora and separate phase/formant experiments.
- Reproducible model manifests, checksums, licensing, GPU/CPU resource limits.
