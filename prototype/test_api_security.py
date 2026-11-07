"""Real HTTP regression tests: rejecting a request must precede side effects."""
import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch
import web_app


class APISecurityTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), web_app.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.authority = '127.0.0.1:' + str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, method, path, headers=(), body=b''):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        try:
            conn.putrequest(method, path, skip_host=True)
            for name, value in headers:
                conn.putheader(name, value)
            conn.putheader('Content-Length', str(len(body)))
            conn.endheaders(body)
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            conn.close()

    def token(self):
        status, headers, raw = self.request('GET', '/v1/security/bootstrap', [('Host', self.authority)])
        self.assertEqual(status, 200)
        self.assertEqual(headers.get('Cache-Control'), 'no-store')
        self.assertNotIn('Access-Control-Allow-Origin', headers)
        return json.loads(raw)['csrf_token']

    def test_foreign_host_blocks_reads_and_mutations_before_dispatch(self):
        with patch.object(web_app, 'delete_scene') as delete:
            for method, path in [('GET', '/health'), ('GET', '/v1/security/bootstrap'), ('DELETE', '/v1/mnemonics/id')]:
                with self.subTest(method=method, path=path):
                    self.assertEqual(self.request(method, path, [('Host', 'evil.example:' + str(self.server.server_port))])[0], 403)
            delete.assert_not_called()

    def test_absent_origin_and_missing_token_cannot_mutate(self):
        with patch.object(web_app, 'delete_scene') as delete:
            for method in ('POST', 'PUT', 'DELETE', 'PATCH'):
                with self.subTest(method=method):
                    self.assertEqual(self.request(method, '/v1/mnemonics/id', [('Host', self.authority)])[0], 403)
            delete.assert_not_called()

    def test_token_and_same_origin_allow_mutation(self):
        token = self.token()
        with patch.object(web_app, 'delete_scene', return_value=True) as delete:
            for origin in (None, 'http://' + self.authority):
                headers = [('Host', self.authority), ('X-Study-CSRF', token)]
                if origin:
                    headers.append(('Origin', origin))
                self.assertEqual(self.request('DELETE', '/v1/mnemonics/id', headers)[0], 200)
            self.assertEqual(delete.call_count, 2)

    def test_untrusted_origin_cannot_use_valid_token(self):
        token = self.token()
        for origin in ('null', 'https://' + self.authority, 'http://evil.example', 'http://127.0.0.1:1', 'http://' + self.authority + '/', 'http://localhost:' + str(self.server.server_port)):
            with self.subTest(origin=origin):
                headers = [('Host', self.authority), ('Origin', origin), ('X-Study-CSRF', token)]
                self.assertEqual(self.request('DELETE', '/v1/mnemonics/id', headers)[0], 403)

    def test_ambiguous_headers_wrong_ports_and_absolute_targets_rejected(self):
        token = self.token()
        cases = [
            [], [('Host', '127.0.0.1')], [('Host', '127.0.0.1:1')],
            [('Host', self.authority), ('Host', self.authority)],
            [('Host', self.authority), ('Origin', 'http://' + self.authority), ('Origin', 'http://' + self.authority)],
            [('Host', self.authority), ('X-Study-CSRF', token), ('X-Study-CSRF', token)],
            [('Host', self.authority), ('X-Study-CSRF', 'wrong')],
            [('Host', self.authority), ('X-Study-CSRF', token), ('Sec-Fetch-Site', 'cross-site')],
        ]
        for headers in cases:
            with self.subTest(headers=headers):
                self.assertEqual(self.request('DELETE', '/v1/mnemonics/id', headers)[0], 403)
        self.assertEqual(self.request('GET', 'http://evil.example/health', [('Host', self.authority)])[0], 403)

    def test_loopback_alias_read_and_cross_site_bootstrap(self):
        for host in ('localhost:' + str(self.server.server_port), self.authority):
            self.assertEqual(self.request('GET', '/health', [('Host', host)])[0], 200)
        self.assertEqual(self.request('GET', '/v1/security/bootstrap', [('Host', self.authority), ('Sec-Fetch-Site', 'cross-site')])[0], 403)

    def test_foreign_boundary_all_methods_has_no_side_effects(self):
        token=self.token()
        with patch.object(web_app,'delete_scene') as delete, patch.object(web_app,'create_document') as upload, patch.object(web_app,'process_document') as process, patch.object(web_app,'comfy_submit') as generate:
            cases=[('POST','/v1/comfy/generate',b'{"prompt":"cup"}'),('PUT','/v1/documents',b'%PDF-1.4'),('DELETE','/v1/mnemonics/id',b''),('OPTIONS','/v1/documents',b'')]
            for method,path,body in cases:
                for boundary in ('host','origin'):
                    with self.subTest(method=method,boundary=boundary):
                        headers=[('Host','evil.example' if boundary=='host' else self.authority),('X-Study-CSRF',token)]
                        if boundary=='origin':headers.append(('Origin','http://evil.example'))
                        status,received,raw=self.request(method,path,headers,body)
                        self.assertEqual(status,403)
                        self.assertNotIn('Access-Control-Allow-Origin',received)
            for mock in (delete,upload,process,generate):mock.assert_not_called()

    def test_legitimate_token_all_mutating_methods(self):
        token=self.token();headers=[('Host',self.authority),('Origin','http://'+self.authority),('X-Study-CSRF',token)]
        with patch.object(web_app,'comfy_submit',return_value={'status':'queued'}) as generate,patch.object(web_app,'create_document',return_value={'status':'queued'}) as upload,patch.object(web_app,'delete_scene',return_value=True) as delete:
            self.assertEqual(self.request('POST','/v1/comfy/generate',headers,b'{"prompt":"cup"}')[0],200)
            self.assertEqual(self.request('PUT','/v1/documents',headers,b'%PDF-1.4')[0],200)
            self.assertEqual(self.request('DELETE','/v1/mnemonics/id',headers)[0],200)
            for mock in (generate,upload,delete):self.assertEqual(mock.call_count,1)
        # An unimplemented same-origin preflight is harmless and exposes no CORS.
        status,received,_=self.request('OPTIONS','/v1/documents',[('Host',self.authority)])
        self.assertEqual(status,501);self.assertNotIn('Access-Control-Allow-Origin',received)


if __name__ == '__main__':
    unittest.main()
