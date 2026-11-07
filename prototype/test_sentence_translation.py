import unittest
from unittest.mock import patch
import sentence_translation

class SentenceTests(unittest.TestCase):
    def test_validation(self):
        with self.assertRaises(ValueError):
            sentence_translation.translate("","de","ru")
        with self.assertRaises(ValueError):
            sentence_translation.translate("Hallo","de","de")
    def test_tokenization(self):
        self.assertEqual(sentence_translation.split_words("Ich stelle die Tasse auf den Tisch."),
                         ["Ich","stelle","die","Tasse","auf","den","Tisch"])
    def test_no_fake_translation_when_missing_backend(self):
        # Model availability depends on local packages; no invented output.
        with patch.dict("sys.modules",{"argostranslate":None}):
            r=sentence_translation.translate("Hallo Welt","de","ru")
        self.assertEqual(r["status"],"unavailable")
        self.assertIsNone(r["translation"])
if __name__=="__main__":
    unittest.main()
