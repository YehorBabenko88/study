import io,struct,tempfile,unittest,wave
from pathlib import Path
from unittest.mock import patch
import speech_projects
class SpeechProjectsTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  self.p1=patch.object(speech_projects,"DB",Path(self.tmp.name)/"db.sqlite")
  self.p2=patch.object(speech_projects,"AUDIO_DIR",Path(self.tmp.name)/"audio")
  self.p1.start();self.p2.start()
 def tearDown(self):
  self.p2.stop();self.p1.stop();self.tmp.cleanup()
 def test_roundtrip(self):
  p=speech_projects.save({"title":"Tasse","lang":"de","transcript":"Die Tasse.","segments":[{"label":"Die","t":0.1}]})
  self.assertEqual(speech_projects.get(p["id"])["transcript"],"Die Tasse.")
  self.assertEqual(len(speech_projects.list_projects()),1)
  b=io.BytesIO()
  with wave.open(b,"wb") as w:
   w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(struct.pack("<"+"h"*1600,*([0]*1600)))
  speech_projects.save_audio(p["id"],b.getvalue())
  self.assertEqual(speech_projects.read_audio(p["id"]),b.getvalue())
  self.assertTrue(speech_projects.get(p["id"])["has_audio"])
 def test_invalid_segment(self):
  with self.assertRaises(ValueError):
   speech_projects.save({"segments":[{"label":"a","t":float("nan")}]})
if __name__=="__main__":unittest.main()
