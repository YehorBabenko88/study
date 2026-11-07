import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import visual_memory, skill_memory
from study_core import LexicalItem,Anchor,build_scene

class SkillTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.p=patch.object(visual_memory,"DB",Path(self.temp.name)/"skills.sqlite3")
        self.p.start()
        self.sid=visual_memory.save(build_scene(
            LexicalItem("Tasse","de","чашка","die"),
            [Anchor("ta","тарелка","чашка")]))["scene_id"]
    def tearDown(self):
        self.p.stop()
        self.temp.cleanup()
    def test_separate_word_and_article(self):
        self.assertTrue(skill_memory.record(self.sid,"word","Tasse")["correct"])
        self.assertFalse(skill_memory.record(self.sid,"article","der")["correct"])
        state=skill_memory.overview(self.sid)
        self.assertEqual(state["word"]["correct"],1)
        self.assertEqual(state["article"]["correct"],0)
    def test_self_report_not_pronunciation_score(self):
        r=skill_memory.record(self.sid,"pronunciation","remembered")
        self.assertEqual(r["assessment"],"self_report")
        self.assertIsNone(r["expected"])
    def test_invalid_self_report(self):
        with self.assertRaises(ValueError):
            skill_memory.record(self.sid,"image_link","yes")
    def test_meaning(self):
        self.assertTrue(skill_memory.record(self.sid,"meaning"," ЧАШКА ")["correct"])

if __name__=="__main__":
    unittest.main()
