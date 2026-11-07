import os, tempfile, unittest
from unittest.mock import patch
import comfy_adapter as c

class RegistryTests(unittest.TestCase):
    def test_resource_configuration_must_be_finite_and_bounded(self):
        with tempfile.TemporaryDirectory() as d:
            for options in ({'timeout':float('inf')},{'timeout':0},{'workers':0},{'workers':5},{'capacity':0},{'capacity':65},{'poll':0}):
                with self.subTest(options=options):
                    with self.assertRaises(ValueError):c.JobRegistry(d+'/jobs.sqlite',start_workers=False,**options)

    def test_registry_exists(self):
        with tempfile.TemporaryDirectory() as d:
            registry=c.JobRegistry(d+'/jobs.sqlite', start_workers=False)
            with patch.dict(os.environ, {'STUDY_COMFYUI_CHECKPOINT':'test.safetensors'}):
                a=registry.submit('cup',request_id='request-1')
                self.assertEqual(a['status'],'queued')
                self.assertEqual(registry.submit('cup',request_id='request-1')['prompt_id'],a['prompt_id'])
                with self.assertRaises(ValueError):registry.submit('house',request_id='request-1')
                self.assertEqual(registry.cancel(a['prompt_id'])['status'],'cancelled')
            registry.close()

if __name__=='__main__':unittest.main()
import json, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

class FakeComfyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.mode='complete'; self.posts=0
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*a):pass
            def do_POST(self):
                owner.posts+=1
                owner.payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                self.send_response(200);self.end_headers()
                self.wfile.write(json.dumps({'prompt_id':'12345678-1234-1234-1234-123456789012'}).encode())
            def do_GET(self):
                self.send_response(200);self.end_headers()
                value={}
                if owner.mode=='complete':value={'12345678-1234-1234-1234-123456789012':{'outputs':{'7':{'images':[{'filename':'Study_1.png','type':'output'}]}}}}
                if owner.mode in ('error','oom','model'):
                    message={'error':'execution failed','oom':'CUDA out of memory','model':'checkpoint not found'}[owner.mode]
                    value={'12345678-1234-1234-1234-123456789012':{'status':{'status_str':'error','messages':[['execution_error',{'exception_message':message}]]}}}
                self.wfile.write(b'not json' if owner.mode=='broken' else json.dumps(value).encode())
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.env=patch.dict(os.environ,{'STUDY_COMFYUI_CHECKPOINT':'test.safetensors'});self.env.start()
        self.base=patch.object(c,'BASE','http://127.0.0.1:'+str(self.server.server_port));self.base.start()
        # Success tests allow Windows/Chromium scheduling; deadline test sets its own short budget.
        self.registry=c.JobRegistry(self.temp.name+'/jobs.sqlite',timeout=2,poll=.01)
    def tearDown(self):
        self.registry.close();self.server.shutdown();self.server.server_close();self.thread.join();self.base.stop();self.env.stop();self.temp.cleanup()
    def wait(self,job):
        end=time.monotonic()+3
        while time.monotonic()<end:
            result=self.registry.result(job['prompt_id'])
            if result['status'] in c.TERMINAL:return result
            time.sleep(.01)
        self.fail('worker did not settle')
    def test_complete_and_request_binding(self):
        result=self.wait(self.registry.submit('cup'))
        self.assertEqual(result['status'],'complete');self.assertEqual(result['images'][0]['filename'],'Study_1.png')
        self.assertEqual(result['state'],'completed')
        with self.assertRaises(KeyError):self.registry.result('12345678-1234-1234-1234-123456789012')
    def test_execution_failure(self):
        self.mode='error';self.assertEqual(self.wait(self.registry.submit('cup'))['status'],'failed')
    def test_parameters_reach_comfy_and_are_bound_to_request_id(self):
        job=self.registry.submit('cup',seed=42,width=768,height=512,steps=35,request_id='parameters')
        self.assertEqual(self.wait(job)['status'],'complete')
        self.assertEqual(self.payload['prompt']['4']['inputs'],{'width':768,'height':512,'batch_size':1})
        self.assertEqual(self.payload['prompt']['5']['inputs']['steps'],35)
        self.assertEqual(self.payload['prompt']['5']['inputs']['seed'],42)
        again=self.registry.submit('cup',seed=42,width=768,height=512,steps=35,request_id='parameters')
        self.assertEqual(again['job_id'],job['job_id'])
        self.assertEqual(self.posts,1)
        with self.assertRaises(ValueError):
            self.registry.submit('cup',seed=42,width=512,height=512,steps=35,request_id='parameters')
    def test_disabled_feature_does_not_replay_durable_queue_on_read(self):
        self.registry.close()
        self.registry=c.JobRegistry(self.temp.name+'/jobs.sqlite',start_workers=False)
        job=self.registry.submit('cup');self.registry.close()
        with patch.object(c,'_registry',None),patch.dict(os.environ,{
                'STUDY_COMFYUI_ENABLED':'0','STUDY_COMFYUI_DB':self.temp.name+'/jobs.sqlite'}):
            try:
                c.list_jobs();time.sleep(.1)
                self.assertEqual(self.posts,0)
                self.assertEqual(c.result(job['job_id'])['state'],'queued')
                self.registry=c._registry
            finally:
                if c._registry is not None:self.registry=c._registry
    def test_versioned_request_rejects_workflows_and_image_conditioning(self):
        request={'contract_version':1,'mode':'text_to_image','prompt':'cup',
                 'parameters':{'seed':3,'width':512,'height':768,'steps':5},'references':[]}
        with patch.object(c,'_registry',self.registry),patch.dict(os.environ,{'STUDY_COMFYUI_ENABLED':'1'}):
            job=c.consume_generation_request(request,request_id='composer-v1')
            self.assertEqual(self.wait(job)['status'],'complete')
            self.assertEqual(self.payload['prompt']['4']['inputs']['height'],768)
            for bad in (dict(request,mode='image_conditioned'),dict(request,references=['asset']),dict(request,workflow={}),dict(request,contract_version=True)):
                with self.subTest(bad=bad),self.assertRaises(ValueError):c.consume_generation_request(bad)
    def test_deadline(self):
        self.registry.timeout=.15
        self.mode='pending';job=self.wait(self.registry.submit('cup'))
        self.assertEqual(job['status'],'timed_out');self.assertEqual(job['state'],'failed')
    def test_actionable_diagnostics_for_oom_missing_model_and_corrupt_json(self):
        for mode,code in [('oom','out_of_vram'),('model','model_missing'),('broken','invalid_response')]:
            self.mode=mode
            job=self.wait(self.registry.submit('cup'))
            self.assertEqual(job['state'],'failed')
            self.assertEqual(job['error']['code'],code)
    def test_stopped_comfy_is_distinct_from_execution_error(self):
        import socket
        self.registry.timeout=2
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        with patch.object(c,'BASE','http://127.0.0.1:'+str(port)):
            job=self.wait(self.registry.submit('cup'))
        self.assertEqual(job['error']['code'],'comfyui_unavailable')
    def test_cancel_does_not_complete(self):
        self.mode='pending';job=self.registry.submit('cup');self.registry.cancel(job['prompt_id'])
        time.sleep(.05);self.assertEqual(self.registry.result(job['prompt_id'])['status'],'cancelled')
    def test_recovery(self):
        self.registry.close()
        self.registry=c.JobRegistry(self.temp.name+'/jobs.sqlite',start_workers=False)
        job=self.registry.submit('cup')
        self.registry.db.execute("UPDATE jobs SET state='running' WHERE id=?",(job['prompt_id'],));self.registry.db.commit();self.registry.close()
        self.registry=c.JobRegistry(self.temp.name+'/jobs.sqlite',start_workers=False)
        self.assertEqual(self.registry.result(job['prompt_id'])['status'],'interrupted')
    def test_capacity_and_validation(self):
        self.registry.close();self.registry=c.JobRegistry(self.temp.name+'/jobs.sqlite',capacity=1,start_workers=False)
        self.registry.submit('cup')
        with self.assertRaises(c.QueueFull):self.registry.submit('house')
        with self.assertRaises(ValueError):c.workflow('cup',seed=True)
        with self.assertRaises(ValueError):c._image_name('../secret.png','')
        with self.assertRaises(ValueError):c._image_name('ok.png','../outside')

