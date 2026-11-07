# Study Language Programming Canvas — multimodal graph v0.3

The user can build a language graph from **letters, phonetic syllables, words, sentences, images, actions and notes**. Nodes can be positioned freely; directed edges are typed as association, part_of, sequence, meaning, sound or action. Links are user-authored associations, **not automatically verified grammar facts**.

## Images from other programs
Drag a PNG, JPEG or WebP file from Explorer into the canvas. It is decoded with Pillow, normalized to RGB PNG, stripped of EXIF metadata and saved under `prototype/board_assets`. Board documents reference asset UUIDs. Clipboard-paste and remote image URL import are not yet implemented. The existing mnemonic gallery can also attach saved scenes. Only use images you have rights to use.

## German book scans
Select an image of a page and click **Распознать страницу (DE)**. Optional OCR uses pytesseract plus a locally installed Tesseract executable and German traineddata (`deu`). The user must review recognized text before converting it into individual word nodes. No text is sent to a cloud OCR service. OCR accuracy varies with typography, skew, scans and old German Fraktur; this is not a verified transcription. PDF multi-page ingestion is not implemented.

Install optional Python package:
```powershell
cd "$HOME\Desktop\study\prototype"
.\.venv\Scripts\python.exe -m pip install pytesseract
```
Separately install Tesseract OCR for Windows from a trusted distribution and verify `tesseract --list-langs` includes `deu`. If absent, the API returns an unavailable status. This prototype intentionally does not silently install system software.

## Workflow
1. Paste a paragraph or OCR a page; review the text.
2. Split it into draggable word nodes, with directed sequence links.
3. Create a sentence node and link its words using `part_of`.
4. For a selected word, type manually segmented phonetic chunks (e.g. `Tas-se`) and generate syllable nodes.
5. Attach existing mnemonic scenes or drag external pictures to create image nodes.
6. Connect syllables to images with `sound` or `association`, words to meanings with `meaning`, and sentence nodes to action nodes with `action`.
7. Save/reopen the board; use undo/redo for recent changes.

## Remaining engineering gates
- Render virtualization and viewport culling for thousands of nodes
- Page groups and subgraphs, edge routing, keyboard accessibility, redo/undo persistence
- Robust browser E2E tests and performance benchmarks
- OCR bounding boxes and page-layout preservation; PDF ingestion
- Automatic German morphology, phoneme segmentation, sense disambiguation, syntax validation
- Real animation and AI image generation
- Dataset import and audited DE/RU dictionary coverage

Do not claim these pending features are complete. The server is local-only and lacks multiuser authentication. Back up `study_local.sqlite3` plus `board_assets/` and `generated_media/` together.
