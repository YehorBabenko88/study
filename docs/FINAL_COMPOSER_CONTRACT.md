# Final composer integration contract

The final integration keeps PR #16's `semantic_composer.py` as the canonical compiler and revision store. Its multiple roots, directed traversal, exact graph snapshot/hash, immutable versions, parameter validation, and explicit unsupported image-conditioned generation remain intact. PR #11's alternative prompt compiler does not replace it. PR #11's non-destructive `add_link`, `remove_link` and conflict-aware `undo_link` survive in the separate `semantic_links.py`; undo preserves later node/gallery edits and never deletes media.

## HTTP service

`composition_service.dispatch(method, path, data=None)` returns `(status, JSON payload)`, or `None` outside its namespace. The web server supplies its existing loopback, Host/Origin, token, and request-size guards before dispatch.

- `POST /v1/compositions`: `{graph, roots, direction:"both", parameters, ...compiler options}` creates an immutable revision; 201 returns that revision.
- `POST /v1/compositions/revisions/{revision_id}`: `{user_prompt, parameters}` appends a reviewed revision; omission inherits prior prompt, explicit null clears it. Source graph and selection remain fixed. Changed graph requires a new composition.
- `GET /v1/compositions/{composition_id}`: `{items:[revisions]}`; each revision includes `jobs`.
- `GET /v1/compositions`: `{items:[latest revisions]}`; each includes jobs for that revision. Historical revisions remain available through composition history.
- `POST /v1/compositions/revisions/{revision_id}/generate`: `{request_id}` only; returns 202 and a durable job. Prompt or parameter changes require a saved revision first.
- `GET /v1/compositions/jobs/{job_id}` polls/resumes reconciliation. `POST /v1/compositions/jobs/{job_id}/cancel` cancels locally.

Jobs include `job_id`, `revision_id`, `request_id`, `prompt_id`, `prompt_id_kind`, `upstream_prompt_id`, `status`, and `result`. Results contain terminal status and `outputs:[{asset_id,sha256}]`; hashes describe the actual PNG bytes saved as board assets. Bad input returns 400, unknown resources 404, request/revision conflicts 409, full queue 429, disabled/transient local service 503. A disabled response retains a durable job ID for polling or cancellation. GET of previously authorized durable reservations may reconcile submission and output saving.

## Local versus upstream IDs

The adapter's existing `prompt_id` is its **local durable queue ID**. It remains unchanged for backward compatibility and is explicitly labeled `prompt_id_kind:"local"`. The distinct `upstream_prompt_id` is null until the loopback ComfyUI `/prompt` response supplies it. Completed terminal results preserve that upstream ID across restart. Local queue acceptance does not claim that upstream generation ran or completed.

The revision's `effective_prompt`, seed, width, height, and steps are passed to the existing fixed allowlisted workflow. The checkpoint remains the explicitly configured local adapter checkpoint. No image references are transmitted; image-conditioned execution raises. Available source assets in provenance are not evidence of pixel conditioning.

## Durability and recovery

`STUDY_COMPOSITIONS_DB` selects the separate SQLite file; the local default is `prototype/compositions.sqlite`. Revisions, accepted jobs, terminal results, request reservations, cancellation records, and output digest mappings are append-only with SQLite UPDATE/DELETE guards. No existing learning/board database is migrated.

Before adapter submission the service commits a request reservation bound to exactly one saved revision. Its deterministic adapter request key survives a crash between queue acceptance and service job recording. Repeating generation or GET reuses the adapter's durable idempotent job instead of submitting another generation. Adapter checkpoint/configuration must remain consistent while reconciling a previously submitted request; changed adapter input is refused rather than silently rebound.

Queued adapter work can resume when the adapter restarts. Its running work is truthfully marked interrupted on restart; the service records that terminal result, rather than pretending GPU execution survived. A retry requires a new request ID and preserves the old job/result. Cancellation never claims to stop already-running upstream computation. Cancellation of a reservation that has not reached the adapter prevents later submission.

Completed PNGs pass through the adapter's owned-job output validation. Assets are deduplicated by source SHA-256, assigned deterministic UUIDs, and saved through `board_assets.store` with immutable atomic publication. Reusing an asset ID with different bytes fails. A crash after image publication but before the database digest mapping can safely retry the same immutable ID. Terminal results are appended once; later polling/history reads reuse them without refetching pixels. No original asset is overwritten or deleted. Atomic publishing may leave an unreferenced temporary file after a process crash; existing assets remain intact.

## Isolated validation

`../venv/Scripts/python.exe -m unittest discover -s prototype -p test_composition_service.py` covers fake loopback HTTP submission/polling/PNG fetch, exact reviewed parameters, durable request conflicts, cancellation, restart after submission and while running, interrupted/failure/timeout results, history, immutable asset writes, deduplication, and crash-after-image-publication recovery. Test assets, queues, and composition databases use temporary directories. `test_semantic_links.py` preserves the link/undo contract; the original #16 compiler tests continue to run unchanged.
