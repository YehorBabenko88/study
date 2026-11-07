import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import ai_images
import visual_memory
from study_core import LexicalItem, Anchor, build_scene

class ImportImageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = patch.object(visual_memory, "DB", Path(self.tmp.name) / "test.sqlite3")
        self.media = patch.object(ai_images, "MEDIA", Path(self.tmp.name) / "media")
        self.db.start()
        self.media.start()
        scene = build_scene(LexicalItem("Tasse", "de", "чашка", "die"), [Anchor("ta", "тарелка", "чашка")])
        self.id = visual_memory.save(scene)["scene_id"]

    def tearDown(self):
        self.media.stop()
        self.db.stop()
        self.tmp.cleanup()

    def test_valid_png_roundtrip(self):
        buf = io.BytesIO()
        Image.new("RGB", (32, 32), "blue").save(buf, format="PNG")
        result = ai_images.import_png(self.id, buf.getvalue())
        self.assertEqual(result["source"], "user_import")
        self.assertEqual(ai_images.image_bytes(self.id), buf.getvalue())

    def test_invalid_png_rejected(self):
        with self.assertRaises(ValueError):
            ai_images.import_png(self.id, b"not a png")

    def test_missing_scene_rejected(self):
        with self.assertRaises(KeyError):
            ai_images.import_png("00000000-0000-0000-0000-000000000000", b"no")

if __name__ == "__main__":
    unittest.main()
