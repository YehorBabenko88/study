# Semantic Composer Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans; the user authorized continuous implementation without another approval gate.

**Goal:** Deliver the independent, testable semantic scene composer for issue #8.
**Architecture:** Pure graph compiler plus detached JSON snapshots; SQLite append-only revision/job store. Existing backend and UI files remain unchanged.
**Tech Stack:** Python 3.10+, standard library, unittest, SQLite.
**Spec:** docs/SEMANTIC_COMPOSER_DESIGN.md

## Global Constraints

Own branch from docs/study-architecture-v0.1; Draft PR only. No merge or deletion.
No image-conditioned support claim without actual image transmission.
Only new composer module, tests and documentation may change.

## Review Focus

Malformed JSON values and control characters; high-degree cyclic graphs;
parallel revision writers; mutation of loaded snapshots; failed/retried jobs.

### Task 1: Deterministic graph compiler

Files: prototype/semantic_composer.py, prototype/test_semantic_composer.py.
Interface: compose(graph, roots, *, direction='outgoing', max_depth=4,
max_nodes=24, max_edges=64, parameters=None, user_prompt=None) -> dict.

- [ ] Write tests for deterministic typed directed scenes, cycles, input and output limits, reference manifests, unchanged originals.
- [ ] Run unittest and observe missing implementation failure.
- [ ] Implement compiler and strict validation with canonical snapshots.
- [ ] Run focused tests to green.

### Task 2: Append-only provenance and adapter boundary

Same files; add docs/SEMANTIC_COMPOSER_CONTRACT.md.
Interface: CompositionStore(path).create/revise/get/history/record_job/record_result/job_history;
generation_request(revision) -> text-only request or explicit unsupported-mode error.

- [ ] Write failing tests for durable immutable versions, concurrent writers, job/result provenance, invalid requests and disabled image mode.
- [ ] Implement SQLite append-only API and safe detached request builder.
- [ ] Run focused tests, full prototype unittest suite, diff checks.
- [ ] Document exact contract, limitations and verification; commit and push own branch, create Draft PR.
