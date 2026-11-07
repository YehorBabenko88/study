import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime,timezone,timedelta
import visual_memory, learning_memory
from study_core import LexicalItem,Anchor,build_scene

class LearningMemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.patch=patch.object(visual_memory,"DB",Path(self.tmp.name)/"study.sqlite3")
        self.patch.start()
        scene=build_scene(LexicalItem("Tasse","de","чашка","die"),[Anchor("ta","тарелка","чашка")])
        self.sid=visual_memory.save(scene)["scene_id"]
        self.now=datetime(2026,11,7,tzinfo=timezone.utc)

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_recall_schedule_persists(self):
        self.assertEqual(len(learning_memory.due_scenes(self.now)),1)
        result=learning_memory.submit(self.sid," DIE  tasse ",self.now)
        self.assertTrue(result["correct"])
        self.assertEqual(result["streak"],1)
        self.assertEqual(len(learning_memory.due_scenes(self.now)),0)
        self.assertEqual(len(learning_memory.due_scenes(self.now+timedelta(days=2))),1)
        self.assertEqual(learning_memory.stats(self.sid)["attempts"],1)

    def test_wrong_answer_resets(self):
        learning_memory.submit(self.sid,"die Tasse",self.now)
        result=learning_memory.submit(self.sid,"der Tasse",self.now+timedelta(days=1))
        self.assertFalse(result["correct"])
        self.assertEqual(result["streak"],0)
        self.assertEqual(learning_memory.stats(self.sid)["correct"],1)

    def test_invalid_response(self):
        with self.assertRaises(ValueError):
            learning_memory.submit(self.sid,"x"*201)

if __name__=="__main__":
    unittest.main()
