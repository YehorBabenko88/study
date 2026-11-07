# Study research prototype 0.1

Minimal, dependency-free Python reference implementation of a personal mnemonic scene intermediate representation and **exact-match-only** recall check. No AI inference, external APIs, PostgreSQL, audio, UI, image generation, spaced scheduler, or VR implemented yet.

Run with Python 3.10+:

```bash
cd prototype
python study_core.py
python -m unittest discover -v
```

The scene demonstrates a *user-authored* whimsical phonetic association for `die Tasse`. The example anchors are invented and not lexicographically verified. The prototype uses ephemeral in-memory values and does not store learner data. Do not interpret exact-match checking as a pronunciation or semantic assessment.

Next step: schema/API contracts and PostgreSQL persistence behind independent service boundaries. Verify licenses before importing Wiktionary material.
