# Semantic composer v1 — integration contract for agent A

Scope: issue #8. Implementation: `prototype/semantic_composer.py`. No existing
backend, canvas, board, gallery, adapter or database schema files are modified.
This is the proposed executable boundary for agent A; it has not yet been
independently accepted by agent A or integrated into HTTP routes.

## Compile and review

Python 3.10+, no third-party dependencies:

```python
from semantic_composer import CompositionStore, generation_request

store = CompositionStore("/chosen/data/semantic_compositions.sqlite3")
revision = store.create(board_document, ["word-node"], direction="outgoing",
                        parameters={"seed": 42})
# Show source_description, suggested_prompt and user_prompt separately in UI.
edited = store.revise(revision["revision_id"], user_prompt="A cup rides a train.")
request = generation_request(edited)
```

`compose(graph, roots, *, direction='outgoing', max_depth=4, max_nodes=24,
max_edges=64, parameters=None, user_prompt=None, mode='text_to_image')` is the pure
equivalent of `create`, without storage IDs, versions or timestamps.

The graph uses existing board objects: `nodes` with `id`, `type`, optional `text`,
`asset_id`, `image_assets`; `edges` with `from`, `to`, optional `relation`.
Node types: letter, syllable, word, sentence, image, note, action.
Relations: association (default for old boards), part_of, sequence, meaning,
sound, action. A relation always describes **from -> to**, even during incoming
traversal. Association is also traversed directionally; use `both` when wanted.
`part_of` means child -> whole; sequence means predecessor -> successor;
meaning means source -> meaning; sound means source -> phonetic association;
action means actor -> target. No inferred reverse edges or inferred translations.

Sorted-root BFS with sorted neighbors visits nodes once, including self/cyclic
links. All original edges whose endpoints were selected appear in the scene
(including parallel/duplicate edges); incoming traversal never reverses clauses.
At the depth limit, `depth_limited=true` reports omitted reachable neighbors.
Capacity overflows raise ValueError rather than generate an incomplete scene.

Each scene contains:

| Field | Meaning |
| --- | --- |
| schema_version | Composer format version, currently 1 |
| source_graph_json | Canonical immutable JSON string of the full original graph, including unknown metadata and list order |
| source_graph_sha256 | SHA-256 of UTF-8 snapshot bytes; integrity identifier, not a signature |
| roots / selection | Root IDs and traversal settings for replay |
| selected_node_ids / selected_edges | Exact selected source IDs and directed edge objects |
| source_description | Deterministic structured description of elements and relations |
| suggested_prompt | Auto-proposed single-scene instruction plus description |
| user_prompt | Exact optional user edit, independently retained; null means no edit |
| effective_prompt | Suggested prompt or normalized user edit sent to adapter |
| parameters | seed, width, height, steps, including defaults |
| mode | text_to_image or image_conditioned draft |
| references | Sorted node_id/asset_id pairs, retaining every contributing node |
| reference_images_transmitted | Always false in this implementation |
| scene_fingerprint | SHA-256 of deterministic selected scene/settings, excluding timestamps and full-source snapshot order |

Original text remains in the snapshot. Description/prompt text replaces control
and formatting characters with spaces and collapses whitespace. Labels are JSON
quoted; this is not a natural-language prompt injection filter. Image IDs are
references to assets, not paths/URLs; the composer never reads arbitrary files.
Legacy `scene_id` metadata is preserved but not resolved into image bytes.

Hard limits: full source JSON 2 MB UTF-8, nesting 32; 1000 input nodes, 3000 input
edges; ID 80 characters, node text 5000 characters, 12 gallery assets per node;
selection 1..64 nodes and 0..256 edges, depth 0..32; 8 unique reference assets;
1200 characters each for suggested/effective/user prompt. A manual edit does not
bypass an oversized automatic description. UUID assets must be canonical lowercase
hyphenated strings. Finite strict JSON only; unsupported types/keys reject.
Stored revision envelopes have a separate 8 MB cap to accommodate snapshot
re-escaping and duplicated selected-edge metadata without reducing the source cap.

## Immutable history and replay

`create` writes version 1 with a new composition_id/revision_id. `revise(id, *,
parameters=None, user_prompt=<omitted>, mode=None)` reads a stored snapshot and
creates a new revision without altering its parent. Partial parameters inherit;
omitted edit inherits, explicit `user_prompt=None` restores the automatic prompt.
Selection/source remain fixed; a changed source graph starts a new composition.
Revision numbers increase across all branches of the same composition; parent ID
records which version was used. Concurrent SQLite writers allocate unique versions.

