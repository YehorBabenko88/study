import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pymupdf
import pytesseract
import document_import as d


class PDFOCRRetryTests(unittest.TestCase):
    def setUp(self):
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
        with patch.object(pytesseract, 'image_to_string', return_value='Restored legacy result'):
            state=d.process(self.job,batch=1,ocr=True,retry=True)
        self.assertEqual(state['status'],'complete')
        self.assertEqual(d.page(self.job,1)['text'],'Restored legacy result')

    def test_ocr_retry_requires_explicit_ocr_flag(self):
        with self.assertRaises(ValueError):
            d.process(self.job,retry=True)


if __name__ == '__main__':
    unittest.main()
