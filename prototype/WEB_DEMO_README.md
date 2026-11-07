# Local web API and UI (prototype)

From repository root:
```powershell
cd prototype
py web_app.py
```
Open `prototype/study.html` in a browser (as a file) and interact with the loopback API at 127.0.0.1:8766. Some browser security policies may block file-to-localhost requests; this demonstration deliberately does not enable permissive CORS. If blocked, use PowerShell `Invoke-RestMethod http://127.0.0.1:8766/health` to verify the API, and defer browser integration until a same-origin frontend server is implemented.

Endpoints: GET /health, GET /v1/lexicon/search?q=..., POST /v1/mnemonics/preview, POST /v1/learning/check.

**Not production ready:** Python stdlib HTTP server has basic security only; loopback-only, no authentication, rate limiting, durable DB, real translation, AI generation, or user isolation. Recall checker accepts the expected answer from the client, therefore is not secure and is only a demonstration. No cloud calls, database changes or automatic downloads.
