"""Concurrent OCR retries must not commit stale results over a recovered page."""
import sys,tempfile,threading,time,types,unittest
from pathlib import Path
from unittest.mock import patch
import pymupdf
import document_import as d

class DocumentConcurrencyTests(unittest.TestCase):
    def test_concurrent_retries_are_serialized_and_keep_recovered_state(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(d,'DB',Path(folder)/'db.sqlite'),patch.object(d,'ROOT',Path(folder)/'pdf'):
            pdf=pymupdf.open();pdf.new_page(width=120,height=120);raw=pdf.tobytes();pdf.close()
            pid=d.create(raw,'scan.pdf')['id'];d.process(pid,batch=1)
            with d._db() as db:
                db.execute("UPDATE document_pages SET method='ocr_error' WHERE document_id=?",(pid,));db.commit()
            entered=threading.Event();release=threading.Event();second_started=threading.Event()
            calls=[];errors=[]
            def engine(*args,**kwargs):
                calls.append(threading.current_thread().name)
                if len(calls)==1:
                    entered.set();release.wait(2);raise RuntimeError('slow failed OCR')
                return 'Recovered German text'
            def run(second=False):
                if second:second_started.set()
                try:d.process(pid,batch=1,ocr=True,retry=True)
                except Exception as exc:errors.append(exc)
            with patch.dict(sys.modules,{'pytesseract':types.SimpleNamespace(image_to_string=engine)}):
                first=threading.Thread(target=run,name='first');second=threading.Thread(target=lambda:run(True),name='second')
                first.start();self.assertTrue(entered.wait(2));second.start();self.assertTrue(second_started.wait(1))
                try:
                    time.sleep(.15)
                    self.assertEqual(len(calls),1,'second OCR entered before first retry completed')
                finally:
                    release.set();first.join(3);second.join(3)
            self.assertFalse(first.is_alive());self.assertFalse(second.is_alive());self.assertEqual(errors,[])
            self.assertEqual(d.status(pid)['status'],'complete')
            self.assertEqual(d.page(pid,0)['text'],'Recovered German text')
            self.assertEqual((d.ROOT/(pid+'.pdf')).read_bytes(),raw)