class HttpContractTests(unittest.TestCase):
    def test_routes_and_unknown_job(self):
        import urllib.request, urllib.error
        import web_app
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ,{'STUDY_COMFYUI_ENABLED':'1','STUDY_COMFYUI_CHECKPOINT':'test.safetensors'}):
            registry=c.JobRegistry(d+'/jobs.sqlite',start_workers=False)
            with patch.object(c,'_registry',registry):
                server=ThreadingHTTPServer(('127.0.0.1',0),web_app.Handler)
                thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
                base='http://127.0.0.1:'+str(server.server_port)
                try:
                    token=json.load(urllib.request.urlopen(base+'/v1/security/bootstrap'))['csrf_token']
                    req=urllib.request.Request(base+'/v1/comfy/generate',data=b'{"prompt":"cup","request_id":"route-1"}',headers={'Content-Type':'application/json','X-Study-CSRF':token})
                    job=json.load(urllib.request.urlopen(req));self.assertEqual(job['status'],'queued')
                    self.assertEqual(json.load(urllib.request.urlopen(base+'/v1/comfy/jobs/'+job['prompt_id']))['request_id'],'route-1')
                    req=urllib.request.Request(base+'/v1/comfy/jobs/'+job['prompt_id']+'/cancel',data=b'{}',headers={'X-Study-CSRF':token})
                    self.assertEqual(json.load(urllib.request.urlopen(req))['status'],'cancelled')
                    with self.assertRaises(urllib.error.HTTPError) as caught:urllib.request.urlopen(base+'/v1/comfy/jobs/12345678-1234-1234-1234-123456789012')
                    self.assertEqual(caught.exception.code,404)
                    for extra in ('workflow','references','url'):
                        req=urllib.request.Request(base+'/v1/comfy/generate',data=json.dumps({'prompt':'cup',extra:{}}).encode(),headers={'X-Study-CSRF':token})
                        with self.assertRaises(urllib.error.HTTPError) as rejected:urllib.request.urlopen(req)
                        self.assertEqual(rejected.exception.code,400)
                    self.assertEqual(len(registry.list()),1)
                finally:server.shutdown();server.server_close();thread.join();registry.close()

    def test_png_validation(self):
        from io import BytesIO
        from PIL import Image
        output=BytesIO();Image.new('RGB',(2,2)).save(output,format='PNG')
        info={'status':'complete','images':[{'filename':'ok.png','subfolder':''}]}
        class Response:
            def __init__(self,data):self.data=data
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def read1(self,size):
                chunk=self.data[:size];self.data=self.data[size:];return chunk
        with patch.object(c,'result',return_value=info):
            with patch.object(c,'_open',return_value=Response(output.getvalue())):
                self.assertEqual(c.image_bytes('id','ok.png'),output.getvalue())
            with patch.object(c,'_open',return_value=Response(b'<html>bad</html>')):
                with self.assertRaises(ValueError):c.image_bytes('id','ok.png')
            import struct,zlib
            def chunk(kind,data):
                return struct.pack('!I',len(data))+kind+data+struct.pack('!I',zlib.crc32(kind+data))
            corrupt=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!IIBBBBB',2,2,8,2,0,0,0))+chunk(b'IDAT',b'not compressed pixels')+chunk(b'IEND',b'')
            with patch.object(c,'_open',return_value=Response(corrupt)):
                with self.assertRaises(ValueError):c.image_bytes('id','ok.png')
            with self.assertRaises(ValueError):c.image_bytes('id','other.png')

