# P0/P1 remediation implementation plan

> Execution: inline with agent A owning API security and C owning shared UI. User explicitly authorized ordinary fixes/tests without further approvals.

Goal: close the two proven defects and independently re-accept exact integrated commits without deleting historical evidence or merging PRs.

Architecture: keep the local Python HTTP server and SQLite schema. A adds a central mutation security gate. D records retryable per-page OCR outcomes and preserves successful pages. C exposes Retry and updates same-origin UI requests for the agreed security contract.

Constraints: PR #14 stays Draft; no merge, user data deletion, system changes or language/model installation. Historical qa/evidence remains unchanged.

Review focus: absent Origin forgery; forged Host/port; OCR failure after successful pages; old completed ocr_unavailable records; legitimate browser mutation flows.

1. Coordinate shared-file owners through existing A/C chats. Pin A/B/C heads.
2. RED: test missing OCR language, explicit retry after recovery, no_text distinct from OCR failure, preservation of prior text/PDF, migration of legacy error pages.
3. GREEN: modify document_import.py process(pid,batch=2,ocr=False,retry=False); failed OCR must not advance next_page, explicit retry selects only eligible pages; retain schema and original bytes. Page methods pdf_text/no_text/tesseract_unverified/ocr_no_text/ocr_error distinguish outcomes.
4. A owns web_app.py/security tests and dispatch gate; request retry parameter forwarded. C owns canvas.html Retry/status UI and any CSRF fetch changes.
5. Integrate reviewed exact commits A/B/C on this branch without merging external PRs; run unittest discover and all discovered browser modules with a live isolated server; independent negative API matrix plus 150-page kill/resume/OCR retry, real galleries and mock ComfyUI.
6. Fresh review, separate timestamped evidence/report with exact HEADs/commands, push updates to Draft PR #14. Keep FAIL/NO-GO until the two defect checks pass; distinguish unavailable real OCR/ComfyUI.

Verification commands: project venv Python -m unittest discover -s prototype -v; PowerShell qa/acceptance.ps1 using a new EvidenceRoot. No mandatory skips accepted in browser pass.
