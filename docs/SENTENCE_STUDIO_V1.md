# Sentence Studio v1 — German/Russian sentence translation

Study supports free-form sentence input, direction DE→RU or RU→DE, browser speech synthesis, clickable word tokenization and an optional local Argos Translate backend. The service never pretends a translation exists if the backend or language pack is missing.

## Installation
Run `py -m unittest discover -v` and `py web_app.py` as usual. The sentence UI will appear without extra dependencies but show an unavailable status until Argos and language packs are installed.

Argos Translate is optional. Check whether your Python version is supported; Python 3.15 may not yet have compatible wheels for the complete dependency chain. If needed, use a separate Python 3.12 virtual environment for the prototype:
```powershell
cd "$HOME\Desktop\study\prototype"
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install Pillow argostranslate
```
Argos packages are **separate** from the Python package. Install reviewed, compatible DE→RU and RU→DE model packages via Argos's documented package manager/API; not every direct language pair is available, and intermediate pivot translation may degrade accuracy. Do not install arbitrary packages from untrusted sites. Use the venv Python to start `web_app.py`.

## Limitations
- Free-form translation is optional and model-dependent; it is not guaranteed until compatible language packs are installed and tested.
- Clickable tokens are naive word boundaries, not morphological lemmatization. German inflected forms may not match the dictionary lemma.
- No full grammatical analysis, translation memory, sense alignment, sentence-to-mnemonic scene composition, or cloud translation provider yet.
- Browser TTS depends on installed voices.
- Sentence text stays local with Argos; it is not logged to learner DB by this prototype.
- No assumption that a machine translation is linguistically correct.
