# PhonoVision 3D Lab — checkpoint

Route: `http://127.0.0.1:8766/phonovision-3d`.

An interactive, **pseudo-3D projection** of the existing short-time spectral energy matrix. The rendering is drawn on a 2D HTML Canvas, without WebGL or a physics engine. It supports mouse-controlled rotation, relief height, sampling detail, moving time cursor, synthetic demo and PNG export. Real spectral input is supplied by the existing `PUT /v1/phonovision/analyze` API for short 16-bit PCM WAV recordings.

The visual surface is a user-editable mnemonic ingredient, **not a mathematically unique translation of letters into pictures**, a 3D model file, or a neuroscience-validated learning intervention.

## Run and verify
```powershell
cd "$HOME\Desktop\study"
git pull --ff-only origin docs/study-architecture-v0.1
cd prototype
.\.venv\Scripts\python.exe -m unittest discover -v
.\.venv\Scripts\python.exe web_app.py
```
Open `/phonovision-3d`; check demo, rotation, animation, PNG export. For a real signal, upload a short WAV. The generated PNG can be dragged onto the existing `/canvas` board, where it becomes a regular image node.

## Next steps
1. Web Audio microphone capture with permission, local WAV conversion, and speech segment boundaries.
2. Fast FFT/STFT implementation for longer samples, psychoacoustic features and optional formant/F0 estimators.
3. Export reusable geometry (glTF), animation timeline and direct scene-node linking.
4. Compare sound-derived imagery with self-generated mnemonics using delayed recall experiments.
5. Add browser end-to-end and Windows native tests; currently only static UI contract tests were committed.

The existing dictionary and German/Russian translation model installations remain separate incomplete workstreams.
