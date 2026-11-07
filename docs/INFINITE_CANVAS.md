# Study Infinite Canvas v0.1

A new canvas route `/canvas` offers a zoomable, pannable spatial graph for language construction. Nodes are typed: word, syllable, image (text placeholder), sentence, note. Users can drag nodes, link any two, split user-marked hyphenated syllables, paste up to 1,500 tokens per operation and save/reopen boards in SQLite. Board graph schema supports 10,000 nodes and 30,000 edges, but performance at these sizes is **not benchmarked**.

The canvas has a soft Trello-inspired blue palette, airy white cards and a dotted workspace, without copying proprietary logos or artwork.

## Limitations
- This is a browser DOM canvas, not a high-performance virtualized engine. A whole book should be imported as chunks/pages, not rendered all at once.
- Image nodes are placeholders for now. Attaching media and linking to existing mnemonic image assets is a future integration.
- No automatic syllabification: users enter `Tas-se` to create two sound nodes. German hyphenation is not always equivalent to phonetic syllables.
- Sentence word order is represented by directed edges but not yet enforced by a grammar engine.
- The board is single-user, no authentication, undo/redo, keyboard-accessible dragging or multiuser synchronization.
- Saving overwrites the current board snapshot. Backup the SQLite database before experimentation.
- Existing vocabulary importer and translation setup remain independent and are **not** complete dictionaries.

## Run
Update the draft branch, run unit tests, start `py web_app.py`, open `http://127.0.0.1:8766/canvas`. Use the sidebar to create and connect nodes. Wheel zooms, dragging a blank area pans, dragging a card moves it. Save and reopen the board to test persistence.
