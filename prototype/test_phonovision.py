import io, math, struct, unittest, wave
import phonovision
class PhonoVisionTests(unittest.TestCase):
 def test_signal(self):
  b=io.BytesIO()
  with wave.open(b,"wb") as w:
   w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000)
   w.writeframes(struct.pack("<"+"h"*8000,*[int(12000*math.sin(2*math.pi*440*i/16000)) for i in range(8000)]))
  r=phonovision.analyze_wav(b.getvalue())
  self.assertGreater(len(r["spectrogram"]),0)
  self.assertIn("<svg",phonovision.svg(r))
 def test_invalid(self):
  with self.assertRaises(ValueError):phonovision.analyze_wav(b"no")
 def test_metaphor_is_not_science(self):
  self.assertEqual(phonovision.metaphor("sch")["evidence"],"creative_heuristic_not_phonetic_analysis")
if __name__=="__main__":unittest.main()
