import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pymupdf
import sys
import types
pytesseract=types.SimpleNamespace(image_to_string=lambda *a, **k: "", TesseractError=RuntimeError)
import document_import as d


class PDFOCRRetryTests(unittest.TestCase):
    def setUp(self):
        self.ocrmodule=patch.dict(sys.modules,{"pytesseract":pytesseract})
        self.ocrmodule.start();self.addCleanup(self.ocrmodule.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = patch.object(d, 'DB', Path(self.tmp.name)/'audit.sqlite')
        self.root = patch.object(d, 'ROOT', Path(self.tmp.name)/'pdf')
        self.db.start(); self.root.start()
        self.addCleanup(self.db.stop); self.addCleanup(self.root.stop)
        pdf = pymupdf.open()
        page = pdf.new_page()
        page.insert_text((72,72), 'Previously extracted text must remain unchanged and recoverable.')
        pdf.new_page()
        self.raw = pdf.tobytes(); pdf.close()
        self.job = d.create(self.raw, 'retry.pdf')['id']

    def test_missing_language_stops_then_explicit_retry_recovers(self):
        with patch.object(pytesseract, 'image_to_string', side_effect=pytesseract.TesseractError(1, 'deu unavailable')):
            state = d.process(self.job, batch=2, ocr=True)
        self.assertEqual(state['status'], 'ocr_error')
        self.assertEqual(state['next_page'], 1)
        self.assertEqual(d.page(self.job,1)['method'], 'ocr_error')
        previous = d.page(self.job,0)
        self.assertEqual((d.ROOT/(self.job+'.pdf')).read_bytes(), self.raw)
        with patch.object(pytesseract, 'image_to_string', return_value='Recovered German text') as engine:
            state = d.process(self.job, batch=2, ocr=True, retry=True)
        self.assertEqual(state['status'], 'complete')
        self.assertEqual(state['next_page'], 2)
        self.assertEqual(d.page(self.job,1)['text'], 'Recovered German text')
        self.assertEqual(d.page(self.job,0), previous)
        self.assertEqual(engine.call_count, 1)
        self.assertEqual(state['error'], '')

    def test_no_text_is_distinct_from_ocr_error_and_retryable(self):
        state = d.process(self.job, batch=2)
        self.assertEqual(state['status'], 'complete')
        self.assertEqual(d.page(self.job,1)['method'], 'no_text')
        with patch.object(pytesseract, 'image_to_string', return_value=''):
            state = d.process(self.job,batch=2,ocr=True,retry=True)
        self.assertEqual(state['status'], 'complete')
        self.assertEqual(d.page(self.job,1)['method'], 'ocr_no_text')

    def test_legacy_completed_unavailable_page_can_be_retried(self):
        d.process(self.job,batch=2)
        with d._db() as db:
            db.execute("UPDATE document_pages SET method='ocr_unavailable',text='' WHERE document_id=? AND page_number=1",(self.job,))
            db.commit()
        self.assertEqual(d.status(self.job)['status'],'ocr_error')
        self.assertEqual(d.process(self.job,batch=1)['next_page'],1)
        with patch.object(pytesseract, 'image_to_string', return_value='Restored legacy result'):
            state=d.process(self.job,batch=1,ocr=True,retry=True)
        self.assertEqual(state['status'],'complete')
        self.assertEqual(d.page(self.job,1)['text'],'Restored legacy result')

    def test_ocr_retry_requires_explicit_ocr_flag(self):
        with self.assertRaises(ValueError):
            d.process(self.job,retry=True)

    def test_retry_batches_do_not_starve_later_empty_pages(self):
        pdf=pymupdf.open()
        for _ in range(6):pdf.new_page()
        raw=pdf.tobytes();pdf.close()
        pid=d.create(raw,'blank-six.pdf')['id']
        d.process(pid,batch=5);d.process(pid,batch=5)
        with patch.object(pytesseract,'image_to_string',return_value='') as engine:
            d.process(pid,batch=5,ocr=True,retry=True)
            d.process(pid,batch=5,ocr=True,retry=True)
        self.assertEqual(engine.call_count,6)
        self.assertEqual(d.page(pid,5)['method'],'ocr_no_text')


    def test_retry_failure_preserves_existing_legacy_text(self):
        d.process(self.job,batch=2)
        with d._db() as db:
            db.execute("UPDATE document_pages SET method='ocr_unavailable',text='Previously recovered user text' WHERE document_id=? AND page_number=1",(self.job,));db.commit()
        with patch.object(pytesseract,'image_to_string',side_effect=RuntimeError('missing language')):
            state=d.process(self.job,batch=1,ocr=True,retry=True)
        self.assertEqual(state['status'],'ocr_error')
        self.assertEqual(d.page(self.job,1)['text'],'Previously recovered user text')
        self.assertEqual((d.ROOT/(self.job+'.pdf')).read_bytes(),self.raw)


class LargeDocumentFailureRecoveryTests(unittest.TestCase):
    def test_150_pages_failure_restart_and_recovery_preserve_pdf_and_text(self):
        import importlib.util
        import sqlite3
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);pdf=pymupdf.open()
            for i in range(150):
                page=pdf.new_page(width=120,height=120)
                if i!=75:page.insert_text((5,30),f'Page {i+1}',fontsize=8)
            raw=pdf.tobytes();pdf.close()
            fake=types.SimpleNamespace(image_to_string=lambda *a,**k: (_ for _ in ()).throw(RuntimeError('missing deu')))
            with patch.object(d,'DB',root/'db.sqlite'),patch.object(d,'ROOT',root/'pdf'),patch.dict(sys.modules,{'pytesseract':fake}):
                pid=d.create(raw,'150.pdf')['id']
                for _ in range(15):d.process(pid,batch=5,ocr=True)
                state=d.process(pid,batch=5,ocr=True)
                self.assertEqual((state['status'],state['next_page']),('ocr_error',75))
                previous=d.page(pid,74)
                spec=importlib.util.spec_from_file_location('pdf_restarted',d.__file__)
                reopened=importlib.util.module_from_spec(spec);spec.loader.exec_module(reopened)
                reopened.DB=d.DB;reopened.ROOT=d.ROOT
                self.assertEqual(reopened.process(pid,batch=5)['status'],'ocr_error')
                self.assertEqual(reopened.status(pid)['next_page'],75)
                with patch.object(fake,'image_to_string',return_value='Recovered page 76') as engine:
                    recovered=reopened.process(pid,batch=1,ocr=True,retry=True)
                self.assertEqual(engine.call_count,1)
                self.assertEqual(recovered['next_page'],76)
                while reopened.status(pid)['next_page']<150:reopened.process(pid,batch=5)
                self.assertEqual(reopened.status(pid)['status'],'complete')
                self.assertEqual(reopened.page(pid,74),previous)
                self.assertEqual(reopened.page(pid,75)['text'],'Recovered page 76')
                self.assertEqual((reopened.ROOT/(pid+'.pdf')).read_bytes(),raw)
                with sqlite3.connect(reopened.DB) as connection:
                    self.assertEqual(connection.execute('SELECT count(*) FROM document_pages WHERE document_id=?',(pid,)).fetchone()[0],150)
                connection.close()

