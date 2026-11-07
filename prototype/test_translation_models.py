import unittest
from unittest.mock import patch
import translation_models

class TranslationModelsTests(unittest.TestCase):
    def test_explicit_consent_required(self):
        with self.assertRaises(ValueError):
            translation_models.install_file("anything.argosmodel")
    def test_reject_non_model(self):
        with self.assertRaises(ValueError):
            translation_models.install_file("anything.zip",consent=True)
    def test_no_argos(self):
        with patch.dict("sys.modules",{"argostranslate":None}):
            self.assertFalse(translation_models.installed()["available"])
if __name__=="__main__":
    unittest.main()
