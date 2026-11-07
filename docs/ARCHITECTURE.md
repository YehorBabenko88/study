# Architecture Specification v0.1

## 1. Core learning loop
**Target meaning ↔ spoken/written form → learner-chosen phonetic anchors → bizarre composite mnemonic → narrative link to meaning → retrieval without prompt → pronunciation and contextual use → retention measurement → optional redesign.**

Example, *die Tasse* = чашка: first establish that the German word is `die Tasse`, with noun article `die` and /ˈtasə/ pronunciation. Do **not** invent that `Tasse` sounds exactly like an unrelated Russian word. A learner may choose any personal anchors to the sound fragments *ta* + *sə*, generate an unusual multi-object scene involving a cup, and annotate how each fragment cues sound and meaning. Test whether they can subsequently retrieve **both** `die Tasse` and its meaning without seeing the mnemonic.

The system must avoid mistaking familiarity with a picture for lexical learning. A mnemonic is optional, editable, and personal.

## 2. Independent service boundaries
1. **Lexicon**: lexical entries, senses, genders, declension, conjugation, examples, bidirectional search, source/version/license.
2. **Linguistic Analysis**: tokenization, lemmatization, POS, German morphology, dependency parse, sense disambiguation. Independent NLP provider adapter.
3. **Translation & Validation**: translation candidates, uncertainty, grammatical review, human-editable results.
4. **Phonetics**: IPA, syllabification, sound chunks and optional user-created Russian sound analogies.
5. **Mnemonic Studio**: user-chosen associative objects and their relationships, candidate suggestion, scene recipes, history.
6. **Scene Semantics**: typed objects, properties, spatial relations, action timelines, editable format independent of renderer.
7. **Media Renderer**: separate image, animation, audio and 3D backends; provider adapters, cache, cost ceilings, provenance.
8. **Speech**: TTS, ASR and optional pronunciation feedback with calibrated uncertainty; no claim of clinically accurate accent scoring.
9. **Learning Memory**: attempt event store, spaced-repetition scheduling, separate recognition/recall/production estimates.
10. **Tutor/Dialogue**: conversational pedagogical planner; uses API tools and must not silently rewrite verified lexical facts.
11. **XR Interaction**: optional VR/AR client mapping pointing, grabbing, moving, walking and spatial relationships to scene/action events.
12. **Analytics & Experimentation**: retention, delayed recall, transfer, error analysis, consented and reversible experiments.
13. **Identity/Consent**: account/session, learner data export/delete, scopes, parent/guardian rules if minors supported.

Each has a well-defined independent API contract and health/version endpoints. **Logical modules do not require 13 deployment processes on day one.** Start as separately testable packages with boundaries; split into independently deployable services only as needed. No direct cross-module table writes.

## 3. Orchestration
Client -> API gateway / tutor -> typed module APIs -> event stream. Use request id, idempotency key, trace id, versioned schemas, bounded retries, timeouts and circuit breakers; media generation via asynchronous jobs. Failure of image/VR/speech leaves text study operational. If an AI provider fails, stored cards and schedules remain usable offline.

Codex is a software development agent, not the runtime tutor. The runtime tutor uses explicitly selected, replaceable AI providers and deterministic validation for high-stakes persistence.

## 4. Scene intermediate representation
`SceneIR` is a device-agnostic, versioned, structured object with `objects[]`, `attributes`, `relations[]`, `actions[]`, `audio_cues[]`, `target_form`, `meaning_anchor`, `mnemonic_anchor_map`, `source_provenance`, `language_tags` and `accessibility_text`. Coordinate systems and temporal units are explicit. A renderer must not interpret a metaphor as a literal lexicon fact.

Scene examples: `MOVE(cup, table)`, `PLACE(chair, beside(table))`, `SAY("Stell den Stuhl neben den Tisch.")`. Distinguish verified translations from generated creative mnemonic material.

## 5. Personal adaptation
User controls mnemonic objects. Recommenders offer alternatives without enforcing purported rigid "learning styles". Adapt using observed delayed recall and correction, not a one-off personality quiz. Track article, pronunciation, meaning, spelling and contextual production separately. Keep an explainer for why an exercise is scheduled.

## 6. Operations
Windows-first local deployment with PostgreSQL, media directory or compatible object storage, local API, browser frontend. Containerized deployment optional; support offline/no-cloud mode for core review. Sensitive data stays local by default; encrypted backup and restore tests required. All modules are explicitly portable to other projects, with stable licenses/contracts.

## 7. Non-goals for first prototype
All German words (lexicographic completeness cannot be assured), open-ended film generation, perfect translation, automated neural diagnosis, production-ready VR object recognition and massive microservice infrastructure.
