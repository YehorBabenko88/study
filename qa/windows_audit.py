"""Independent checks. Run only in the disposable copy made by acceptance.ps1."""
import argparse
import io
import hashlib
import http.client
import json
import os
import subprocess
import sys
import threading
import time
import unittest
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'prototype'))
URL = ''

def request(path, data=None, method='GET', headers=None, csrf=True, header_only=False):
    headers=dict(headers or {})
    if csrf and method in ('POST','PUT','DELETE'):
        status,raw=request('/v1/security/bootstrap')
        if status==200:headers.setdefault('X-Study-CSRF',json.loads(raw)['csrf_token'])
    if header_only:
        connection=http.client.HTTPConnection(URL.removeprefix('http://'),timeout=10)
        try:
            connection.putrequest(method,path,skip_host='Host' in headers)
            for key,value in headers.items():connection.putheader(key,value)
            connection.putheader('Content-Length',str(len(data or b'')));connection.endheaders()
            response=connection.getresponse();return response.status,response.read()
        finally:connection.close()
    req=urllib.request.Request(URL+path,data=data,method=method,headers=headers)
    try:
        with urllib.request.urlopen(req,timeout=10) as r:return r.status,r.read()
    except urllib.error.HTTPError as e:return e.code,e.read()

def pdf_worker(pid):
    import document_import as d
    while d.status(pid)['status'] != 'complete':
        result = d.process(pid, batch=5)
        if result['status'] == 'failed':
            raise RuntimeError(result)

