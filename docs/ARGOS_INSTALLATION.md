# Study translation model setup — controlled installation

Argos Translate is an optional local inference engine. Installing its Python package does not automatically install language packs. Direct German↔Russian packages may be absent; English pivot translation may be needed and can lose meaning. Do not silently claim translation quality.

## Windows
Use Python 3.12 in an isolated environment when Argos dependencies do not support your Python 3.15 installation:

```powershell
cd "$HOME\Desktop\study\prototype"
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install Pillow argostranslate
.\.venv\Scripts\python.exe translation_models.py installed
.\.venv\Scripts\python.exe translation_models.py candidates
```

The `candidates` command refreshes Argos's online package index (network request), but does not download or install model weights. Review package origin, license, size and direction before downloading an `.argosmodel` package from the Argos project catalog. Once reviewed and downloaded, install explicitly:

```powershell
.\.venv\Scripts\python.exe translation_models.py install --file "C:\StudyData\reviewed-de-ru.argosmodel" --yes
.\.venv\Scripts\python.exe web_app.py
```

The filename is illustrative, not an assertion that a direct DE→RU package exists. Run `installed` after installation to inspect languages. The current translator requires an installed language route that Argos can resolve. If no route exists, the UI reports unavailable instead of inventing a translation.

## Quality gates
- Validate 50+ German/Russian sentences for word order, negation, cases, separable verbs, articles and ambiguity.
- Treat machine translations as suggestions, not verified dictionary senses.
- Do not upload learner text to cloud without consent.
- Keep Argos behind the replaceable translation API.
