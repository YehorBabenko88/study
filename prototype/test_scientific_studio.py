import unittest
from pathlib import Path
class ScientificStudioTests(unittest.TestCase):
 def test_ui_has_scientific_controls(self):
  html=Path(__file__).with_name("acoustic_studio.html").read_text(encoding="utf-8")
  for term in ("/v1/speech/transcribe","/v1/speech/align","/v1/speech/pitch-shift","/v1/phonovision/mesh","study-acoustic-object.gltf","X-Transcript-B64"):
   self.assertIn(term,html)
  self.assertNotIn("innerHTML",html)
 def test_api_routes(self):
  src=Path(__file__).with_name("web_app.py").read_text(encoding="utf-8")
  for term in ("/v1/speech/transcribe","/v1/speech/align","/v1/speech/pitch-shift","/v1/phonovision/mesh"):
   self.assertIn(term,src)
if __name__=="__main__":unittest.main()