class Acceptance(unittest.TestCase):
    def test_upload_limits(self):
        _,bootstrap=request('/v1/security/bootstrap')
        token=json.loads(bootstrap).get('csrf_token','')
        for method,path,limit in [('PUT','/v1/documents',100_000_000),('PUT','/v1/board-assets',8_000_000),('POST','/v1/boards',4_000_000)]:
            # Send only headers: the server must reject before reading an oversized body.
            conn=http.client.HTTPConnection(URL.removeprefix('http://'),timeout=5)
            try:
                conn.putrequest(method,path);conn.putheader('Content-Length',str(limit+1));conn.putheader('X-Study-CSRF',token);conn.endheaders()
                self.assertEqual(conn.getresponse().status,413)
            finally:conn.close()
        self.assertEqual(request('/v1/board-assets',b'invalid','PUT')[0],400)

    def test_api_rejects_foreign_origin_mutation(self):
        # No credentials or existing user data: create an audit-only empty board.
        for extra in ({'Origin':'https://attacker.invalid'},{'Host':'attacker.invalid'}):
            with self.subTest(headers=extra):
                status,body=request('/v1/boards',b'{"nodes":[],"edges":[],"title":"Origin audit"}', 'POST',
                    {**extra,'Content-Type':'text/plain'},header_only=True)
                print('FOREIGN_ORIGIN_OR_HOST',extra,status,body,flush=True)
                self.assertIn(status,(400,403),'Untrusted Origin/Host accepted a state-changing request')

    def test_api_mutation_security_matrix(self):
        body=b'{"nodes":[],"edges":[],"title":"security matrix"}'
        # Unknown future endpoints must be gated before routing as well.
        for method,path,payload in [('POST','/v1/boards',body),('PUT','/v1/board-assets',b'png'),('DELETE','/v1/mnemonics/00000000-0000-4000-8000-000000000001',None),('POST','/v1/future-generation',b'{}')]:
            for headers in ({},{'Origin':URL},{'X-Study-CSRF':'forged'},{'Origin':'null'},{'Origin':'https://attacker.invalid'}):
                with self.subTest(method=method,headers=headers):
                    self.assertIn(request(path,payload,method,headers,csrf=False,header_only=True)[0],(400,403))
        for host in ('attacker.invalid','127.0.0.1.attacker.invalid','127.0.0.1:1','user@127.0.0.1','127.0.0.1'):
            with self.subTest(host=host):
                self.assertIn(request('/v1/security/bootstrap',headers={'Host':host})[0],(400,403))
        for origin in ('null','http://127.0.0.1:1','https://attacker.invalid'):
            with self.subTest(origin=origin):
                self.assertIn(request('/v1/boards',body,'POST',{'Origin':origin},header_only=True)[0],(400,403))
        # Valid token is necessary even for same-origin; valid native client may omit Origin.
        self.assertEqual(request('/v1/boards',body,'POST')[0],200)
        self.assertEqual(request('/v1/boards',body,'POST',{'Origin':URL})[0],200)

    def test_mock_comfy_http_roundtrip(self):
        import comfy_adapter as c
        from PIL import Image
        buf=io.BytesIO();Image.new('RGB',(32,32),'green').save(buf,'PNG');png=buf.getvalue()
        pid='00000000-0000-4000-8000-000000000099'
        class Mock(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                assert payload['prompt']['7']['class_type']=='SaveImage'
                self.reply(json.dumps({'prompt_id':pid}).encode())
            def do_GET(self):
                self.reply(png if self.path.startswith('/view?') else json.dumps({pid:{'outputs':{'7':{'images':[{'filename':'qa.png','subfolder':'','type':'output'}]}}}}).encode())
            def reply(self,data):
                self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        mock=ThreadingHTTPServer(('127.0.0.1',0),Mock)
        threading.Thread(target=mock.serve_forever,daemon=True).start()
        try:
            with patch.object(c,'BASE',f'http://127.0.0.1:{mock.server_port}'),patch.dict(os.environ,{'STUDY_COMFYUI_ENABLED':'1','STUDY_COMFYUI_CHECKPOINT':'qa.safetensors'}):
                code,body=request('/v1/comfy/generate',b'{"prompt":"QA cup"}','POST')
                self.assertEqual(code,200);local_id=json.loads(body)['prompt_id']
                deadline=time.monotonic()+10
                while time.monotonic()<deadline:
                    state=json.loads(request('/v1/comfy/jobs/'+local_id)[1])
                    if state['status']=='complete':break
                    time.sleep(.05)
                self.assertEqual(state['status'],'complete')
                self.assertEqual(request('/v1/comfy/jobs/'+local_id+'/image?filename=qa.png')[1],png)
                from playwright.sync_api import sync_playwright
                with sync_playwright() as play:
                    browser=play.chromium.launch(headless=True)
                    try:
                        page=browser.new_page(viewport={'width':1440,'height':900})
                        page.on('dialog',lambda dialog:dialog.accept())
                        page.goto(URL+'/canvas')
                        page.locator('.node.word').first.wait_for()
                        page.locator('.node.word').first.click()
                        before=page.locator('.node').count()
                        page.locator('#generateComposite').click()
                        page.wait_for_function('nodes.some(n=>n.text.startsWith("Сгенерированный образ:"))',timeout=20000)
                        self.assertEqual(page.locator('.node').count(),before+1)
                        self.assertTrue(page.evaluate('edges.some(e=>nodes.find(n=>n.id===e.to)?.text.startsWith("Сгенерированный образ:"))'))
                        image=page.locator('.node.image img').last
                        image.wait_for()
                        self.assertTrue(image.evaluate('(im)=>im.complete && im.naturalWidth>0'))
                        page.screenshot(path=str(ROOT/'mock-comfy.png'))
                    finally:browser.close()
        finally:
            if getattr(c,'_registry',None) is not None:
                c._registry.close();c._registry=None
            mock.shutdown();mock.server_close()

    def test_pdf_150_process_restart(self):
        import fitz
        import document_import as d
        pdf = fitz.open()
        for i in range(150):
            p = pdf.new_page()
            if i!=75:p.insert_text((72,72), f'Independent acceptance page {i:03d} with recoverable text.')
        raw = pdf.tobytes()
        pdf.close()
        status,body=request('/v1/documents',raw,'PUT',{'X-Document-Name':'acceptance150.pdf'})
        self.assertEqual(status,200)
        job=json.loads(body)
        child = subprocess.Popen([sys.executable, __file__, '--pdf-worker', job['id']])
        deadline = time.monotonic()+30
        while time.monotonic()<deadline:
            state = d.status(job['id'])
            if state['next_page'] >= 5 or child.poll() is not None:
                break
            time.sleep(.005)
        child.kill() if child.poll() is None else None
        child.wait()
        state = d.status(job['id'])
        print('INTERRUPTED_PDF', json.dumps(state), flush=True)
        self.assertGreater(state['next_page'], 0)
        self.assertLess(state['next_page'], 150, 'No interrupted job was observed')
        import psutil
        child=subprocess.Popen([sys.executable, __file__, '--pdf-worker', job['id']])
        peak=0;latencies=[];deadline=time.monotonic()+60
        try:
            while child.poll() is None:
                if time.monotonic()>deadline:raise TimeoutError('PDF resume timed out')
                try:
                    worker=psutil.Process(child.pid)
                    peak=max(peak,sum(proc.memory_info().rss for proc in [worker,*worker.children(recursive=True)] if proc.is_running()))
                except psutil.NoSuchProcess:pass
                start=time.monotonic();self.assertEqual(request('/workspace')[0],200);latencies.append((time.monotonic()-start)*1000)
                time.sleep(.02)
            self.assertEqual(child.returncode,0)
        finally:
            if child.poll() is None:child.kill();child.wait()
        print('PDF_METRICS',json.dumps({'worker_tree_peak_sampled_rss':peak,'workspace_http_ms':latencies}),flush=True)
        self.assertEqual(d.status(job['id'])['next_page'],150)
        for i in range(150):
            if i!=75:self.assertIn(f'page {i:03d}',d.page(job['id'],i)['text'])
        preserved={i:d.page(job['id'],i) for i in range(150) if i!=75}
        import pytesseract
        retry_body=b'{"batch":5,"ocr":true,"retry":true}'
        with patch.object(pytesseract,'image_to_string',side_effect=pytesseract.TesseractError(1,'deu missing')):
            status,body=request('/v1/documents/'+job['id']+'/process',retry_body,'POST')
        self.assertEqual(status,200);self.assertEqual(json.loads(body)['status'],'ocr_error')
        self.assertEqual(json.loads(body)['next_page'],75)
        with patch.object(pytesseract,'image_to_string',return_value='Recovered page 075'):
            status,body=request('/v1/documents/'+job['id']+'/process',retry_body,'POST')
        self.assertEqual(status,200);self.assertEqual(json.loads(body)['status'],'complete')
        self.assertEqual(d.page(job['id'],75)['text'],'Recovered page 075')
        self.assertEqual((d.ROOT/(job['id']+'.pdf')).read_bytes(),raw)
        self.assertEqual({i:d.page(job['id'],i) for i in preserved},preserved)
        with d._db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM document_pages WHERE document_id=?',(job['id'],)).fetchone()[0],150)

    def test_ocr_missing_language(self):
        import board_assets as b
        import pytesseract
        from PIL import Image
        buf=io.BytesIO(); Image.new('RGB',(50,50),'white').save(buf,'PNG')
        with patch.object(pytesseract,'image_to_string',side_effect=pytesseract.TesseractError(1,'deu.traineddata missing')):
            result=b.recognize(buf.getvalue(),'deu')
        self.assertEqual(result['status'],'unavailable')
        self.assertEqual(result['reason'],'tesseract_or_language_data_missing')
        print('ACTUAL_OCR', b.recognize(buf.getvalue(),'deu'),flush=True)

    def test_pdf_ocr_missing_language_remains_retryable(self):
        import fitz
        import document_import as d
        import pytesseract
        pdf=fitz.open();pdf.new_page();raw=pdf.tobytes();pdf.close()
        job=d.create(raw,'missing-language.pdf')
        with patch.object(pytesseract,'image_to_string',side_effect=pytesseract.TesseractError(1,'deu missing')):
            state=d.process(job['id'],ocr=True)
        print('PDF_OCR_MISSING',json.dumps({'state':state,'page':d.page(job['id'],0)}),flush=True)
        self.assertNotEqual(state['status'],'complete','Missing OCR marked blank page complete; normal resume cannot retry it')

    def test_pdf_retry_button_live_server(self):
        import pymupdf
        import pytesseract
        import document_import as d
        from playwright.sync_api import sync_playwright
        pdf=pymupdf.open();pdf.new_page();raw=pdf.tobytes();pdf.close()
        code,body=request('/v1/documents',raw,'PUT',{'X-Document-Name':'browser-retry.pdf'})
        self.assertEqual(code,200);pid=json.loads(body)['id']
        with patch.object(pytesseract,'image_to_string',side_effect=pytesseract.TesseractNotFoundError()):
            code,body=request('/v1/documents/'+pid+'/process',b'{"batch":1,"ocr":true}','POST')
        self.assertEqual(json.loads(body)['status'],'ocr_error')
        with sync_playwright() as play:
            browser=play.chromium.launch()
            try:
                page=browser.new_page();page.goto(URL+'/canvas?document='+pid)
                page.wait_for_function('(id)=>document.getElementById("documentList").value===id',arg=pid)
                with patch.object(pytesseract,'image_to_string',return_value='Recovered via real browser retry'):
                    page.locator('#pdfRetry').click()
                    page.wait_for_function('document.getElementById("pdfStatus").textContent.includes("обработка завершена")')
                self.assertEqual(d.page(pid,0)['text'],'Recovered via real browser retry')
                self.assertEqual(d.status(pid)['status'],'complete')
                self.assertEqual((d.ROOT/(pid+'.pdf')).read_bytes(),raw)
                page.screenshot(path=str(ROOT/'pdf-retry-live.png'))
            finally:browser.close()

    def test_gallery_bytes_persist_across_process(self):
        import board_assets as b
        import spatial_board as s
        from PIL import Image
        ids=[]; originals=[]
        for color in ('red','blue'):
            buf=io.BytesIO();Image.new('RGB',(40,40),color).save(buf,'PNG')
            asset=b.store(buf.getvalue())['asset_id'];ids.append(asset);originals.append(b.read(asset))
        doc={'nodes':[{'id':'qa-word','type':'word','text':'Tasse','x':0,'y':0,'image_assets':ids}],'edges':[]}
        saved=s.save(doc,title='Independent gallery audit')
        output=subprocess.check_output([sys.executable,'-c',
            'import sys,json,hashlib;sys.path.insert(0,"prototype");import spatial_board,board_assets;doc=spatial_board.load(sys.argv[1]);print(json.dumps({"doc":doc,"hashes":[hashlib.sha256(board_assets.read(x)).hexdigest() for x in doc["nodes"][0]["image_assets"]]}))',saved['id']],cwd=ROOT,text=True)
        self.assertEqual(json.loads(output)['doc']['nodes'],doc['nodes'])
        self.assertEqual(json.loads(output)['hashes'],[hashlib.sha256(x).hexdigest() for x in originals])
        from playwright.sync_api import sync_playwright
        with sync_playwright() as play:
            browser=play.chromium.launch(headless=True)
            try:
                page=browser.new_page();page.goto(URL+'/canvas')
                page.get_by_role('button',name='Independent gallery audit',exact=True).click()
                page.wait_for_function('document.querySelectorAll(".image-gallery img").length===2 && [...document.querySelectorAll(".image-gallery img")].every(im=>im.complete && im.naturalWidth>0)')
                page.screenshot(path=str(ROOT/'gallery-reopened.png'))
            finally:browser.close()

    def test_sqlite_windows_rename_after_use(self):
        import visual_memory as v
        with v.connection() as db: db.execute('SELECT 1')
        target=v.DB.with_suffix('.rename-check')
        v.DB.rename(target);target.rename(v.DB)

    def test_ui_500_cards_measurement(self):
        import psutil
        from playwright.sync_api import sync_playwright
        with sync_playwright() as play:
            browser=play.chromium.launch(headless=True)
            try:
                page=browser.new_page(viewport={'width':1440,'height':900})
                page.goto(URL+'/canvas');page.locator('.node.word').first.wait_for()
                baseline=sum(p.memory_info().rss for p in psutil.Process().children(recursive=True) if p.is_running())
                measurements=[]
                for i in range(3):
                    measurements.append(page.evaluate('''() => {const t=performance.now();nodes=Array.from({length:500},(_,i)=>({id:'perf'+i,type:'word',text:'Tasse '+i,x:(i%20)*210,y:Math.floor(i/20)*130}));edges=[];draw();return performance.now()-t}'''))
                    page.wait_for_timeout(100)
                rss=sum(p.memory_info().rss for p in psutil.Process().children(recursive=True) if p.is_running())
                print('UI_METRICS',json.dumps({'draw_500_ms':measurements,'child_rss_before':baseline,'child_rss_after':rss,'dom_cards':page.locator('.node').count()}),flush=True)
                self.assertEqual(page.evaluate('nodes.length'),500)
                self.assertGreater(page.locator('.node').count(),0)
                page.screenshot(path=str(ROOT/'ui-500-cards.png'))
            finally:browser.close()

    def test_pointer_fling_workspace(self):
        from playwright.sync_api import sync_playwright
        with sync_playwright() as play:
            browser=play.chromium.launch(headless=True)
            try:
                page=browser.new_page(viewport={'width':1440,'height':900})
                page.goto(URL+'/workspace')
                canvas=page.frame_locator('iframe[src="/canvas"]')
                canvas.locator('.node.word').first.wait_for()
                node=canvas.locator('.node.word').first
                frame=page.frames[1]
                for candidate in page.frames:
                    if candidate.url.endswith('/canvas'):frame=candidate
                original=frame.evaluate('edges.length')
                self.assertGreater(original,0)
                box=node.bounding_box();x=box['x']+45;y=box['y']+45
                # Move the left-hand word away from its right-hand syllable neighbors.
                page.mouse.move(x,y);page.mouse.down()
                page.locator('.drag-hint').wait_for(timeout=3000)
                page.mouse.move(x,y+200,steps=2);page.mouse.up()
                page.wait_for_timeout(200)
                print('POINTER_FLING',json.dumps({'before':original,'after':frame.evaluate('edges.length')}),flush=True)
                self.assertEqual(frame.evaluate('edges.length'),0)
                page.screenshot(path=str(ROOT/'pointer-fling.png'))
            finally:browser.close()

def main():
    global URL
    p=argparse.ArgumentParser();p.add_argument('--pdf-worker');p.add_argument('--browser',action='store_true');a=p.parse_args()
    if a.pdf_worker:
        pdf_worker(a.pdf_worker);return
    import web_app
    server=ThreadingHTTPServer(('127.0.0.1',0),web_app.Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    url=f'http://127.0.0.1:{server.server_port}';URL=url
    os.environ['STUDY_E2E_URL']=url
    try:
        suite=unittest.defaultTestLoader.loadTestsFromTestCase(Acceptance)
        if a.browser:
            import importlib
            for file in sorted((ROOT/'prototype').glob('test*.py')):
                if 'playwright' in file.read_text(encoding='utf-8'):
                    suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(importlib.import_module(file.stem)))
        result=unittest.TextTestRunner(verbosity=2).run(suite)
        sys.exit(not result.wasSuccessful() or bool(result.skipped))
    finally:
        server.shutdown();server.server_close()

if __name__=='__main__':main()
