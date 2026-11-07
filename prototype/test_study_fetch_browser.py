import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright=None


@unittest.skipUnless(sync_playwright and os.getenv('STUDY_E2E_URL'),'Requires live browser acceptance')
class StudyFetchBrowserTests(unittest.TestCase):
    def test_mutations_include_csrf_and_preserve_request_body(self):
        seen=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                data=b'{"csrf_token":"test-only-token"}' if self.path=='/v1/security/bootstrap' else b'<html><body>Study test</body></html>'
                self.send_response(200);self.end_headers();self.wfile.write(data)
            def do_POST(self):
                seen.append((self.headers.get('X-Study-CSRF'),self.rfile.read(int(self.headers.get('Content-Length','0')))))
                self.send_response(200 if seen[-1][0]=='test-only-token' else 403);self.end_headers()
            do_PUT=do_POST
            do_DELETE=do_POST
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            with sync_playwright() as play:
                browser=play.chromium.launch()
                try:
                    page=browser.new_page();page.goto(f'http://127.0.0.1:{server.server_port}/')
                    path=Path(__file__).with_name('study-fetch.js')
                    if path.exists():page.add_script_tag(path=str(path))
                    for method in ('POST','PUT','DELETE'):
                        result=page.evaluate('''async method => {const req=new Request(location.origin+'/mutation',{method,body:'payload'});return (await fetch(req)).status}''',method)
                        self.assertEqual(result,200)
                    self.assertEqual(seen,[('test-only-token',b'payload')]*3)
                    foreign=ThreadingHTTPServer(('127.0.0.1',0),Handler)
                    threading.Thread(target=foreign.serve_forever,daemon=True).start()
                    try:
                        page.evaluate('''async url => {try {await fetch(url,{method:'POST',body:'foreign'});}catch(error) {}}''',f'http://127.0.0.1:{foreign.server_port}/mutation')
                        self.assertEqual(seen[-1],(None,b'foreign'),'CSRF token must never be sent to another origin')
                    finally:foreign.shutdown();foreign.server_close()
                finally:browser.close()
        finally:server.shutdown();server.server_close()
