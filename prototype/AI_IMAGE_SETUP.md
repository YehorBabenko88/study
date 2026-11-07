# Optional AI image provider (experimental)

Study now supports **opt-in** image generation from saved mnemonic scenes using an OpenAI-compatible image generation endpoint. The default behavior remains offline SVG. No automatic paid requests. Only generate after clicking the button. This is an adapter, **not** a guarantee that any particular provider supports `response_format=b64_json`.

In PowerShell, before starting `py web_app.py`, set:
```powershell
$env:STUDY_IMAGE_API_URL="https://YOUR-PROVIDER.example/v1/images/generations"
$env:STUDY_IMAGE_MODEL="YOUR-IMAGE-MODEL"
$env:STUDY_IMAGE_API_KEY="YOUR_SECRET_KEY"
py web_app.py
```
Never commit keys to GitHub or paste them into chat. Check provider billing, retention, endpoint compatibility and model licensing first. The API key and mnemonic text are transmitted to the configured provider over HTTPS. Avoid personal data in mnemonics.

After creating and saving a scene, click Generate AI image. Optionally describe changes to the scene. Each generation may incur charges. A saved PNG replaces the prior generated PNG for the same scene. The SVG storyboard remains available independently.

**Limits:** synchronous request (90-second timeout), single user, no auth, no queue, no rate/cost limits beyond manual button, no cloud response caching, no AI video, no speech. Use only on loopback for testing. Future production design requires asynchronous jobs, quotas, consent UI, provider allowlist, cancellation, retries and durable asset versioning.
