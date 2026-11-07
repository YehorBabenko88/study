import unittest
from pathlib import Path
ROOT=Path(__file__).parent
class SharedSpeechUITests(unittest.TestCase):
 def test_every_view_has_speech_project(self):
  checks={
   "acoustic_studio.html":('id="saveSpeech"','/v1/speech-projects'),
   "board.html":('id="speechList"','id="splitSpeech"','/v1/speech-projects'),
   "canvas.html":('id="speechList"','id="speechGraph"','/v1/speech-projects'),
   "study.html":('id="sharedSpeechList"','/v1/speech-projects'),
   "phonovision_3d.html":('id="sharedSpeechList"','/v1/speech-projects')
  }
  for name,needles in checks.items():
   text=(ROOT/name).read_text(encoding="utf-8")
   for needle in needles:self.assertIn(needle,text,(name,needle))
 def test_server_routes(self):
  text=(ROOT/"web_app.py").read_text(encoding="utf-8")
  for route in ('parsed.path == "/v1/speech-projects"','"/v1/speech-projects"','save_speech_audio','read_speech_audio'):
   self.assertIn(route,text)
if __name__=="__main__":unittest.main()
