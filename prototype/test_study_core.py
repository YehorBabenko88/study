import unittest
from study_core import Anchor, LexicalItem, build_scene, check_recall

class StudyCoreTests(unittest.TestCase):
    def setUp(self):
        self.item = LexicalItem("Tasse", "de", "чашка", "die", "/ˈtasə/")
        self.anchors = [Anchor("ta", "тарелка", "чашка"), Anchor("sə", "робот", "чашка")]

    def test_composite_scene(self):
        scene = build_scene(self.item, self.anchors)
        self.assertEqual(len(scene["objects"]), 2)
        self.assertEqual(scene["target"]["article"], "die")
        self.assertEqual(scene["render_status"], "text_only")

    def test_empty_anchors_rejected(self):
        with self.assertRaises(ValueError):
            build_scene(self.item, [])

    def test_empty_sound_fragment_rejected(self):
        with self.assertRaises(ValueError):
            build_scene(self.item, [Anchor("", "робот", "чашка")])

    def test_unaided_recall(self):
        self.assertTrue(check_recall("die Tasse", " DIE   tasse ")["correct"])
        self.assertTrue(check_recall("die Tasse", "die Tasse")["unaided"])
        self.assertFalse(check_recall("die Tasse", "der Tasse")["correct"])
        self.assertFalse(check_recall("die Tasse", "die Tasse", cues_shown=True)["unaided"])

if __name__ == "__main__":
    unittest.main()
