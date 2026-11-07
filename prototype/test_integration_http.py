"""HTTP integration boundary tests; no learner storage or real models."""
import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch
import web_app


class IntegrationHTTPTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), web_app.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        _, raw = self.request('GET', '/v1/security/bootstrap')
        self.token = json.loads(raw)['csrf_token']

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()

    def request(self, method, path, body=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=4)
        try:
            headers = {'Content-Type': 'application/json'}
            if hasattr(self, 'token'): headers['X-Study-CSRF'] = self.token
            connection.request(method, path, json.dumps(body).encode() if body is not None else None, headers)
            response = connection.getresponse()
            return response.status, response.read()
        finally: connection.close()

    def test_every_html_view_bootstraps_mutations_before_inline_code(self):
        for path in ('/', '/workspace', '/canvas', '/phonovision-3d', '/acoustic-studio', '/legacy-study', '/legacy-board', '/legacy-spectral-relief'):
            with self.subTest(path=path):
                status, raw = self.request('GET', path)
                self.assertEqual(status, 200)
                self.assertIn(b'<script src="/study-fetch.js"></script>', raw)
                self.assertLess(raw.index(b'/study-fetch.js'), raw.index(b'</head>'))

    def test_composition_dispatch_is_behind_shared_csrf_gate(self):
        with patch.object(web_app, 'composition_dispatch', create=True, return_value=(200, {'revision_id': 'test'})) as dispatch:
            status, raw = self.request('POST', '/v1/compositions', {'graph': {}, 'roots': ['a']})
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(raw)['revision_id'], 'test')
            dispatch.assert_called_once_with('POST', '/v1/compositions', {'graph': {}, 'roots': ['a']})
            del self.token
            self.assertEqual(self.request('POST', '/v1/compositions', {})[0], 403)
            self.assertEqual(dispatch.call_count, 1)

    def test_ocr_retry_preserves_boolean_validation(self):
        with patch.object(web_app, 'process_document', return_value={'status': 'complete'}) as process:
            status, _ = self.request('POST', '/v1/documents/test/process', {'batch': 2, 'ocr': True, 'retry': True})
            self.assertEqual(status, 200)
            process.assert_called_once_with('test', 2, True, True)
