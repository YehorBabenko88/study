import os
import unittest
from unittest.mock import patch
from ai_images import configured, prompt_for, generate

class ImageProviderTests(unittest.TestCase):
    def setUp(self):
        self.scene = {"target": {"translation": "чашка"}, "anchors": [
            {"sound_fragment": "ta", "object_name": "тарелка", "meaning_link": "держит чашку"},
            {"sound_fragment": "sə", "object_name": "робот", "meaning_link": "пьёт чай"}]}

    def test_prompt_includes_all_links(self):
        p = prompt_for(self.scene, "добавь крылья")
        self.assertIn("тарелка", p)
        self.assertIn("робот", p)
        self.assertIn("добавь крылья", p)

    def test_no_cloud_without_configuration(self):
        with patch.dict(os.environ, {"STUDY_IMAGE_API_URL": "", "STUDY_IMAGE_API_KEY": ""}):
            self.assertFalse(configured())
            with self.assertRaises(RuntimeError):
                generate("00000000-0000-0000-0000-000000000000")

    def test_instruction_length(self):
        with self.assertRaises(ValueError):
            prompt_for(self.scene, "x" * 401)

if __name__ == "__main__":
    unittest.main()
