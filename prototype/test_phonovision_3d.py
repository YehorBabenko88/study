import unittest
from pathlib import Path
class PhonoVision3DTests(unittest.TestCase):
 def test_ui_contract(self):
  html=Path(__file__).with_name("phonovision_3d.html").read_text(encoding="utf-8")
  for term in ("spectrogram","requestAnimationFrame","toBlob","/v1/phonovision/analyze","rotation","height","demo"):
   self.assertIn(term,html)
  self.assertNotIn("innerHTML",html)
if __name__=="__main__":unittest.main()
