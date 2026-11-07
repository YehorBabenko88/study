"""Independent retention over actual HTTP and Chromium, including process restart.

All state lives under the test-owned TemporaryDirectory. No model is started.
The optional Comfy server below is an explicit deterministic fake, not inference.
"""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from urllib.request import Request, urlopen
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

REPO = Path(__file__).resolve().parents[1]
CHILD = r'''
import os,sys
from pathlib import Path
root=Path(sys.argv[1]); data=Path(sys.argv[2]); port=int(sys.argv[3])
sys.path.insert(0,str(root/'prototype'))
os.environ['STUDY_COMFYUI_DB']=str(data/'queue.sqlite')
os.environ['STUDY_COMPOSITIONS_DB']=str(data/'compositions.sqlite')
import web_app,comfy_adapter
if os.getenv('STUDY_TEST_COMFY_BASE'):comfy_adapter.BASE=os.environ['STUDY_TEST_COMFY_BASE']
for module in tuple(sys.modules.values()):
 source=getattr(module,'__file__',None)
 if not source or not Path(source).resolve().is_relative_to(root/'prototype'):continue
 if hasattr(module,'DB'):module.DB=data/('lexicon.sqlite' if module.__name__=='lexicon_store' else 'study.sqlite')
 for key in ('ROOT','MEDIA','AUDIO_DIR'):
  if hasattr(module,key):
   target=data/(module.__name__+'-'+key);target.mkdir(exist_ok=True);setattr(module,key,target)
from http.server import ThreadingHTTPServer
with ThreadingHTTPServer(('127.0.0.1',port),web_app.Handler) as server:server.serve_forever()
'''

class RestartableStudy:
    def __init__(self, root, fake_base=None):
        self.root=Path(root)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));self.port=sock.getsockname()[1]
        self.base=f'http://127.0.0.1:{self.port}'
        self.fake_base=fake_base;self.process=None;self.log=None
        try:self.start()
        except BaseException:
            self.stop();raise

    def start(self):
        env=dict(os.environ,STUDY_COMFYUI_ENABLED='1' if self.fake_base else '0',STUDY_COMFYUI_CHECKPOINT='fake-reviewed.safetensors',STUDY_COMFYUI_TIMEOUT='5')
        if self.fake_base:env['STUDY_TEST_COMFY_BASE']=self.fake_base
        self.log=(self.root/'server.log').open('ab')
        self.process=subprocess.Popen([sys.executable,'-u','-c',CHILD,str(REPO),str(self.root),str(self.port)],env=env,stdout=self.log,stderr=self.log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            if self.process.poll() is not None:raise RuntimeError((self.root/'server.log').read_text(errors='replace'))
            try:
                self.token=self.request('/v1/security/bootstrap')['csrf_token'];return
            except OSError:time.sleep(.05)
        raise RuntimeError('Disposable Study server failed startup')

    def stop(self):
        if self.process is not None:
            self.process.terminate()
            try:self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=5)
            self.process=None
        if self.log:self.log.close();self.log=None

    def restart(self):
        self.stop();self.start()

    def request(self,path,method='GET',data=None,raw=False,headers=None):
        extra=dict(headers or {})
        if data is not None and not isinstance(data,bytes):
            data=json.dumps(data).encode();extra['Content-Type']='application/json'
        if method not in ('GET','HEAD'):extra['X-Study-CSRF']=self.token
        with urlopen(Request(self.base+path,data=data,method=method,headers=extra),timeout=10) as response:
            body=response.read()
        return body if raw else json.loads(body)


