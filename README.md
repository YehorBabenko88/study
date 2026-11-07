# Study — Adaptive Multimodal Language Learning

**Status:** CONCEPT / ARCHITECTURE v0.1 — no production implementation.

Study is an independent, API-first language-learning platform. Initial language pair: **German ↔ Russian**. The design supports other languages later.

## Product vision
Learners create **personal phonetic mnemonics** (sometimes bizarre, composite scenes) connecting how a foreign word sounds to what it means. The system helps turn those associations into pictures, animation, audio, interactive scenes, and optionally VR/AR environments. It then verifies whether the learner can independently recall, pronounce and use the word.

Two entry modes:
1. **Sentence Studio:** type or speak a sentence; get a reviewed translation, morphology, audio, visual scene, and recall exercises.
2. **Immersive Action:** point to and manipulate virtual/recognized objects; learn vocabulary and grammar through actions, feedback and active recall.

The memory model and content formats are shared between modes. Each module can run independently behind versioned APIs. No dependency on other user projects.

## Start here
- [Product and architecture](docs/ARCHITECTURE.md)
- [Scientific assumptions and evaluation](docs/LEARNING_SCIENCE.md)
- [Initial data and API contracts](docs/DATA_AND_API.md)
- [Delivery roadmap and acceptance](docs/ROADMAP.md)
- [Data provenance, privacy, licenses](docs/SAFETY_AND_LICENSES.md)

## Design boundaries
- GitHub: versioned source code, manifests, migrations, docs and small curated public samples **only**.
- PostgreSQL: working lexical records, morphology, sentence graph, learner preferences, schedules, attempts and provenance.
- Object storage: generated audio, pictures, scenes, animations, and 3D assets (content hashes in DB).
- No licensed third-party corpora or personal learner data checked into GitHub.
- The first phase is research/design, not implementation.
