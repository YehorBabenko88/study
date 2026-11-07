"""HTTP-to-worker-to-HTTP mock acceptance; no model/service download or execution."""
from contextlib import ExitStack
from pathlib import Path
import sys
import io
import json
import os
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from PIL import Image
import comfy_adapter as comfy
import web_app

@unittest.skipUnless(hasattr(comfy, 'JobRegistry'), 'Requires local Comfy job registry change')
class IndependentMockGeneration(unittest.TestCase):
    browser_hook = None
    def test_generate_poll_fetch_png_over_actual_http(self):
        output = io.BytesIO(); Image.new('RGB', (3,3), 'blue').save(output, format='PNG')
        png = output.getvalue(); remote = '12345678-1234-1234-1234-123456789012'
        class Fake(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def send(self,data):
                self.send_response(200); self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                assert body['prompt']['7']['class_type']=='SaveImage'
                self.send(json.dumps({'prompt_id':remote}).encode())
            def do_GET(self):
                if self.path.startswith('/view?'): return self.send(png)
                self.send(json.dumps({remote:{'status':{'completed':True},'outputs':{'7':{'images':[{'filename':'mock.png','subfolder':'','type':'output'}]}}}}).encode())
        fake=ThreadingHTTPServer(('127.0.0.1',0),Fake)
        app=ThreadingHTTPServer(('127.0.0.1',0),web_app.Handler)
        threads=[threading.Thread(target=s.serve_forever,daemon=True) for s in (fake,app)]
        for t in threads:t.start()
        try:
            with tempfile.TemporaryDirectory(prefix='study-mock-') as d, patch.dict(os.environ,{'STUDY_COMFYUI_ENABLED':'1','STUDY_COMFYUI_CHECKPOINT':'mock.safetensors'}),patch.object(comfy,'BASE',f'http://127.0.0.1:{fake.server_port}'):
                stack=ExitStack()
                for module in tuple(sys.modules.values()):
                    path=getattr(module,'__file__',None)
                    if path and Path(path).resolve().parent == Path(web_app.__file__).resolve().parent:
                        if hasattr(module,'DB'):stack.enter_context(patch.object(module,'DB',Path(d)/'study.sqlite'))
                        for key in ('ROOT','MEDIA','AUDIO_ROOT'):
                            if hasattr(module,key):
                                folder=Path(d)/(module.__name__+'-'+key);folder.mkdir(exist_ok=True)
                                stack.enter_context(patch.object(module,key,folder))
                registry=comfy.JobRegistry(d+'/jobs.sqlite',poll=.01,timeout=2)
                try:
                    with patch.object(comfy,'_registry',registry):
                        base=f'http://127.0.0.1:{app.server_port}'
                        with urlopen(base+'/v1/security/bootstrap') as r:token=json.load(r)['csrf_token']
                        with urlopen(Request(base+'/v1/comfy/generate',data=b'{"prompt":"blue cube","request_id":"independent-http"}',headers={'Content-Type':'application/json','X-Study-CSRF':token})) as r:job=json.load(r)
                        deadline=time.monotonic()+3
                        while time.monotonic()<deadline:
                            with urlopen(base+'/v1/comfy/jobs/'+job['prompt_id']) as r:status=json.load(r)
                            if status['status'] in comfy.TERMINAL:break
                            time.sleep(.01)
                        self.assertEqual(status['status'],'complete')
                        path=base+'/v1/comfy/jobs/'+job['prompt_id']+'/image?filename=mock.png'
                        with urlopen(path) as r:self.assertEqual(r.read(),png)
                        with self.assertRaises(HTTPError):urlopen(path.replace('mock.png','unowned.png'))
                        if self.browser_hook:self.browser_hook(base)
                finally:registry.close();stack.close()
        finally:
            for s in (app,fake):s.shutdown();s.server_close()
            for t in threads:t.join()

if __name__=='__main__': unittest.main()
