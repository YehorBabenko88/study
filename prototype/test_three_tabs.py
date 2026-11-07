import unittest
from pathlib import Path
ROOT=Path(__file__).parent
class ThreeTabTests(unittest.TestCase):
 def test_tabs(self):
  for path,tab in [("home.html","home"),("canvas.html","canvas"),("acoustic_studio.html","lab")]:
   html=(ROOT/path).read_text(encoding="utf-8")
   for url in ('href="/"','href="/canvas"','href="/phonovision-3d"'):
    self.assertIn(url,html)
   self.assertIn('data-tab="'+tab+'"',html)
   self.assertIn('aria-current',html)
 def test_home_actions(self):
  s=(ROOT/"home.html").read_text(encoding="utf-8")
  for marker in ('id="record"','id="ocr"','id="loadAudio"','/v1/speech-projects','/canvas?project='):
   self.assertIn(marker,s)
 def test_old_features_not_deleted(self):
  s=(ROOT/"web_app.py").read_text(encoding="utf-8")
  for route in ('"/legacy-board"','"/legacy-study"','"/legacy-spectral-relief"'):
   self.assertIn(route,s)
 def test_lab_has_spectral_panel(self):
  s=(ROOT/"acoustic_studio.html").read_text(encoding="utf-8")
  self.assertIn('src="/legacy-spectral-relief"',s)
if __name__=="__main__":unittest.main()
