# Implementation checkpoint 01

Added an initial PostgreSQL 15+ migration with independent lexicon, learning and mnemonic schemas, sense-level translation relations, user-owned versioned SceneIR recipes, and skill-specific attempts/schedules.

Added a conservative streaming JSONL/GZ preview parser for Wiktextract input, with no network access and no writes. It does NOT yet implement licensing approval, source attribution imports, Russian translation alignment or actual database persistence.

## Run local tests
```powershell
cd prototype
py -m unittest discover -v
```

## Database review (do not run against existing shared databases)
```powershell
psql -X -v ON_ERROR_STOP=1 -d study_dev -f db/migrations/001_core.sql
```
Run from repository root. Use a newly created dedicated database and a non-production account.

## Important limitations
No working web UI, API server, trained neural network, audio, images, video or XR. PostgreSQL migration is not yet integration-tested against a real server. Translation and lexical facts require review. No external data was downloaded. Future work: schema rollback strategy, real ingestion, FastAPI endpoints, UI and test evidence.
