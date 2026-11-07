# Windows integration acceptance

Status: MERGE_NO-GO until owner approval. A mock image is not real ComfyUI acceptance.

## Automated checks on one committed HEAD

Use the prepared Python environment containing Pillow, PyMuPDF, pytesseract's Python wrapper and Playwright. No OCR executable, language pack, model or cloud service is installed by the runner.

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH = '<existing reviewed Playwright browser directory>'
<python> scripts/run_integration_acceptance.py --mode unit --require-clean
<python> scripts/run_integration_acceptance.py --mode browser --require-clean
```

Both commands print the exact git HEAD and actual PASS/SKIP/failure counts. Unit discovery intentionally skips browser tests. The browser phase must have zero skips and runs real Chromium. All application databases/media paths are redirected to a fixture directory. Mock-Comfy tests start explicitly fake loopback servers; they exercise transport and preservation, not GPU inference or model quality.

## Physical Windows test with existing local software

1. Record `git rev-parse HEAD`, Python/browser versions and the reviewed existing ComfyUI/checkpoint configuration. Keep existing learner databases, PDF uploads, speech audio and media intact. Use a separate test checkout and copied fixture data; do not run reset/delete/cleanup commands against learner paths.
2. Start Study on loopback using existing dependencies. Open `/canvas`, `/workspace` and `/phonovision-3d`. Confirm existing boards, galleries and sound projects can reopen. Record file hashes for copied PDF/audio/images before testing.
3. Select a word with typed connections. Build the scene, inspect selected sources and description, edit the prompt/seed/size/steps and save a child revision. Confirm the older revision remains selectable and source nodes/text/images are unchanged.
4. Only if an existing reviewed local ComfyUI and checkpoint are available, explicitly enable the adapter. Do not install/download a model as part of this test. Generate from the saved revision; record local job ID, upstream ComfyUI ID, workflow/checkpoint identity, exact parameters, stored PNG SHA-256, revision ID and source fingerprint. Inspect the real image. References are provenance only; text-to-image must not claim pixel conditioning.
5. Reload during a queued/running job. Reopen the saved revision/job; verify one result and one PNG asset, without a second submission. Cancel another job; confirm local cancellation is terminal and that the UI states upstream work may continue. Restart Study during a job and verify the interrupted outcome/history and explicit retry to a new job.
6. Save/reopen the board and reopen a prior scene/result after restarting Study. Compare original copied board/PDF/audio/gallery/image hashes. Open independent and opener-created Canvas tabs; edits and reloads must retain distinct drafts in supported Chromium.
7. On a copied scanned PDF with unavailable German OCR, confirm `ocr_error` and a retryable page, not false completion. If the machine already has the required working OCR engine/language, use the explicit bounded retry button, then resume subsequent batches. Record unavailable cases as SKIP/BLOCKED; do not install the language silently.
8. Run the security tests: foreign Host/Origin and missing/wrong CSRF tokens must produce no mutations for POST/PUT/DELETE; legitimate same-origin UI and token-bearing local clients must work. Do not expose Study on a public interface to test this.

Accept real ComfyUI only with logs and an actual produced/reopened PNG at the exact tested integration SHA. Record physical microphone, touch/high-DPI, real OCR accuracy and GPU inference separately from automated Chromium fixtures. No merge follows automatically from passing tests.
