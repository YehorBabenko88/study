import io,unittest,wave,struct
import local_speech
def wav():
 b=io.BytesIO()
 with wave.open(b,"wb") as w:
  w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(struct.pack("<"+"h"*1600,*([0]*1600)))
 return b.getvalue()
class LocalSpeechTests(unittest.TestCase):
 def test_requires_local_model(self):
  self.assertEqual(local_speech.transcribe(wav(),model_dir="")["reason"],"local_model_not_configured")
 def test_requires_aligner(self):
  self.assertEqual(local_speech.align(wav(),"Hallo",align_model_dir="")["reason"],"local_alignment_model_not_configured")
 def test_bad_input(self):
  with self.assertRaises(Exception):local_speech.transcribe(b"bad")
if __name__=="__main__":unittest.main()
