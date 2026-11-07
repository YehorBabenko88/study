import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import visual_memory
from study_core import LexicalItem, Anchor, build_scene

class VisualMemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patcher = patch.object(visual_memory, "DB", Path(self.tmp.name) / "test.sqlite3")
        self.patcher.start()
        self.scene = build_scene(LexicalItem("Tasse","de","чашка","die"),
                                 [Anchor("ta","тарелка","держит чашку"), Anchor("sə","робот","видит чашку")])

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def test_save_list_get_delete(self):
        saved = visual_memory.save(self.scene)
        self.assertEqual(len(visual_memory.list_scenes()), 1)
        self.assertEqual(visual_memory.get_scene(saved["scene_id"])["target"]["lemma"], "Tasse")
        self.assertTrue(visual_memory.delete_scene(saved["scene_id"]))
        self.assertIsNone(visual_memory.get_scene(saved["scene_id"]))

    def test_svg_escapes_untrusted_text(self):
        self.scene["anchors"][0]["object_name"] = "<script>alert(1)</script>"
        output = visual_memory.svg(self.scene).decode()
        self.assertIn("&lt;script&gt;", output)
        self.assertNotIn("<script>", output)
        self.assertIn("робот", output)

if __name__ == "__main__":
    unittest.main()