class PDFRetryHTTPTests(unittest.TestCase):
    def test_real_upload_failure_bounded_explicit_retry_and_readback(self):
        import json
        import threading
        from http.server import ThreadingHTTPServer
        from urllib.request import Request,urlopen
        from urllib.error import HTTPError
        import web_app
        with tempfile.TemporaryDirectory() as folder,patch.object(d,'DB',Path(folder)/'db.sqlite'),patch.object(d,'ROOT',Path(folder)/'pdf'):
            server=ThreadingHTTPServer(('127.0.0.1',0),web_app.Handler)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            base='http://127.0.0.1:'+str(server.server_port)
            try:
                with urlopen(base+'/v1/security/bootstrap') as response:token=json.load(response)['csrf_token']
                def post(path,payload):
                    with urlopen(Request(base+path,data=json.dumps(payload).encode(),headers={'X-Study-CSRF':token,'Content-Type':'application/json'})) as response:return json.load(response)
                pdf=pymupdf.open();p=pdf.new_page(width=120,height=120);p.insert_text((5,30),'Original text',fontsize=8)
                for _ in range(2):pdf.new_page(width=120,height=120)
                raw=pdf.tobytes();pdf.close()
                with urlopen(Request(base+'/v1/documents',method='PUT',data=raw,headers={'X-Study-CSRF':token})) as response:job=json.load(response)
                path='/v1/documents/'+job['id']+'/process'
                fake=types.SimpleNamespace(image_to_string=lambda *a,**k: (_ for _ in ()).throw(RuntimeError('missing deu')))
                with patch.dict(sys.modules,{'pytesseract':fake}):
                    state=post(path,{'batch':2,'ocr':True})
                    self.assertEqual((state['status'],state['next_page']),('ocr_error',1))
                    original=d.page(job['id'],0)
                    self.assertEqual(post(path,{'batch':2,'ocr':True})['status'],'ocr_error')
                    with patch.object(fake,'image_to_string',return_value='Recovered text') as engine:
                        state=post(path,{'batch':1,'ocr':True,'retry':True})
                    self.assertEqual(engine.call_count,1);self.assertEqual(state['next_page'],2)
                    with patch.object(fake,'image_to_string',return_value='Final text'):
                        self.assertEqual(post(path,{'batch':1,'ocr':True})['status'],'complete')
                    for invalid in ({'batch':6,'ocr':True,'retry':True},{'batch':1,'ocr':'true','retry':True},{'batch':1,'ocr':True,'retry':'true'}):
                        with self.assertRaises(HTTPError) as caught:post(path,invalid)
                        self.assertEqual(caught.exception.code,400)
                with urlopen(base+'/v1/documents/'+job['id']+'/pages/1') as response:recovered=json.load(response)
                self.assertEqual(recovered['text'],'Recovered text')
                self.assertEqual(d.page(job['id'],0),original)
                self.assertEqual((d.ROOT/(job['id']+'.pdf')).read_bytes(),raw)
            finally:server.shutdown();server.server_close();thread.join()

class OCRRasterBoundsTests(unittest.TestCase):
    def test_huge_pdf_page_is_rejected_before_raster_allocation(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(d,'DB',Path(folder)/'db.sqlite'),patch.object(d,'ROOT',Path(folder)/'pdf'):
            pdf=pymupdf.open();pdf.new_page(width=50000,height=50000);raw=pdf.tobytes();pdf.close()
            pid=d.create(raw,'huge-page.pdf')['id']
            fake=types.SimpleNamespace(image_to_string=lambda *a,**k:'should not run')
            with patch.dict(sys.modules,{'pytesseract':fake}),patch.object(pymupdf.Page,'get_pixmap',side_effect=AssertionError('raster allocation attempted')) as raster:
                state=d.process(pid,batch=1,ocr=True)
            self.assertEqual(state['status'],'ocr_error')
            raster.assert_not_called()
            self.assertEqual((d.ROOT/(pid+'.pdf')).read_bytes(),raw)
