# Full-size lexicon subsystem — first implementation

Study now has a streaming SQLite lexicon store, separate from learner scenes and recall. It does not impose a fixed vocabulary count. It stores the original Wiktextract JSON entry plus extracted senses, inflected forms and translation candidates. **This is not yet a complete or reviewed German-Russian dictionary.**

## Source and license requirements
Obtain a German Wiktextract JSONL/GZ snapshot from a reputable source (for example the Kaikki Wiktionary extraction project). Verify its exact date, license, attribution and reuse obligations before importing. Wiktionary derivatives may require CC BY-SA attribution/share-alike; verify the exact dump and downstream redistribution terms. Do not put bulk dumps or learner data in GitHub.

## Import (Windows PowerShell)
Save the reviewed downloaded file as `C:\StudyData\de-wiktextract.jsonl.gz`. From `prototype`:
```powershell
py lexicon_store.py "C:\StudyData\de-wiktextract.jsonl.gz" --source "de-wiktionary" --license "REPLACE_WITH_VERIFIED_LICENSE" --attribution "REPLACE_WITH_VERIFIED_ATTRIBUTION" --snapshot "REPLACE_WITH_SNAPSHOT_DATE"
```
Replace all placeholders with **verified** information. For Russian-language entries, import a separately reviewed Russian snapshot with a distinct source ID. The parser only imports records whose `lang_code` is `de` or `ru`; a German Wiktionary dump can contain German and Russian entries, but coverage differs by source.

The database `prototype/study_lexicon.sqlite3` is created automatically. Back it up before re-imports. Repeated imports upsert source keys. Import currently commits in batches; a failed import can leave partial rows. The source-key design is provisional and may conflate duplicate etymology records: validate uniqueness and collision counts before large-scale production ingestion. It does **not** automatically delete entries absent from newer snapshots.

## Query
`GET /v1/lexicon/search?q=Haus&lang=de`
`GET /v1/lexicon/search?q=чашка&lang=ru`
`GET /v1/lexicon/stats`

Imported entries are searchable in the browser's new Dictionary section. The mnemonic scene builder remains restricted to three hand-curated words until sense-level validation and user choice are integrated. **Raw translation candidates must not be treated as verified German-Russian sense alignments.**

## Future quality gates
- Source manifests and deterministic snapshot SHA256 verification.
- Import checkpoint/restart and staged atomic swap for complete snapshots.
- Exact sense identity, duplicate/etymology collision detection and morphological index.
- Bidirectional reviewed DE↔RU links with confidence, license and source.
- PostgreSQL implementation of the same API for production-scale concurrency.
- Daily/weekly update jobs with provenance and rollback.
- No lexical coverage claims without measured counts and audit.

## Run tests
```powershell
py -m unittest discover -v
```
