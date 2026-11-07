-- Study PostgreSQL 15+ schema v0.1. Run in a dedicated database.
BEGIN;
CREATE SCHEMA IF NOT EXISTS lexicon;
CREATE SCHEMA IF NOT EXISTS learning;
CREATE SCHEMA IF NOT EXISTS mnemonic;

CREATE TABLE IF NOT EXISTS lexicon.source (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 name text NOT NULL,
 source_url text NOT NULL,
 license_id text NOT NULL,
 snapshot_id text NOT NULL,
 attribution text NOT NULL,
 imported_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE (name, snapshot_id)
);
CREATE TABLE IF NOT EXISTS lexicon.lexeme (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 language_code text NOT NULL CHECK (language_code IN ('de','ru')),
 lemma text NOT NULL,
 pos text NOT NULL,
 source_id bigint REFERENCES lexicon.source(id),
 UNIQUE(language_code, lemma, pos, source_id)
);
CREATE INDEX IF NOT EXISTS lexeme_lookup ON lexicon.lexeme(language_code, lower(lemma));
CREATE TABLE IF NOT EXISTS lexicon.sense (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 lexeme_id bigint NOT NULL REFERENCES lexicon.lexeme(id) ON DELETE CASCADE,
 sense_key text NOT NULL,
 gloss text NOT NULL,
 gloss_language text NOT NULL CHECK (gloss_language IN ('de','ru')),
 review_status text NOT NULL DEFAULT 'unreviewed' CHECK (review_status IN ('unreviewed','reviewed','rejected')),
 UNIQUE(lexeme_id, sense_key)
);
CREATE TABLE IF NOT EXISTS lexicon.form (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 lexeme_id bigint NOT NULL REFERENCES lexicon.lexeme(id) ON DELETE CASCADE,
 written_form text NOT NULL,
 grammatical_features jsonb NOT NULL DEFAULT '{}'::jsonb,
 UNIQUE(lexeme_id, written_form, grammatical_features)
);
CREATE TABLE IF NOT EXISTS lexicon.translation (
 source_sense_id bigint NOT NULL REFERENCES lexicon.sense(id) ON DELETE CASCADE,
 target_sense_id bigint NOT NULL REFERENCES lexicon.sense(id) ON DELETE CASCADE,
 provenance_source_id bigint REFERENCES lexicon.source(id),
 review_status text NOT NULL DEFAULT 'unreviewed' CHECK (review_status IN ('unreviewed','reviewed','rejected')),
 PRIMARY KEY(source_sense_id,target_sense_id),
 CHECK (source_sense_id <> target_sense_id)
);
CREATE TABLE IF NOT EXISTS learning.learner (
 id uuid PRIMARY KEY,
 created_at timestamptz NOT NULL DEFAULT now(),
 consent_version text
);
CREATE TABLE IF NOT EXISTS mnemonic.recipe (
 id uuid PRIMARY KEY,
 learner_id uuid NOT NULL REFERENCES learning.learner(id) ON DELETE CASCADE,
 target_sense_id bigint NOT NULL REFERENCES lexicon.sense(id),
 revision integer NOT NULL CHECK (revision > 0),
 scene_ir jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(learner_id,target_sense_id,revision)
);
CREATE INDEX IF NOT EXISTS recipe_owner ON mnemonic.recipe(learner_id);
CREATE TABLE IF NOT EXISTS learning.attempt (
 id uuid PRIMARY KEY,
 learner_id uuid NOT NULL REFERENCES learning.learner(id) ON DELETE CASCADE,
 target_sense_id bigint NOT NULL REFERENCES lexicon.sense(id),
 skill text NOT NULL CHECK(skill IN ('meaning','form','article','pronunciation','context')),
 response text NOT NULL,
 correct boolean NOT NULL,
 cues_shown boolean NOT NULL,
 occurred_at timestamptz NOT NULL DEFAULT now(),
 metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS attempt_history ON learning.attempt(learner_id,target_sense_id,occurred_at DESC);
CREATE TABLE IF NOT EXISTS learning.review_schedule (
 learner_id uuid NOT NULL REFERENCES learning.learner(id) ON DELETE CASCADE,
 target_sense_id bigint NOT NULL REFERENCES lexicon.sense(id),
 skill text NOT NULL CHECK(skill IN ('meaning','form','article','pronunciation','context')),
 due_at timestamptz NOT NULL,
 scheduler_version text NOT NULL,
 scheduler_state jsonb NOT NULL DEFAULT '{}'::jsonb,
 PRIMARY KEY(learner_id,target_sense_id,skill)
);
COMMIT;
