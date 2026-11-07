"""Request boundary for the unauthenticated, loopback-only Study demo.

This is browser CSRF/rebinding protection, not authentication against local apps.
Never trust forwarded host/origin headers or publish the bootstrap with CORS.
"""
import re
import secrets
import threading

_token_lock = threading.Lock()
SAFE_METHODS = frozenset(('GET', 'HEAD', 'OPTIONS'))


def csrf_token(server):
    """One unpredictable token per server instance, shared across its threads."""
    with _token_lock:
        if not hasattr(server, '_study_csrf_token'):
            server._study_csrf_token = secrets.token_hex(32)
        return server._study_csrf_token


def _single(headers, name):
    values = headers.get_all(name, [])
    return values[0] if len(values) == 1 else None


def rejection(handler):
    """Return a stable error code, or None; run before any route dispatch."""
    port = handler.server.server_port
    hosts = {f'127.0.0.1:{port}', f'localhost:{port}', f'[::1]:{port}'}
    host = _single(handler.headers, 'Host')
    if host not in hosts:
        return 'untrusted_host'
    # Only origin-form request targets; proxy-style absolute targets are ambiguous.
    if not handler.path.startswith('/') or handler.path.startswith('//'):
        return 'invalid_request_target'
    origins = handler.headers.get_all('Origin', [])
    if origins and (len(origins) != 1 or origins[0] != 'http://' + host):
        return 'untrusted_origin'
    sites = handler.headers.get_all('Sec-Fetch-Site', [])
    if len(sites) > 1 or (sites and sites[0] not in ('same-origin', 'same-site', 'none')):
        return 'untrusted_fetch_site'
    if handler.command not in SAFE_METHODS:
        token = _single(handler.headers, 'X-Study-CSRF')
        if not token or not re.fullmatch(r'[0-9a-f]{64}', token) or not secrets.compare_digest(token, csrf_token(handler.server)):
            return 'csrf_token_required'
    return None
