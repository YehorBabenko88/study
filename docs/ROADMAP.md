# Delivery Roadmap and Acceptance v0.1

## P0 — Audit and science/design
Verify source datasets and license/provenance, evidence review, user journeys, API boundaries and privacy threat model. No claims of complete German vocabulary. Create issue backlog and agree MVP.

## P1 — Reproducible foundation
PostgreSQL migrations, local configuration, auth, seed sample, tests, module health and OpenAPI contracts. Installer/uninstaller *planned*, with safe data retention defaults.

## P2 — Lexicon and sentence studio
DE↔RU sense-aware search, morphological analysis, grammar/translation candidates with confidence, user sentence input, editable correction and verified audio.

## P3 — Personal mnemonic studio
Learner chooses sound fragments and arbitrary multiple objects; graph editor stores directed sound→object→meaning links; build 2D scene, narrated audio, versioned reproducible assets.

## P4 — Memory and experiments
Unaided recall, article/pronunciation/use checks, FSRS candidate, 1/7/30 day reporting, learner-controlled recommendation and reproducible A/B tests.

## P5 — Video/3D
SceneIR compiler, action timeline, compositional animation and a renderer switch with cache/cost caps. Keep everything functional when rendering fails.

## P6 — VR/AR (separate optional module)
Object pointing/grabbing/moving, spatial actions, grammar mapping, speech prompts, realistic fallback to simulated room if world recognition fails. VR and camera-based AR have distinct constraints; check hardware and permissions.

## Mandatory delivery gates
- One module failing never prevents plain-text vocabulary recall.
- End-to-end German↔Russian "die Tasse" + sentence works reproducibly.
- User can build, edit and delete a composite mnemonic and retrieve it in multiple modes.
- Learning outcomes assessed via delayed unaided recall, not appearance or immediate recognition alone.
- Media generation is asynchronous and cancellable; no silent unlimited cloud spending.
- All ingestion, media and user data have explicit licensing/consent/provenance.
- No secrets or personal data committed to GitHub.
- Tests, documentation and evidence must precede production release.
