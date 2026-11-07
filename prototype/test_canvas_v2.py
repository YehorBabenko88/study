import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import spatial_board,visual_memory
class CanvasV2Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.p=patch.object(visual_memory,"DB",Path(self.tmp.name)/"db.sqlite3")
        self.p.start()
    def tearDown(self):
        self.p.stop();self.tmp.cleanup()
    def test_valid_scene_ref(self):
        sid="00000000-0000-0000-0000-000000000001"
        doc={"nodes":[{"id":"x","type":"image","text":"образ","x":0,"y":0,"scene_id":sid}],"edges":[]}
        self.assertEqual(spatial_board.load(spatial_board.save(doc)["id"])["nodes"][0]["scene_id"],sid)
    def test_reject_nan(self):
        with self.assertRaises(ValueError):
            spatial_board.validate({"nodes":[{"id":"x","type":"word","x":math.nan,"y":0}],"edges":[]})
    def test_reject_invalid_scene_ref(self):
        with self.assertRaises(ValueError):
            spatial_board.validate({"nodes":[{"id":"x","type":"image","scene_id":"../bad"}],"edges":[]})
if __name__=="__main__":unittest.main()