`get(revision_id)`, `history(composition_id)` return detached JSON dictionaries;
missing revisions raise KeyError. SQL triggers reject UPDATE/DELETE in composer
tables. There is no deletion API. Undo is selecting an older revision; regenerating
it produces another job or child revision. No board/gallery asset is removed.
The application owns asset retention and access controls: snapshotting an ID does
not copy image bytes or prevent another service from deleting an asset.

## Text-to-image adapter v1

`generation_request(revision)` returns this JSON-serializable payload:

```json
{
  "contract_version": 1,
  "mode": "text_to_image",
  "prompt": "reviewed effective scene prompt",
  "parameters": {"seed": 42, "width": 512, "height": 512, "steps": 20},
  "references": []
}
```

Seeds: integer 0..2^53-1; width/height: 512 or 768; steps: 5..35. Unknown parameter
keys reject. Defaults: seed 0, 512x512, 20 steps. These match existing
`comfy_adapter.workflow(prompt, **parameters)`. CFG/sampler/checkpoint remain the
reviewed adapter's responsibility. Same compiler input yields identical prompt and
fingerprint; exact GPU pixels also depend on model/workflow/runtime versions.

Agent A should expose a submission method accepting the entire request, enforce
existing ComfyUI opt-in, use all parameters, and return the actual `prompt_id`.
The current `comfy_adapter.submit(prompt, seed)` only accepts seed: it can be used
only with default dimensions/steps. Do not silently discard non-default parameters.
This module performs no network calls or automatic generation.

After actual successful submission:

```python
job = store.record_job(edited["revision_id"], actual_comfy_prompt_id)
# On completion, A validates the ComfyUI output, saves each new asset, hashes its
# stored bytes, and records terminal provenance. The old assets stay untouched.
store.record_result(job["job_id"], status="complete", outputs=[
    {"asset_id": new_asset_id, "sha256": stored_image_sha256}
])
# Or: store.record_result(job["job_id"], status="failed", error="GPU unavailable")
```

`record_job` snapshots the request from the stored revision. `record_result`
appends one terminal outcome; `job_history(revision_id)` returns jobs in insertion
order with optional result. Every result has job_id and revision_id, so each image
traces through the job to original graph, selected elements, prompt and seed.
Retry creates another real job; changed parameters create a child revision first.
Duplicate prompt IDs and overwriting terminal outcomes reject. Output metadata is
a caller assertion; the composer does not claim to verify pixels or asset hashes.

The caller must submit exactly `generation_request(stored_revision)`; don't submit
a mutated detached draft and then record a different stored revision. Submission
and SQLite recording are not a distributed transaction: if the process crashes
after submission, reconcile the returned ComfyUI ID before resubmitting. Record
full reviewed workflow, checkpoint hashes and runtime in agent A's execution log
when bitwise image reproducibility is required.

## Image-conditioned capability (unavailable)

`mode='image_conditioned'` permits drafting/reviewing a scene with one or several
asset references. Both `generation_request` and `record_job` raise UnsupportedMode
for this mode. Reference manifests alone never mean image-to-image support.

Before enabling execution, agent A must implement and test a reviewed adapter that:

1. Resolves all unique asset IDs under existing authorization, reads actual bytes,
   verifies formats/size/pixels and records content SHA-256 values.
2. Uploads actual bytes to ComfyUI and obtains server-side image identifiers.
3. Binds every uploaded image into an explicit compatible workflow's conditioning
   inputs that reach the sampled output, with reviewed node classes and weights.
4. Records workflow/version, uploaded identifiers, hashes, all contributing node
   IDs, parameters and actual prompt_id. Sets transmitted/used flags only after
   the corresponding steps succeed; missing assets fail instead of text fallback.
5. Tests multi-reference request transport and workflow connectivity, then runs
   a real ComfyUI smoke test before advertising the mode as working.

No backend route/UI claim should expose this mode as supported before that work.

## Verification

From repository root: `python -m unittest discover -s prototype -v`.
Focused: `python -m unittest discover -s prototype -p test_semantic_composer.py -v`.
Tests use temporary databases and in-memory graphs, never learner assets/data.
No live ComfyUI inference or image-conditioned smoke test is performed here.

Verified on Python 3.12.3 / Windows: 23 composer tests passed; full discovery ran
122 tests, with 116 passing and 6 skipped (five Playwright/STUDY_E2E_URL browser
tests and one missing-PyMuPDF PDF test). Existing baseline was 99 tests with the
same 6 skips. Independent review identified the source/envelope byte-limit
mismatch; a failing regression test reproduced it before the fix. No other
important review findings remained. CI status is recorded in the Draft PR.
