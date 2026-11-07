"""Independent adapter safety regressions; no models or real Comfy service."""
import io,json,os,socket,struct,tempfile,threading,time,unittest,zlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from unittest.mock import patch
import comfy_adapter as c

class AdapterSafetyTests(unittest.TestCase):
    def test_disabled_restart_does_not_submit_persisted_queue(self):
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'STUDY_COMFYUI_CHECKPOINT':'test.safetensors','STUDY_COMFYUI_ENABLED':'0','STUDY_COMFYUI_DB':folder+'/jobs.sqlite'}):
            registry=c.JobRegistry(folder+'/jobs.sqlite',start_workers=False)
            job=registry.submit('cup');registry.close()
            with patch.object(c,'_registry',None),patch.object(c,'_request',return_value={}) as request:
                resumed=c.registry()
                try:
                    time.sleep(.1)
                    request.assert_not_called()
                    self.assertEqual(resumed.result(job['prompt_id'])['status'],'queued')
                finally:resumed.close()

    def test_verify_only_png_is_not_accepted_without_raster_decode(self):
        def chunk(kind,data):return struct.pack('!I',len(data))+kind+data+struct.pack('!I',zlib.crc32(kind+data)&0xffffffff)
        raw=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!IIBBBBB',1,1,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b''))+chunk(b'IEND',b'')
        from PIL import Image
        with Image.open(io.BytesIO(raw)) as image:image.verify()
        class Response(io.BytesIO):
            def read1(self,size):return self.read(size)
        info={'status':'complete','images':[{'filename':'bad.png','subfolder':''}]}
        with patch.object(c,'result',return_value=info),patch.object(c,'_open',return_value=Response(raw)):
            with self.assertRaises(ValueError):c.image_bytes('local-id','bad.png')

    def test_absolute_deadline_includes_dripping_response_headers(self):
        class Drip(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                try:
                    self.connection.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
                    self.wfile.write(b'HTTP/1.0 200 OK\r\n');self.wfile.flush()
                    for _ in range(40):
                        self.wfile.write(b'X-Drip: x\r\n');self.wfile.flush();time.sleep(.03)
                    self.wfile.write(b'Content-Length: 2\r\n\r\n{}');self.wfile.flush()
                except OSError:pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Drip)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        started=time.monotonic()
        try:
            with patch.object(c,'BASE','http://127.0.0.1:'+str(server.server_port)):
                with self.assertRaises(TimeoutError):c._request('/history',timeout=.5)
            self.assertLess(time.monotonic()-started,.9)
        finally:server.shutdown();server.server_close();thread.join()

    def test_invalid_config_and_explicit_empty_request_id(self):
        with tempfile.TemporaryDirectory() as folder:
            for params in ({'workers':0},{'capacity':0},{'timeout':float('nan')},{'poll':float('inf')},{'timeout':True},{'poll':True}):
                with self.subTest(params=params):
                    candidate=None
                    try:
                        with self.assertRaises(ValueError):candidate=c.JobRegistry(folder+'/jobs.sqlite',start_workers=False,**params)
                    finally:
                        if candidate is not None:candidate.close()
            registry=c.JobRegistry(folder+'/jobs.sqlite',start_workers=False)
            try:
                with patch.dict(os.environ,{'STUDY_COMFYUI_CHECKPOINT':'test.safetensors'}):
                    with self.assertRaises(ValueError):registry.submit('cup',request_id='')
            finally:registry.close()

    def test_deadline_connection_aborts_the_actual_socket(self):
        listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(1)
        connection=c._DeadlineConnection('127.0.0.1',listener.getsockname()[1],timeout=.12)
        try:
            connection.connect();connection.sock.settimeout(1);peer,_=listener.accept()
            try:
                started=time.monotonic()
                try:self.assertEqual(connection.sock.recv(1),b'')
                except OSError as exc:self.assertNotIsInstance(exc,TimeoutError)
                self.assertLess(time.monotonic()-started,.6)
            finally:peer.close()
        finally:connection.close();listener.close()
    def test_deadline_invalidates_buffered_http_response_socket(self):
        release=threading.Event()
        class WaitingBody(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                self.send_response(200);self.send_header('Content-Length','1');self.end_headers()
                release.wait(2)
        server=ThreadingHTTPServer(('127.0.0.1',0),WaitingBody)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with c._open('http://127.0.0.1:'+str(server.server_port),timeout=.12) as response:
                self.assertTrue(hasattr(response,'_study_deadline'))
                time.sleep(.2)
                started=time.monotonic()
                with self.assertRaises(OSError) as caught:response.read1(1)
                self.assertNotIsInstance(caught.exception,TimeoutError)
                self.assertLess(time.monotonic()-started,.1)
        finally:release.set();server.shutdown();server.server_close();thread.join()
