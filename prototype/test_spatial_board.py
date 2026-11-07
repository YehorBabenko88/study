import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import visual_memory,spatial_board
class SpatialBoardTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory()
        self.p=patch.object(visual_memory,"DB",Path(self.t.name)/"test.db")
        self.p.start()
    def tearDown(self):
        self.p.stop();self.t.cleanup()
    def test_roundtrip(self):
        doc={"nodes":[{"id":"a","type":"word","text":"Haus","x":2,"y":4},{"id":"b","type":"syllable","text":"Haus","x":6,"y":8}],"edges":[{"from":"a","to":"b"}]}
        bid=spatial_board.save(doc)["id"]
        self.assertEqual(spatial_board.load(bid)["nodes"],doc["nodes"])
        self.assertEqual(len(spatial_board.list_boards()),1)
    def test_invalid_link(self):
        with self.assertRaises(ValueError):
            spatial_board.save({"nodes":[],"edges":[{"from":"x","to":"y"}]})
    def test_duplicate_id(self):
        with self.assertRaises(ValueError):
            spatial_board.validate({"nodes":[{"id":"a","type":"word"},{"id":"a","type":"word"}],"edges":[]})
if __name__=="__main__":unittest.main()
