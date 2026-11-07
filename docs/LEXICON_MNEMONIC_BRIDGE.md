# Study lexicon-to-mnemonic bridge (experimental)

The mnemonic editor now accepts arbitrary German lemmas and user-confirmed Russian meanings, with optional article. Existing three demo words remain hand-curated. This removes the three-word restriction from mnemonic creation **without fabricating translations**.

The translator's German word tokens can be copied into the mnemonic editor with one click; the dictionary results include a "Create mnemonic" action. The learner must verify meaning and article before saving. Imported Wiktextract glosses may be in English and are not reliable DE↔RU alignments.

## Windows smoke test
1. Update the docs/study-architecture-v0.1 branch and run `py -m unittest discover -v`.
2. Run `py web_app.py` and open localhost:8766.
3. Enter `Freiheit`, choose `die`, enter `свобода`; add two user-created sound-object-meaning anchors; save.
4. Open saved scene and verify the SVG and review prompt use the new lemma and meaning.
5. Type `Ich liebe die Freiheit.` in Sentence Studio and click the `Freiheit` token; it should populate the mnemonic word field.
6. Do not infer that an Argos package, large dictionary, or German/Russian verified sense link has been installed.

## Known limitations
- Existing demo entries override user-supplied article/meaning.
- User-authored translations are not lexicographically validated.
- Sentence tokens are not lemmatized, so inflected forms may be selected.
- No automatic bulk download or audited complete dictionary yet.
- SQLite prototype remains single-user, loopback-only, and not production hardened.
