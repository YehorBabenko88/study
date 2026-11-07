import unittest
import pitch_shift
class PitchShiftTests(unittest.TestCase):
 def test_reject_invalid(self):
  for x in (float("nan"),100,"high"):
   with self.assertRaises(ValueError):pitch_shift.shift_wav(b"",x)
if __name__=="__main__":unittest.main()
