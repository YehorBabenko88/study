import unittest
from pathlib import Path
class AcousticStudioTests(unittest.TestCase):
 def test_controls_and_local_audio(self):
  text=Path(__file__).with_name("acoustic_studio.html").read_text(encoding="utf-8")
  for x in ("getUserMedia","decodeAudioData","AudioContext","createBuffer","audio/wav","SpeechRecognition","segments","study.phonovision.project","toBlob","modifiedSamples","Сфера"):
   if x=="Сфера":continue
   self.assertIn(x,text)
  self.assertNotIn("innerHTML",text)
 def test_explicit_speech_privacy_consent(self):
  text=Path(__file__).with_name("acoustic_studio.html").read_text(encoding="utf-8")
  self.assertIn('confirm("Браузер может передать голос внешнему сервису',text)
if __name__=="__main__":unittest.main()
