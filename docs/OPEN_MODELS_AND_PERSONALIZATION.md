# Study v0.2 — Open Model Selection and Personalized Learning

Status: candidate evaluation; NOT implemented, installed, benchmarked, or license-cleared.

## Decision
Use a replaceable ensemble, not one monolithic model. A general language model proposes mnemonic storyboards, a deterministic lexical validator checks German/Russian facts, specialist speech and image backends handle modalities, and a separate personalized scheduler learns from recall events.

| Module | Candidate | Gate |
| --- | --- | --- |
| Tutor / mnemonic proposal | Qwen3 open-weight Apache-2.0 variants | benchmark DE/RU and CPU/RAM latency; review each checkpoint |
| Translation | NLLB-200 for research comparison; alternative permissively licensed checkpoints | NLLB checkpoint may have noncommercial restrictions; inspect model card before distribution |
| Morphology | spaCy, Stanza, German inflection lexicons | coverage, exact package/model licenses |
| Speech recognition | faster-whisper / Whisper checkpoints | audio consent, word-level accuracy, licensing |
| Speech synthesis | Piper or compatible ONNX voices | runtime and individual voice-model licenses; German accent QA |
| Scheduling | py-fsrs | use recall outcomes, not image likes; review algorithm and library license |
| Images | local diffusion model behind provider API | checkpoint license, GPU requirements, safety and reproducibility |
| 3D / VR | Godot/OpenXR candidates | hardware compatibility, asset licenses, spatial interaction |
| Personalized recommendation | start with calibrated Bayesian/bandit baseline | randomized comparison and sufficient data before model training |

## Personalized model design
Events: learner_id, item/sense, target skill, mnemonic version, cues shown, unassisted response, correctness, response time, delay, context, timestamp, consent. Store minimal personal data and provide deletion/export. Separate lexical correctness from mnemonic quality.

Phase 1: FSRS + rule-based selection and optional learner choices.
Phase 2: hierarchical statistics / contextual bandit with uncertainty, opt-in, exploration cap, no fixed learning-style labels.
Phase 3: small trainable ranking model only after sufficient consented observations and controlled holdout evaluations. No unsupervised model updates to factual dictionary entries.

## Evaluation
Compare plain retrieval, suggested, self-generated and co-created mnemonic conditions. Hold out words and learners; report delayed 1/7/30-day unaided recall, gender, production, time-on-task and costs. Prevent leakage across variants. Creative images must map sound fragments AND meaning explicitly; image recognition alone is not success.

## API contract additions
`POST /v1/model-router/infer`: task, locale, input, model_policy, request_id -> output, model_id, version, latency, cost estimate, provenance.
`POST /v1/mnemonic/candidates`: sense_id, sound_fragments, user_object_preferences -> candidates with sound-to-meaning links.
`POST /v1/learning/recommendations`: learner_id, due_items, capabilities -> task, reason, uncertainty, model_version.
`POST /v1/learning/feedback`: attempt_id, learner_correction, mnemonic_revision.

## Delivery gates
- First benchmark on a single Windows machine before selecting a default local checkpoint.
- No downloading gigabytes of weights without explicit capacity review.
- Check license at exact model/voice/dataset revision.
- No hidden user-data transfer to external AI services.
- Core lexicon and review operate without any generative model.
- No claim of scientifically demonstrated personalized benefit until prospective evaluation.
