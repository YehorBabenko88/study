# Study v0.3 — Hybrid MVP Implementation Contract

**Status:** design and backlog only; no executable deployment yet.

## Hybrid inference policy
Run deterministic dictionary, learner schedules and retrieval locally. Route expensive generative tasks to configurable local or cloud providers. Default to local where available; explicit opt-in before sending learner text, audio, mnemonic or room data to cloud. Provider choice per task; no hard dependency on one vendor. Cost budgets, retries, timeout, circuit breaker, job cancellation and fallback to text.

## First vertical slice (implement before VR)
User enters `die Tasse` or `Поставь чашку на стол`. System returns sense-aware German/Russian equivalents, article, morphological annotations, audio and an editable **sound-fragment → association object → target meaning** graph. User picks bizarre objects; scene compiler creates a 2D storyboard with captions and alt text. Review hides both translation and picture and measures unaided retrieval; subsequent practice can test article and production independently. Preserve user edits and revisions.

## Data ingestion
Candidates: Wiktextract/Kaikki DE and RU Wiktionary dumps, updated regularly and distributed under Wiktionary CC-BY-SA/GFDL obligations. Keep full source attribution, source snapshot date, original IDs, licensing and quality flags; segregate derived redistribution and avoid copying unreviewed content to public repo. Start with 500–2000 manually reviewed lexemes, including polysemy and separable verbs. Bidirectional links must be sense-level; never auto-equate unrelated meanings. Validate duplicate handling, incremental import and rollback. No promise of complete German vocabulary.

## Model selection and evaluation
- Qwen3 open-weight Apache 2.0 as candidate for mnemonic suggestions and tutoring, but output is **not** authoritative lexicography.
- OPUS-MT/Marian candidate translation baseline; source-code MIT does **not** imply each checkpoint is MIT. Pin exact checkpoint and its model-card license (some CC-BY-4.0).
- ASR faster-whisper/Whisper, TTS Piper; audit each checkpoint and voice license.
- Image generation provider adapter: local diffusion or cloud API. Generated image may fail to depict sound cue; validate user comprehension and offer manual corrections.
- FSRS for spacing; start with transparent heuristic/bayesian policy for choosing mnemonic style; train learned recommender only with consented, sufficient events.
- No model downloads or paid cloud requests until user approves environment/cost settings.

## Service packages
`lexicon`, `linguistics`, `translation`, `phonetics`, `mnemonic`, `scene_ir`, `media`, `speech`, `learning`, `tutor`, `xr_adapter`, `analytics`, `identity`. Each independently importable and contract-tested. First implementation may be a modular monolith plus async worker and PostgreSQL to avoid premature distributed operations. Use OpenAPI 3.1 and JSON Schema with semantic versioning; service health and explicit capability discovery.

## MVP acceptance checklist
1. Reproducible local Windows startup with configuration example and no embedded credentials.
2. 500+ licensed, traceable DE lexemes with Russian sense links reviewed; exact number subject to audit.
3. Round-trip text query, sentence parsing and translation candidate with review flags.
4. User can create/edit/delete a multi-object mnemonic with mapped phonetic chunks, storyboard, and text-only fallback.
5. Audio prompt, user attempt, deterministic review scheduling, and per-skill history.
6. Restart/recovery, export/delete learner data, backup/restore and provider failure fallback tested.
7. Integration tests of all boundaries; evidence and exact dependency/model hashes documented.
8. No XR or video required for first release; SceneIR retains future extensibility.

## Proposed implementation order
P0 legal/data/model benchmarks → P1 schema/contracts → P2 lexicon and sentence studio → P3 mnemonic storyboard → P4 recall + FSRS → P5 speech and optional generated media → P6 animation → P7 independent XR plugin. Each gate requires measured evidence before promotion.
