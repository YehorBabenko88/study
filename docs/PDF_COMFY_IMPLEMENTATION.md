# Study — PDF books and ComfyUI integration checkpoint

## PDF ingestion
- `PUT /v1/documents` accepts a PDF (up to 100 MB per request), stores it under `prototype/document_uploads` and records a resumable job in SQLite.
- `POST /v1/documents/<id>/process` accepts `{"batch":2,"ocr":false}`. Each page is extracted independently with PyMuPDF and committed before the next. On interruption, the next call resumes from the last committed page. Set `ocr:true` to try Tesseract German OCR on low-text scanned pages.
- `GET /v1/documents/<id>/pages/<zero-based-page>` retrieves text and provenance. The free canvas can turn a processed page into a sentence/page node and individual word cards.
- Viewport culling skips off-screen DOM cards. It is a first performance improvement, not full spatial indexing/virtualization. Do not add a whole 150-page book to a single canvas at once: use page batches and separate boards.

## ComfyUI
- The adapter calls **only** `http://127.0.0.1:8188` and only when `STUDY_COMFYUI_ENABLED=1`. It submits a controlled standard text-to-image workflow (CheckpointLoaderSimple → CLIP → KSampler → VAEDecode → SaveImage).
- It requires a model filename already installed and reviewed in ComfyUI's checkpoints folder. No weights are downloaded by Study.
- The 3D Lab composition panel can submit prompts, poll job history, show an output image, and drag it to the free canvas.
- The image route checks that a requested output belongs to the submitted job's ComfyUI history. This is a local-only prototype; before multiuser deployment add job ownership, auth, rate limits and strict provider isolation.
- No arbitrary user-supplied ComfyUI workflow JSON is executed.
- The model license and ComfyUI license need review for distribution. A GPU may be required for practical performance; CPU is possible for some models but may be slow.

## Windows setup
```powershell
cd "$HOME\Desktop\study"
git pull --ff-only origin docs/study-architecture-v0.1
cd prototype
.\.venv\Scripts\python.exe -m pip install PyMuPDF pytesseract
.\.venv\Scripts\python.exe -m unittest discover -v
.\.venv\Scripts\python.exe web_app.py
```
Install Tesseract OCR and German `deu` language data separately for scanned PDFs. PyMuPDF handles text-based PDFs without OCR. On Windows, make sure Tesseract is in PATH.

ComfyUI must be installed and started separately on loopback port 8188 with a reviewed checkpoint. Then launch Study in the same PowerShell session with:
```powershell
$env:STUDY_COMFYUI_ENABLED="1"
$env:STUDY_COMFYUI_CHECKPOINT="YOUR_REVIEWED_MODEL.safetensors"
.\.venv\Scripts\python.exe web_app.py
```
The checkpoint name above is a placeholder; it is **not** a downloadable model. Verify the exact checkpoint name and compatible workflow before running. Model architecture-specific workflows (SDXL/Flux etc.) may require different nodes; the current standard workflow is not universal.

## Not yet complete
- No full 150-page automatic background worker, progress streaming, cancellation or automatic board pagination.
- No page layout bounding boxes, image extraction, PDF document search or semantic sentence parsing.
- No browser E2E/Windows physical acceptance yet.
- ComfyUI service/model not installed or exercised on the user's machine.
- For real production, move to queued workers, bounded concurrency, resumable uploads, content hashing, migrations, quotas and auth.

## Parallel Codex tasks
A. PDF worker: robust resumable queue, OCR per page, cancellation, page provenance and large-book tests.
B. Canvas: spatial index/virtualization, page groups and progressive text-to-card import.
C. ComfyUI: verified checkpoint manifests, safe API client, job lifecycle, output asset ingestion, resource controls.
D. Independent integration/QA: browser E2E tests on Windows, cross-panel image transfer, data backup and failure recovery.

Each agent should work in a separate branch/PR, avoid changing the same files concurrently, and report exact test evidence. Do not merge or deploy without acceptance.
