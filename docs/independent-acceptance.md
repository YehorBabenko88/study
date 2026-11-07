# Independent acceptance for Study issue #10

Run from PowerShell with Python dependencies already installed:

```powershell
./scripts/acceptance.ps1 -Python ../venv/Scripts/python.exe -BrowserUrl http://127.0.0.1:8768
```

Use a disposable Study server and temporary data for browser tests. The runner does not start servers, install dependencies/models, merge branches, or delete user data. `-LogDirectory` defaults to a newly named temporary directory. Existing log files at an explicitly supplied location can be overwritten. `STUDY_E2E_URL` is restored on exit. Set `PLAYWRIGHT_BROWSERS_PATH` externally if using a nondefault browser installation.

The static/unit phase includes source-string UI contracts; these are not browser verification. It reports discovered total, actual PASS, SKIP, and failures independently. The browser phase discovers every `test_*browser*.py`; any skip makes browser acceptance fail. Browser logs clearly identify actual Chromium checks. The independent generation browser test uses a fake loopback Comfy service and real Study HTTP routes/worker/PNG storage; it is not real-model acceptance.

The added synthetic PDF tests cover 150-page persisted resume through a fresh module instance, one row per page, missing German OCR language data, invalid PDFs/identifiers, filename traversal isolation, and Windows temporary file/database cleanup. OCR failure is injected deterministically; no claim is made about installed OCR language availability or recognition accuracy. PyMuPDF fixtures use the maintained `pymupdf` import; existing production `fitz` imports remain a supported PyMuPDF alias and were not replaced by this QA change.

The HTTP generation test checks submit, polling, PNG retrieval, and denial of an unowned filename. The Chromium generation check clicks the actual button, accepts its dialog, waits for the generated card, verifies original nodes remain unchanged, checks the new association, and retrieves the stored gallery PNG. Every fixture uses its own temporary directory, closes SQLite connections explicitly, closes HTTP servers and browser contexts, and never cleans an existing Study data directory.

## Scope gates

Passing prepared-scope acceptance does not complete issue #10. Real ComfyUI/model execution needs a separately available reviewed local installation. Semantic composer integration into the existing browser generation flow and image-reference conditioning remain separate implementation gates. Current generation is text-to-image; reference images are not model inputs. Cancellation is local and upstream work may continue. The adapter bounds socket inactivity and body reads, but slow response headers are not a strict end-to-end wall-clock deadline. No merge or deployment is authorized by these test results.
