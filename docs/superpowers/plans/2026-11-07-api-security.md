# Local API protection implementation plan

Goal: close the independently reproduced Host/Origin/CSRF vulnerability without bypasses for future mutation routes.
Spec: direct P0 remediation instructions in D, 2026-11-07; original issue #7.
Architecture: a shared HTTP request gate, invoked by Handler.parse_request before dispatch. Only literal loopback authorities with the actual listening port are trusted. A per-server random token obtained from a no-store same-origin bootstrap endpoint is mandatory for every mutation, including clients without Origin. C owns browser fetch integration; D owns OCR retry.
Tech stack: Python stdlib HTTP, secrets; unittest with real loopback HTTP.

- [ ] Reproduce hostile Host/Origin and absent-Origin mutations with live HTTP tests, verify RED.
- [ ] Implement api_security.py and global dispatch gate; expose GET /v1/security/bootstrap.
- [ ] Verify duplicate headers, wrong ports, absolute request targets, opaque Origin and Sec-Fetch-Site denial; verify legitimate token-bearing requests.
- [ ] Forward PDF retry without truthiness coercion (D integration).
- [ ] Run full unittest, document client contract, commit and push A branch; coordinate C/D exact SHA.

Review focus: token disclosure via rebinding, duplicate authorities, missing Origin forgery, iframe compatibility, future route coverage. No CORS grant, no Windows settings/model installation, no merge. Existing remote A implementation at ad39a25 is reused rather than rewritten.
