# Data Model and API Draft v0.1

## Storage choices
- PostgreSQL for relational data + JSONB for extensible scene recipes. Ordinary SQL edge tables first, graph DB only if justified.
- Object storage/files for generated media. Immutable content hashes, versioned scene IDs and licensed source attribution.
- GitHub for schema/migrations, open reference data and code; **not the live dictionary or user DB**.

## Core entities (proposed)
`lexeme(id,lang,lemma,pos,source_id)`;
`lexical_form(id,lexeme_id,spelling,features_json)`;
`lexical_sense(id,lexeme_id,definition,gloss_lang,register)`;
`translation_link(id,source_sense_id,target_sense_id,confidence,review_status,source_id)`;
`pronunciation(id,lexeme_id,ipa,region,audio_asset_id,source_id)`;
`example_sentence(id,lang,text,source_id,license_id)`;
`example_alignment(id,src_sentence_id,tgt_sentence_id,review_status)`;
`source_licensing(id,source_name,url,license,attribution,import_version)`.

`learner(id,locale,consent_version)`;
`mnemonic(id,learner_id,target_sense_id,version,visibility)`;
`mnemonic_anchor(id,mnemonic_id,sound_fragment,object_concept,link_to_meaning)`;
`scene(id,scene_ir_version,recipe_json,mnemonic_id)`;
`media_asset(id,sha256,mime,location,provider,model,license,created_at)`;
`learning_attempt(id,learner_id,lexical_sense_id,task_type,shown_cues,response,correctness,latency,created_at)`;
`review_schedule(learner_id,lexical_sense_id,skill,algorithm_version,due_at,state_json)`;
`experiment_assignment(id,learner_id,protocol_version,condition,consent)`.

The schema must represent homographs, polysemy, separable verbs, noun genders/plurals, inflected forms, multiword phrases and many-to-many translations. Distinguish lexical entries from *senses*. Track human vs AI-generated statements and confidence.

## Initial APIs (examples, subject to design review)
- `GET /v1/lexicon/search?q=Tasse&source_lang=de&target_lang=ru`
- `GET /v1/lexicon/lexemes/{id}`
- `POST /v1/linguistics/analyze`
- `POST /v1/translation/candidates`
- `POST /v1/phonetics/segment`
- `POST /v1/mnemonics`
- `POST /v1/scenes/compile`
- `POST /v1/media/jobs` + `GET /v1/media/jobs/{id}`
- `POST /v1/speech/evaluate`
- `POST /v1/learning/attempts` + `GET /v1/learning/due`
- `POST /v1/xr/actions`
- `GET /v1/modules/{module}/health` (gateway) or `GET /health` (module)

API schemas should use OpenAPI 3.1 + JSON Schema, stable IDs, locale tags, explicit errors, source metadata, trace IDs and idempotency for mutations. Auth scopes by learner and service. Do not expose personal mnemonics in global lexicon queries.

## Data acquisition candidates (not yet audited)
German Wiktionary extracts, Open Multilingual WordNet, open frequency lists, Universal Dependencies German treebanks and lexicon resources; evaluate exact coverage, German↔Russian sense alignment, commercial/noncommercial restrictions, share-alike obligations, update cadence and source attribution. Multiple collections may contain incompatible rights. Import only sources cleared by a provenance/license manifest. Corpus text and translations must not be fabricated to fill gaps.

## Core quality tests
Bidirectional query correctness; article/inflection and separable verb handling; sense-level translation; phonetic fragment roundtrip; personal mnemonic privacy; SceneIR schema validation and rendering fallback; deterministic scheduling; import re-runs; backup/restore; malformed and prompt-injection input; multilingual Unicode; version-compatibility contracts.
