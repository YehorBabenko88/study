# Study final integration implementation plan

> Execution: user explicitly requested immediate implementation and independent D acceptance; no extra approval gate. Root coordinates disjoint A/B/C changes in one new integration checkout.

Goal: connected graph → reviewed scene revision → durable generation → immutable PNG/result history, preserving all existing data.

Architecture: #16 is canonical composer v1. #11 link edits live separately, without replacing compiler semantics. A's local queue owns execution IDs; the composition service journals request/revision bindings and stores immutable asset results. Existing Study storage stays in place; additional composition history is additive.

Constraints: no merge, no models, no changes to PR1 or agent branches. Text-to-image only; no false image-conditioning claims. All mutation routes require loopback Host/Origin validation and per-server CSRF token.

Review focus: restart between queue submission and history recording; concurrent duplicate requests; cancel versus completion; legacy OCR-unavailable pages; drafts/gallery/audio/PDF reopening.

- [x] Audit and import A12, C13, D15 and canonical B16 into new branch; inspect B11 and QA14.
- [x] A: regression tests then verify/fix HTTP boundary and retryable OCR, preserving existing extracted text and original PDF. Test150-page interrupted resume and explicit retry.
- [x] B: compare contracts, extract immutable link edits; implement composition_service.dispatch(method,path,data), parameter-complete queue submission, durable result reconciliation and non-overwriting asset storage. Test idempotency, failures, restarts and provenance.
- [x] Root: failing HTTP tests for bootstrap injection/composition routing/OCR retry, then wire bounded API dispatch and trusted static scripts. Preserve all old routes.
- [x] C: selection, description, edit, revise, generate/cancel, history and result reopening in Canvas. Real browser tests exercise mock generation and preservation.
- [ ] Root: full unittest and actual Playwright on committed exact HEAD, then D independent acceptance on same SHA. Fix failures with regressions and repeat affected gates.
- [ ] Publish separate integration Draft PR with exact SHA, provenance of imported heads, test evidence, limitations and Windows physical test plan. Keep MERGE_NO-GO and real-Comfy gate explicit.

Development gates: complete unit discovery passed before freeze; targeted C six-browser and D two-process-retention suites passed after review fixes. Final exact-HEAD evidence is emitted outside the checkout by root and independent D; publication never authorizes merge.
