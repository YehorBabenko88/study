# Study cross-panel composition — checkpoint

## Implemented
- `/workspace`: two resizable panes, free canvas and 3D Lab, using existing pages.
- Double-click a language node on `/canvas` to edit text in place; Ctrl+Enter saves, Escape cancels.
- Drag the dedicated `↗ В 3D Lab` handle from a node into the 3D Lab composition zone; its text is appended to an editable image description.
- Drop an external PNG/JPEG/WebP image into the composition zone or select it with the file picker.
- Save the selected reference to Study assets, then drag its preview into the free canvas as an image node.
- Three-tab navigation now also exposes a two-panel work mode.
- Home provides a direct-to-canvas checkbox; the project text is not required to be visually reviewed first.

## Known gaps
- A 150-page book cannot yet be imported as one job. Current OCR accepts one image, and shared speech metadata has a 10k-character cap. Large-scale book processing requires PDF page streaming, OCR queues, document/page/chunk storage, resumable tasks, and canvas virtualization. No claim of unlimited size is made.
- The composition area currently builds a prompt/reference **but does not generate an AI image**. The external ComfyUI/InvokeAI service is not installed, connected or tested.
- Two panels use iframes, which is an interim integration. They share the same localhost backend but not an in-memory editor store.
- Browser drag-and-drop behavior varies across browser implementations and iframe boundaries. E2E tests are still needed.
- The old card board remains archived; existing user data is not deleted.

## External engine assessment
- ComfyUI: best candidate for reusable node-based local image-generation workflows and API integration; requires GPU/CPU sizing, model licensing and resource limits. Core GPL-3.0 licensing should be reviewed for distribution.
- InvokeAI: good alternative for inpainting, layers, guided edits and artistic canvas workflows. Check license for individual dependencies/models.
- tldraw: mature infinite canvas SDK, but production use requires a license under its SDK terms.

## Next implementation gates
1. Build a provider-neutral image job API with explicit opt-in, safe workflow templates, status/cancel, model manifest, seed and image provenance.
2. Connect a reviewed local ComfyUI service over loopback, validate input and output paths, and store generated PNG in Study assets.
3. Add PDF/page import pipeline, OCR resume and database migrations.
4. Move the canvas and 3D composer into one application state to avoid iframe limitations.
5. Automated browser tests for editing, moving and dragging both directions.
