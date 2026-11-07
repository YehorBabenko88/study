# Semantic composer design — 2026-11-07

Approved scope: issue #8; standalone Python module, own branch, Draft PR to
`docs/study-architecture-v0.1`. Only new composer files are owned here.

Use Python standard library and the existing board node/edge vocabulary. A pure
compiler validates JSON input, preserves a detached canonical snapshot of the
whole source graph, and performs deterministic breadth-first traversal. Direction
defaults to outgoing; incoming/both are explicit options. Selected induced edges
keep their original direction and semantic type. Cycles terminate through visited
IDs. Hard input, traversal, reference and prompt limits reject oversized work
rather than silently dropping meaning. Depth boundaries are reported explicitly.

The output is one mnemonic scene description with typed elements and directed
relationship clauses, not a gallery. Raw graph text, suggested prompt, optional
user prompt and effective prompt remain separate. Original text is retained in
the snapshot; only prompt text is normalized for control characters/whitespace.
No claim of semantic interpretation beyond the explicitly represented relations.

An independent SQLite append-only repository stores canonical JSON revision and
job records. New revisions retain the composition ID and parent revision, with
new seed/parameters/prompt overrides; concurrent revision allocation is atomic.
Jobs and results are append-only events. Returned dictionaries are detached;
persisted snapshots cannot be updated through the public API. No board/gallery
or asset mutation; undo means choosing an older revision, not deleting history.

Text-to-image requests match existing comfy_adapter.submit(prompt, seed).
Image-conditioned preparation is intentionally unavailable until agent A supplies
an opt-in adapter that uploads real bytes and wires all uploaded references into
a reviewed compatible workflow. Reference manifests carry node and asset IDs;
they are provenance, never evidence that pixels reached ComfyUI.

Alternatives: direct canvas/backend modification gives immediate UI but overlaps
agent A; the approved standalone module offers an integration boundary and
preserves existing routes. UI and real image-conditioned workflows are deferred.

Verification: unittest tests for validation, all relation types and directions,
cycles, deterministic order, bounds, immutable snapshots, append-only persistence,
revision concurrency, job provenance, text contract and disabled image mode;
existing prototype suite for compatibility. No merge, deployment or data deletion.
