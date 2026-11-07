import io,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import document_import
class PDFImportTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  self.a=patch.object(document_import,"DB",Path(self.tmp.name)/"db.sqlite")
  self.b=patch.object(document_import,"ROOT",Path(self.tmp.name)/"docs")
  self.a.start();self.b.start()
 def tearDown(self):
  self.b.stop();self.a.stop();self.tmp.cleanup()
 def test_text_pdf_pages_resume(self):
  try:import fitz
  except ImportError:self.skipTest("PyMuPDF not installed")
  pdf=fitz.open()
  for i in range(3):
   page=pdf.new_page();page.insert_text((72,72),"Hallo Welt Seite "+str(i+1))
  data=pdf.tobytes();pdf.close()
  job=document_import.create(data,"book.pdf")
  self.assertEqual(job["page_count"],3)
  r=document_import.process(job["id"],batch=2)
  self.assertEqual(r["next_page"],2)
  self.assertIn("Hallo Welt",document_import.page(job["id"],0)["text"])
  r=document_import.process(job["id"],batch=2)
  self.assertEqual(r["status"],"complete")
 def test_reject_nonpdf(self):
  with self.assertRaises(ValueError):document_import.create(b"not pdf","x")
if __name__=="__main__":unittest.main()