@unittest.skipUnless(sync_playwright and os.getenv('STUDY_E2E_URL'),'Requires explicit Chromium acceptance')
class FinalRetentionBrowser(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='study-final-retention-')
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)

    @staticmethod
    def png(color):
        from PIL import Image
        output=io.BytesIO();Image.new('RGB',(7,5),color).save(output,format='PNG');return output.getvalue()

    def test_saved_board_pdf_audio_gallery_reopen_after_process_interruption(self):
        import pymupdf
        server=RestartableStudy(self.root);self.addCleanup(server.stop)
        assets=[]
        for color in ('red','blue'):
            data=self.png(color)
            saved=server.request('/v1/board-assets','PUT',data,headers={'Content-Type':'image/png'})
            assets.append((saved['asset_id'],hashlib.sha256(server.request('/v1/board-assets/'+saved['asset_id'],raw=True)).hexdigest()))
        with pymupdf.open() as pdf:
            for i in range(3):pdf.new_page().insert_text((72,72),f'Retention PDF page {i+1} complete sentence for text extraction.')
            original_pdf=pdf.tobytes()
        doc=server.request('/v1/documents','PUT',original_pdf,headers={'X-Document-Name':'retention-book.pdf'})
        pid=doc['id'];progress=server.request(f'/v1/documents/{pid}/process','POST',{'batch':1})
        self.assertEqual(progress['next_page'],1)
        project=server.request('/v1/speech-projects','POST',{'title':'Retained audio project','lang':'de','transcript':'Die rote Tasse.','segments':[{'label':'Tasse','t':.5}]})
        audio=io.BytesIO()
        with wave.open(audio,'wb') as wav:
            wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(8000);wav.writeframes(b'\x00\x00'*800)
        wav_bytes=audio.getvalue();sid=project['id']
        server.request(f'/v1/speech-projects/{sid}/audio','PUT',wav_bytes,headers={'Content-Type':'audio/wav'})
        nodes=[{'id':'word','type':'word','text':'Retained word','x':34,'y':91,'image_assets':[a[0] for a in assets]},
               {'id':'image','type':'image','text':'Original retained image','x':330,'y':91,'asset_id':assets[0][0]}]
        edges=[{'from':'word','to':'image','relation':'association'}]
        board=server.request('/v1/boards','POST',{'title':'Independent durable board','nodes':nodes,'edges':edges})
        with sync_playwright() as play:
            browser=play.chromium.launch()
            try:
                first=browser.new_context();page=first.new_page();page.goto(server.base+'/canvas',wait_until='networkidle')
                page.locator('#boards button',has_text=board['title']).click()
                page.wait_for_function("nodes.length===2 && nodes[0].id==='word'")
                self.assertEqual(page.evaluate('nodes[0].image_assets'),[a[0] for a in assets])
                first.close()
                # Abrupt process termination is intentional; all writes above were acknowledged.
                server.restart()
                reopened=browser.new_context();page=reopened.new_page();page.goto(server.base+'/canvas',wait_until='networkidle')
                page.wait_for_function('draftReady')
                page.locator('#boards button',has_text=board['title']).click()
                page.wait_for_function("nodes.length===2 && nodes[0].id==='word'")
                self.assertEqual(page.evaluate('({nodes,edges})'),{'nodes':nodes,'edges':edges})
                page.wait_for_function("[...document.querySelectorAll('.node img')].length===3 && [...document.querySelectorAll('.node img')].every(i=>i.complete&&i.naturalWidth>0)")
                self.assertEqual(server.request('/v1/boards/'+board['id'])['nodes'],nodes)
                for aid,digest in assets:self.assertEqual(hashlib.sha256(server.request('/v1/board-assets/'+aid,raw=True)).hexdigest(),digest)
                self.assertEqual(server.request(f'/v1/documents/{pid}')['next_page'],1)
                self.assertEqual((self.root/'document_import-ROOT'/(pid+'.pdf')).read_bytes(),original_pdf)
                resumed=server.request(f'/v1/documents/{pid}/process','POST',{'batch':2})
                self.assertEqual((resumed['status'],resumed['next_page']),('complete',3))
                self.assertIn('page 3',server.request(f'/v1/documents/{pid}/pages/2')['text'])
                page.locator('#documentList').select_option(pid);page.locator('#pageNumber').fill('3');page.locator('#pdfPage').click()
                page.wait_for_function("nodes.some(n=>n.text.includes('Retention PDF page 3'))")
                page.locator('#speechList').select_option(sid);page.locator('#loadSpeech').click()
                page.wait_for_function("document.querySelector('#paste').value==='Die rote Tasse.'")
                self.assertTrue(page.locator('#speechAudio').get_attribute('src').endswith('/'+sid+'/audio'))
                page.wait_for_function("document.querySelector('#speechAudio').readyState>=1")
                self.assertAlmostEqual(page.locator('#speechAudio').evaluate('audio=>audio.duration'),.1,places=3)
                self.assertIsNone(page.locator('#speechAudio').evaluate('audio=>audio.error'))
                self.assertEqual(server.request(f'/v1/speech-projects/{sid}/audio',raw=True),wav_bytes)
                self.assertEqual(server.request('/v1/boards/'+board['id'])['nodes'],nodes,'PDF insertion must not silently overwrite saved original board')
                reopened.close()
            finally:browser.close()

    def test_mocked_composition_interruption_and_completed_history_survive_restart(self):
        png=self.png('green');remote=str(uuid4());complete=threading.Event();counts={'posts':0,'images':0}
        class FakeComfy(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def send(self,value):
                raw=value if isinstance(value,bytes) else json.dumps(value).encode()
                self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
            def do_POST(self):
                payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                assert payload['prompt']['5']['inputs']['seed']==23
                counts['posts']+=1;self.send({'prompt_id':remote})
            def do_GET(self):
                if self.path.startswith('/view?'):
                    counts['images']+=1;return self.send(png)
                if not complete.is_set():return self.send({})
                self.send({remote:{'status':{'completed':True},'outputs':{'7':{'images':[{'filename':'retained.png','subfolder':'','type':'output'}]}}}})
        fake=ThreadingHTTPServer(('127.0.0.1',0),FakeComfy)
        thread=threading.Thread(target=fake.serve_forever,daemon=True);thread.start()
        def stop_fake():fake.shutdown();fake.server_close();thread.join()
        self.addCleanup(stop_fake)
        server=RestartableStudy(self.root,f'http://127.0.0.1:{fake.server_port}');self.addCleanup(server.stop)
        graph={'nodes':[{'id':'root','type':'word','text':'Retained cup'},{'id':'child','type':'word','text':'table'}],
               'edges':[{'from':'root','to':'child','relation':'association'}]}
        revision=server.request('/v1/compositions','POST',{'graph':graph,'roots':['root']})
        reviewed=server.request('/v1/compositions/revisions/'+revision['revision_id'],'POST',{'user_prompt':'My retained reviewed cup beside table','parameters':{'seed':23,'width':512,'height':768,'steps':14}})
        rid=reviewed['revision_id'];cid=reviewed['composition_id']
        first=server.request(f'/v1/compositions/revisions/{rid}/generate','POST',{'request_id':'retention-interrupted'})
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            pending=server.request('/v1/compositions/jobs/'+first['job_id'])
            if pending['status']=='running' and counts['posts']==1:break
            time.sleep(.05)
        self.assertEqual(pending['status'],'running')
        server.restart()
        interrupted=server.request('/v1/compositions/jobs/'+first['job_id'])
        self.assertEqual(interrupted['status'],'interrupted')
        self.assertEqual(interrupted['result']['outputs'],[])
        repeat=server.request(f'/v1/compositions/revisions/{rid}/generate','POST',{'request_id':'retention-interrupted'})
        self.assertEqual(repeat['job_id'],first['job_id']);self.assertEqual(counts['posts'],1)
        complete.set()
        second=server.request(f'/v1/compositions/revisions/{rid}/generate','POST',{'request_id':'retention-complete'})
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            result=server.request('/v1/compositions/jobs/'+second['job_id'])
            if result['status'] in ('complete','failed','interrupted','timed_out'):break
            time.sleep(.05)
        self.assertEqual(result['status'],'complete')
        output=result['result']['outputs'][0]
        stored=server.request('/v1/board-assets/'+output['asset_id'],raw=True)
        self.assertEqual(hashlib.sha256(stored).hexdigest(),output['sha256'])
        self.assertEqual(counts,{'posts':2,'images':1})
        server.restart()
        history=server.request('/v1/compositions/'+cid)['items']
        latest=next(item for item in history if item['revision_id']==rid)
        self.assertEqual(latest['user_prompt'],reviewed['user_prompt'])
        self.assertEqual(latest['parameters'],reviewed['parameters'])
        retained=server.request('/v1/compositions/jobs/'+second['job_id'])
        self.assertEqual(retained['result'],result['result'])
        self.assertEqual(server.request('/v1/board-assets/'+output['asset_id'],raw=True),stored)
        self.assertEqual(counts,{'posts':2,'images':1},'Reopen must not regenerate or redownload completed output')
        self.assertEqual(len(list((self.root/'board_assets-ROOT').glob('*.png'))),1)
        with sync_playwright() as play:
            browser=play.chromium.launch()
            try:
                page=browser.new_page();page.goto(server.base+'/canvas',wait_until='networkidle')
                page.wait_for_function('draftReady')
                before=page.evaluate('JSON.stringify({nodes,edges})')
                original_count=page.evaluate('nodes.length')
                page.locator('#compositionHistory').select_option(cid)
                page.wait_for_function("document.querySelector('#compositionPrompt').value==='My retained reviewed cup beside table'")
                self.assertEqual(page.locator('#compositionSeed').input_value(),'23')
                self.assertEqual(page.locator('#compositionHeight').input_value(),'768')
                page.locator('#compositionResult img').wait_for()
                self.assertEqual(page.locator('#compositionResult img').get_attribute('src'),'/v1/board-assets/'+output['asset_id'])
                self.assertEqual(page.evaluate('JSON.stringify({nodes,edges})'),before,'Browsing completed history must not mutate an unrelated board')
                page.locator('#attachCompositionResult').click()
                page.wait_for_function('(count)=>nodes.length===count+1',arg=original_count)
                self.assertEqual(page.evaluate('(prior)=>JSON.stringify({nodes:nodes.slice(0,-1),edges:edges.slice(0,JSON.parse(prior).edges.length)})',before),before)
                self.assertEqual(page.evaluate('nodes.at(-1).image_assets'),[output['asset_id']])
                self.assertEqual(counts,{'posts':2,'images':1})
            finally:browser.close()
