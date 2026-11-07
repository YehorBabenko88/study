# PhonoVision — acoustic-to-visual mnemonic research module

## Hypothesis
An actual spoken German sound contains time-varying amplitude and frequency information. A learner might use a **stable, personally editable visual metaphor** derived from that information as an additional cue for recall. This is a research hypothesis, not an established claim of superior language acquisition.

The acoustic input is a waveform x[n]. For a short frame m, compute the windowed DFT:
X(m,k)=sum_{n=0}^{N-1} x[n+mH] w[n] exp(-i 2 pi kn/N).
Visualize normalized |X(m,k)| as a time-frequency spectrogram. Short-time RMS gives an amplitude envelope. Unlike a fixed mapping of alphabet letters to musical notes, this depends on actual speech and coarticulation. Pitch F0 is not equivalent to all phoneme frequencies; unvoiced consonants may have no stable pitch. The current implementation does **not** estimate F0, formants, or phoneme boundaries.

## Current implementation
- `prototype/phonovision.py`: standard-library 16-bit PCM WAV analyzer, 8–48 kHz, mono/stereo, max 8 seconds / 2 MB, short-window DFT and SVG spectrogram
- `PUT /v1/phonovision/analyze`: analyze an uploaded WAV and return normalized spectrum + SVG
- `POST /v1/phonovision/metaphor`: propose a *creative heuristic* from a typed sound fragment (flash, ribbon, sparks, texture)
- `/canvas`: buttons to add editable metaphor cards or spectrogram cards and connect them to syllables/words
- No audio upload is sent to cloud. Spectrogram nodes may be persisted inside board JSON; long sessions require future asset deduplication.

## Research plan
Compare (A) personal imagery only, (B) waveform-derived image, (C) combined personal imagery plus waveform, holding word familiarity, time-on-task and review schedule constant. Test unaided recall, article accuracy, delayed retention, and transfer. Record individual preferences but avoid unvalidated fixed learning-style categories.

## Limitations
- Letter-to-sound mapping is context dependent; a typed grapheme is not an acoustic measurement.
- Heuristic sound shapes are illustrative, not phonetic classifications; for example, 's' in spelling need not be /s/ in every German word.
- The DFT is deliberately bounded and not optimized; no microphone recording widget, ASR, IPA alignment, model-based syllabification, formant tracking or melody generation yet.
- WAV only; convert audio locally to PCM WAV before upload.
- SVG spectra are not realistic pictures or AI-generated creatures; users build their own visual metaphors from them.
- This remains a local prototype, not a validated neuroscience intervention.

## Windows check
Update the branch, run `py -m unittest discover -v`, start `py web_app.py`, open `/canvas`. Test sound fragment 'Tas' and a short 16-bit PCM WAV. Verify spectrogram node save/reload. New code has not yet passed physical Windows acceptance.