class RecoveryQueueTests(unittest.TestCase):
    def test_queued_job_survives_restart(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ,{'STUDY_COMFYUI_CHECKPOINT':'test.safetensors'}):
            registry=c.JobRegistry(d+'/jobs.sqlite',start_workers=False)
            job=registry.submit('cup');registry.close()
            registry=c.JobRegistry(d+'/jobs.sqlite',start_workers=False)
            try:self.assertEqual(registry.result(job['prompt_id'])['status'],'queued')
            finally:registry.close()

    def test_one_worker_keeps_second_job_queued(self):
        gate=threading.Event();entered=threading.Event()
        def request(path,payload=None,timeout=15):
            entered.set();gate.wait(1)
            return {'prompt_id':'12345678-1234-1234-1234-123456789012'}
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ,{'STUDY_COMFYUI_CHECKPOINT':'test.safetensors'}),patch.object(c,'_request',side_effect=request):
            registry=c.JobRegistry(d+'/jobs.sqlite',poll=.01)
            try:
                first=registry.submit('cup');self.assertTrue(entered.wait(1))
                second=registry.submit('house');self.assertEqual(registry.result(second['prompt_id'])['status'],'queued')
                registry.cancel(first['prompt_id']);registry.cancel(second['prompt_id'])
            finally:gate.set();registry.close()

class RedirectTests(unittest.TestCase):
    def test_slow_headers_cannot_extend_absolute_request_deadline(self):
        class SlowHeaders(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                try:
                    import socket
                    self.connection.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
                    self.connection.sendall(b'HTTP/1.1 200 OK\r\n')
                    for _ in range(20):
                        time.sleep(.05)
                        self.connection.sendall(b'X-Slow: yes\r\n')
                    self.connection.sendall(b'Content-Length: 2\r\n\r\n{}')
                except OSError:pass
        server=ThreadingHTTPServer(('127.0.0.1',0),SlowHeaders)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with patch.object(c,'BASE','http://127.0.0.1:'+str(server.server_port)):
                start=time.monotonic()
                with self.assertRaises(TimeoutError):c._request('/slow',timeout=.15)
                self.assertLess(time.monotonic()-start,.6)
        finally:server.shutdown();server.server_close();thread.join()

    def test_redirect_is_rejected(self):
        class Redirect(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                self.send_response(302);self.send_header('Location','http://example.com/escape');self.end_headers()
        server=ThreadingHTTPServer(('127.0.0.1',0),Redirect)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with self.assertRaisesRegex(ValueError,'redirects are forbidden'):
                c._open('http://127.0.0.1:'+str(server.server_port),timeout=1)
            with self.assertRaises(ValueError):c._open('http://example.com',timeout=1)
        finally:server.shutdown();server.server_close();thread.join()
