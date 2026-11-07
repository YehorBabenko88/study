import unittest
from pathlib import Path
ROOT=Path(__file__).parent
class PDFComfyUITests(unittest.TestCase):
 def test_routes(self):
  s=(ROOT/"web_app.py").read_text(encoding="utf-8")
  for r in ('"/v1/documents"','"/v1/comfy/generate"','comfy_image','process_document'):
   self.assertIn(r,s)
 def test_canvas(self):
  s=(ROOT/"canvas.html").read_text(encoding="utf-8")
  for r in ('id="pdfUpload"','id="pdfNext"','id="pdfPage"','minX','maxX'):
   self.assertIn(r,s)
 def test_comfy_ui(self):
  s=(ROOT/"acoustic_studio.html").read_text(encoding="utf-8")
  for r in ('id="comfyGenerate"','id="comfyImage"','/v1/comfy/jobs/'):
   self.assertIn(r,s)
if __name__=="__main__":unittest.main()
