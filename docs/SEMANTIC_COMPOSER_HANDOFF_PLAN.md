# Integration readiness extension — 2026-11-07

User approved continuing implementation in PR #16 without editing shared A/C files.
Use writing-plans/executing-plans/TDD; no further architecture gate is needed.

1. Freeze generation_request v1 (strict version and complete parameter object),
   confirm acceptance with A, and test against A's exact adapter SHA.
2. Add append-only submission intents with stable request_id before submission.
   Persist namespace-qualified job links atomically after acceptance. Reopen the
   store to list unlinked intents and unfinished jobs, re-submit the same request
   idempotently, then resume polling. No blind re-generation of interrupted jobs.
3. Pin old/new card fixtures; preserve whole original graph, canonicalize accepted
   legacy UUID spellings only in reference manifests. Keep image_conditioned off.
4. Provide executable lifecycle example and integration tests against a real A
   JobRegistry with loopback HTTP fixture (explicitly no live diffusion claim).
   Assert exact prompt and all four generation parameters in received workflow;
   save actual downloaded image bytes to a new asset, hash stored bytes, record
   results and reload all history. Also test crash windows and idempotent recovery.
5. Run focused and full suites, cross-branch tests and available live checks.
   Record exact own/A HEADs, handoff evidence and limitations; update Draft PR.

New ownership: semantic_composer.py, its tests/fixtures/example and composer docs.
No web_app.py, canvas.html or comfy_adapter.py modifications. Source asset retention
and upstream prompt IDs remain A's responsibility; local queue IDs must be labeled.
