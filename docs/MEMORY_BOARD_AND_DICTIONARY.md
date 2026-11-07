# Memory Board and full-dictionary roadmap

## Interface
Study now includes a four-column board inspired by the user's reference screenshot:
1. Dictionary / word cards
2. Phonetic syllables → image objects → actions
3. Sentence composer and translation
4. Saved mnemonic library

Open `http://127.0.0.1:8766/board` after updating and restarting Study. This is a responsive browser board, not a copy of Trello branding. It uses the existing SQLite scenes and APIs.

## Translation models on the user's Windows machine
The supplied console log confirms Argos Translate 1.11.0 is installed in Python 3.12 but **no models** are installed. The index lists only `de→en`, `en→ru`, `ru→en`, `en→de` for the needed languages. There is no direct DE↔RU model in that output.

A separate installer `install_pivot_models.py` can install the four available packages **only when explicitly invoked with --yes**. It downloads weights and may take time/disk space. Review each package's license, size and privacy policy before running; network and model compatibility may change.

```powershell
cd "$HOME\Desktop\study\prototype"
.\.venv\Scripts\python.exe install_pivot_models.py --yes
.\.venv\Scripts\python.exe translation_models.py installed
.\.venv\Scripts\python.exe web_app.py
```

The installed Argos library may or may not resolve a pivot route automatically; verify actual DE→RU and RU→DE sentences. Pivoting can lose gender, context and meaning.

## Full dictionary
The existing `lexicon_store.py` streams an arbitrary-size Wiktextract JSONL/GZ dataset, but **no real dictionary dump has been imported yet**. To get broad coverage:
- Obtain audited German and Russian Wiktionary snapshots, verify URLs, SHA256 and licensing
- Import into separate source namespaces; preserve sense, form, translation, provenance
- Build sense-level DE↔RU alignment with uncertainty and human review
- Index inflected forms, phrases and compound words
- Add resumable atomic import and periodic updates
- Benchmark PostgreSQL backend for large corpora

Do not claim full DE↔RU lexical coverage merely from raw German and Russian Wiktionary entries. The board can already make personal cards for arbitrary words with user-confirmed meanings.
