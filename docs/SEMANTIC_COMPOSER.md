# Semantic composer (issue #8)

`prototype/semantic_composer.py` is a pure, additive module. It does not modify storage, existing board validation, UI, adapter behavior, or original media.

## Interface

- `compose(document, root_id, max_depth=3, max_nodes=64)` accepts existing board node types and relations. Incident edges are traversed breadth-first (both directions); edge directions are retained in prompt relations. Stable IDs determine ordering. Limits are depth 0–32, selected nodes 1–256, graph 10,000 nodes/30,000 edges, and prompt 8,192 characters. HTML and control characters are removed; concept labels are limited to 240 characters. This is descriptive sanitization, not an LLM instruction security boundary.
- Result includes `prompt`, `prompt_truncated`, `node_ids`, `provenance`, `generation_mode`, and `reference_images_used`. Provenance retains node IDs, scene IDs and gallery asset IDs; asset bytes are never loaded or changed. Asset identifiers are opaque local provenance, not resolved/validated media references.
- `add_link` and `remove_link` return `(new_document, undo_token)` without mutating input. `undo_link(new_document, token)` reverses the edge change while preserving later node/gallery edits. Conflicting edge edits raise rather than overwrite. Tokens are local ephemeral values; callers own undo history and persistence.

## Integration boundary

No route or frontend is wired in this PR, because those files are owned by parallel agents. A server route can pass a validated board snapshot and root ID to `compose`, show the prompt/provenance for review, then send the prompt to its existing generation API. Original image galleries remain independent of prompt planning.

The only supported mode is **text-to-image**. `use_references=True` raises. Having image nodes or asset provenance does not mean their pixels reached ComfyUI. A future image-conditioned workflow must explicitly implement capability checks, opt-in and actual image loading before reporting references used.

## Validation

`python -m unittest discover -s prototype -p test_semantic_composer.py`

The tests cover deterministic ordering, cycles, bounds, plain and encoded markup, prompt truncation, provenance, reference refusal, invalid graphs, immutable edits, non-destructive undo, duplicate links and conflict refusal. Tests perform no database, network, model or system writes.
