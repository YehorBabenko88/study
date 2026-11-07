# Agent B → A integration handoff

Canonical B branch: `feat/semantic-scene-composer`, Draft PR #16. The similarly
named `agent-b/semantic-composer` branch is not the implementation maintained by
this chat. Do not merge as part of this handoff.

## Contract agreement

Agent A explicitly confirmed the v1 text_to_image contract, empty transmitted
references, local job-ID namespace and full-payload request_id idempotency. A then
confirmed implementation and supplied exact adapter commit
`5a30317ff21fcba5a81845e3f5383e458e52e147`. B tested that exact committed adapter,
not a speculative shim. This confirmation was received in B's chat from A during
the user-authorized handoff. See the definitive field/API descriptions in
SEMANTIC_COMPOSER_CONTRACT.md.

Files ready for A:

- `prototype/semantic_composer.py`: pure compiler and durable history/recovery API.
- `prototype/semantic_composer_example.py`: runnable API usage, recovery and asset saving.
- `prototype/semantic_composer_cards.json`: legacy scene cards and new typed/gallery cards.
- `prototype/test_semantic_handoff.py`: contract, compatibility and recovery unit tests.
- `prototype/test_semantic_lifecycle.py`: real A queue + HTTP protocol-fixture lifecycle.

## Minimal API usage

```python
from semantic_composer import CompositionStore
from semantic_composer_example import submit_revision, resume_submission, collect_result, DirectoryAssets
import comfy_adapter  # A's confirmed implementation

store = CompositionStore(data_dir / 'semantic_compositions.sqlite')
initial = store.create(board_document, root_ids)
edited = store.revise(initial['revision_id'], user_prompt='A cup rides a train.',
                      parameters={'seed': 12345, 'width': 768, 'height': 512, 'steps': 29})
job = submit_revision(store, comfy_adapter, edited['revision_id'])
# Poll once per application tick. None means queued/running; no busy loop here.
outcome = collect_result(store, comfy_adapter, job, DirectoryAssets(data_dir / 'assets').save)

# On application restart, using the same B and A database files:
for intent in store.recovery_state()['unlinked_submissions']:
    resume_submission(store, comfy_adapter, intent)
for job in store.recovery_state()['unfinished_jobs']:
    collect_result(store, comfy_adapter, job, DirectoryAssets(data_dir / 'assets').save)
```

Production asset saver must return `{asset_id, sha256}` for a newly saved image,
where sha256 describes the bytes actually retained (board_assets.store may
re-encode PNG). Preserve source images; do not replace existing asset IDs.
Every result links to B job_id, exact revision, complete original graph and selected
elements. The backend returns queued/running/complete or explicit terminal error
states, a durable local UUID, matching request_id and owned image descriptors.
No caller-supplied workflow, URL or reference list is accepted by the text adapter.

## Run after integration

With A's updated adapter on the Python import path, all lifecycle tests run by
normal unittest discovery. On B's independent branch, select the exact A file:

```powershell
$env:STUDY_SEMANTIC_ADAPTER_FILE = 'C:\scratch\agent-a-5a30317.py'
python -m unittest discover -s prototype -p 'test_semantic*.py' -v
Remove-Item Env:STUDY_SEMANTIC_ADAPTER_FILE
```

The selected file must be the unmodified adapter extracted from the recorded A
commit, e.g. with `git show <SHA>:prototype/comfy_adapter.py`. The tests create only
temporary SQLite files/assets and a loopback HTTP server. They perform no live
diffusion, model installation, HTTP-route changes or learner-data writes.

For a user-authorized live run with configured ComfyUI and reviewed checkpoint:

```powershell
$env:STUDY_COMFYUI_ENABLED = '1'
$env:STUDY_COMFYUI_CHECKPOINT = 'reviewed.safetensors'
python prototype/semantic_composer_example.py --adapter-file C:\scratch\agent-a-5a30317.py --data-dir C:\scratch\study-composer-demo
# Same paths and configuration after restart:
python prototype/semantic_composer_example.py --adapter-file C:\scratch\agent-a-5a30317.py --data-dir C:\scratch\study-composer-demo --recover
```

No image_conditioned execution exists: preparing its request, durable submission
intent or accepted job raises UnsupportedMode. Multiple source image IDs remain
provenance only. No live diffusion claim follows from a successful fixture test.

## Remaining integration responsibilities

Wire UI/API actions to this module without overwriting sources, keep A/B DB and
asset-retention policies stable, enforce existing Host/Origin/CSRF authorization
at HTTP boundaries, and retain reviewed model/workflow identity. A's public status
remains backwards compatible; additive canonical state fields can coexist.
Concurrent result collectors should be serialized by the application: the unique
terminal event prevents duplicate history but two collectors may save extra assets.

CLI recovery reports legacy upstream jobs as `manual_reconciliation`, continues
processing study_local jobs, and returns nonzero while manual work remains. It
never sends a legacy upstream ID to A's local lookup. Older persisted job payloads
without a namespace default to comfyui and remain readable without rewriting.

## Completed verification matrix

Python 3.12.3 on Windows, same B source in all runs:

| Setup | Command / result |
| --- | --- |
| B standalone base | unittest discovery: 136 tests, 126 passed, 10 skipped (6 baseline dependency skips + 4 lifecycle tests requiring A) |
| B + exact A adapter 5a30317ff21fcba5a81845e3f5383e458e52e147 | all 37 semantic tests passed, including 4 real-registry/HTTP-fixture integration tests |
| Isolated A 5a30317 + B files | full discovery: 157 tests, 151 passed, 6 baseline skips |
| Isolated latest A bc8cd6bbb6dd1b9310b4f9064980f4ab0fcb8ba6 + B files | full discovery: 185 tests, 154 passed, 31 skipped (25 browser acceptance, 6 PDF/OCR dependency tests) |

Isolated combinations were made by extracting committed A trees into scratch and
copying only B-owned composer/example/test/fixture files. No merge or shared file
edit was performed. The latest A additive canonical `state` field is compatible;
B uses the retained legacy `status` for exact terminal diagnostics.

The lifecycle tests assert actual persisted A local UUIDs, exact maximal seed
2^53-1, both dimensions, steps, edited prompt at the HTTP workflow boundary,
downloaded valid PNG bytes, new asset content hashes, immutable source/revisions,
accepted-before-bind recovery without another POST, running→interrupted recovery,
idempotency rejection on changed parameters and image_conditioned rejection.

Independent review reproduced a legacy-namespace recovery blocker. A failing CLI
regression test then verified the fix; all 37 semantic tests passed afterwards.
No remaining important review findings were reported. Live ComfyUI system_stats
at 127.0.0.1:8188 timed out; live inference and real reference conditioning were
not run. The runnable example's --help and git diff --check were also verified.
