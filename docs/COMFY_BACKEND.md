# Local ComfyUI backend (Issue #7)

Study only connects to HTTP `127.0.0.1:8188`. Proxies and redirects are disabled.
It never installs ComfyUI, checkpoints or Windows settings. The operator must
already have a compatible, reviewed text-to-image checkpoint available.

## Configuration

Process environment (set before starting Study):

| Variable | Default / restriction |
| --- | --- |
| STUDY_COMFYUI_ENABLED | `0`; use `1` to allow dispatch |
| STUDY_COMFYUI_CHECKPOINT | required reviewed `.safetensors` or `.ckpt` name; no absolute/traversal paths |
| STUDY_COMFYUI_DB | `prototype/comfy_jobs.sqlite` |
| STUDY_COMFYUI_WORKERS | `1`, integer 1–4 |
| STUDY_COMFYUI_CAPACITY | `8`, integer 1–64 active local jobs |
| STUDY_COMFYUI_TIMEOUT | `120`, finite .01–600 seconds per running job |

Use **one Study process per registry file**. SQLite WAL commits each transition;
worker shutdown waits for outstanding bounded HTTP calls before closing SQLite.
Disabling generation permits reading old jobs but never resumes queued dispatch.

## HTTP and client contract

Existing routes are retained:

- GET `/v1/comfy/status` returns `enabled`.
- POST `/v1/comfy/generate` accepts `prompt`, optional `seed`, `request_id`,
  `width`, `height`, `steps`. Unknown fields, workflow nodes and external URLs
  are rejected. Default parameters remain 0/512/512/20.
- GET `/v1/comfy/jobs/{id}` and `/image?filename=...&subfolder=...`.
- GET `/v1/comfy/jobs` lists the latest 100 registered Study jobs.
- POST `/v1/comfy/jobs/{id}/cancel` cancels a local job.

`job_id` and backward-compatible `prompt_id` both mean the **local Study UUID**,
namespace `study_local`. They are never an arbitrary upstream history ID.
`request_id` is an optional 1–120 character idempotency key. Persist the key
before submission; identical complete workflow parameters return the same job,
including after restart. Reusing a key with different parameters is rejected.

`state` is one of `queued`, `running`, `completed`, `failed`, `cancelled`.
Legacy `status` is preserved (`complete`, `timed_out`, `interrupted` included).
Consumers should stop polling on terminal states and display `error.code` and
`error.message`, rather than assuming every queued job succeeds.

The composer v1 schema is accepted by `consume_generation_request(request,
request_id=...)` and by `/v1/comfy/generate` (with optional top-level request_id):

```json
{"contract_version":1,"mode":"text_to_image","prompt":"A cup floating above a house","parameters":{"seed":42,"width":768,"height":512,"steps":20},"references":[]}
```

Seed is an integer in 0..2^53-1; dimensions are 512 or 768; steps are integer
5–35; batch size is always one. Booleans are rejected as integer parameters.
Image-conditioned requests are rejected: references are not silently discarded.

## Local API security

Every route passes a common gate before dispatch. Host must be a single literal
`127.0.0.1`, `localhost` or `[::1]` authority with the actual server port.
Absolute proxy request targets, duplicate Host/Origin/token headers, untrusted
Origin and cross-site Fetch Metadata are rejected. Forwarded headers are ignored.

All methods except GET/HEAD/OPTIONS require `X-Study-CSRF`, even when Origin is
absent. Obtain the per-server token via GET `/v1/security/bootstrap`; this endpoint
has `Cache-Control: no-store` and no CORS grant. When Origin is present it must
exactly match `http://{Host}`. This protects browser CSRF/rebinding, not malicious
software already running locally. Reload open UI pages after restarting Study.

`study-fetch.js` attaches the token only to same-origin mutations. The integrated
C/D page wiring includes iframe and legacy pages. Command-line clients must
bootstrap explicitly. On Windows, a rejected request with an already-sent body
may observe connection reset rather than read HTTP 403; dispatch still does not
occur. Header-only negative tests verify the explicit 403 response separately.

## Recovery, cancellation and resource limits

Queued jobs survive restart. Previously running jobs become canonical `failed`
with `status=interrupted` and `restart_interrupted`: their remote acceptance or
completion may be uncertain, so Study never silently resubmits them. The user
must inspect ComfyUI and deliberately create a new request if retry is desired.

Cancellation is local and durable; cancelled work cannot later attach a result.
It does not call ComfyUI's global interrupt, which could stop another client's
work. Upstream computation may continue, and cancellation cannot reclaim its
VRAM. Likewise a network failure after POST may have uncertain acceptance.
No automatic network retry creates a duplicate generation.

The queue and worker count are bounded; the fixed graph bounds dimensions,
steps and batch size. JSON responses are limited to 4 MB, PNG to 8 MB and 16
million decoded pixels. PNG is verified and decoded before delivery, and must
match recorded output provenance for a completed local job. No arbitrary path
or upstream prompt ID grants access. Generated PNGs remain in ComfyUI storage.
These are application limits, **not a hard OS RAM/VRAM quota**; physical model
memory and other ComfyUI clients remain under the operator's control.

A running deadline includes bounded socket lifetime across headers and body.
Connection setup/polling uses at most 15 seconds or the remaining job budget.
Queued jobs are FIFO; their waiting time also depends on earlier active jobs.
Terminal local jobs do not guarantee remote execution has stopped.

Actionable errors: `model_missing`, `out_of_vram`, `comfyui_unavailable`,
`invalid_response`, `generation_timeout`, `upstream_failed`, `restart_interrupted`.
Missing local checkpoint configuration is rejected before creating a job.
Raw upstream traceback/prompt text is not exposed in diagnostic messages.

## Reproducible verification / Windows smoke plan

No test requires a real model. Mock tests start a real loopback HTTP Comfy fixture
and use temporary SQLite files. Run from the repository root:

```powershell
python -m unittest discover -s prototype -v
# With an existing Python containing Pillow, PyMuPDF and Playwright + Chromium:
python qa/verify_backend.py --evidence C:/path/to/new-evidence
```

The verification script installs nothing and copies sources to a fresh isolated
snapshot, avoiding existing user data. It records exact HEAD/time and runs the
entire unittest suite, enabling all available browser modules against its own
loopback server. Missing dependencies/skips must be reported, not called PASS.

Manual optional real-Comfy smoke: confirm enablement/checkpoint; bootstrap;
submit one 512px request with a saved request_id; poll to terminal; open PNG;
repeat identical key and confirm unchanged local ID; restart Study and reread;
cancel a second job and verify it never attaches an image. Inspect ComfyUI before
retrying interrupted work. Do not install models or change system settings as
part of this smoke test. Real diffusion/VRAM performance is unverified here.

## Integration provenance

A reuses backend commits 6612930/ad39a25, adds P0 security, composer parameters,
diagnostics, PNG decoding and socket/shutdown fixes. To avoid shipping protected
API routes with broken UI, this branch includes selected D PDF/CSRF wrapper
commits and C canvas core/security wiring plus hover fix. They retain original
authors; no shared branch was merged or deployed. B's semantic composer remains
in its independent Draft PR #16; its v1 handoff is supported by this backend.
