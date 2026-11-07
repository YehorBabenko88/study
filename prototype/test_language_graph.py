import io, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import board_assets, spatial_board, visual_memory
class LanguageGraphTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  self.a=patch.object(board_assets,"ROOT",Path(self.tmp.name)/"assets")
  self.b=patch.object(visual_memory,"DB",Path(self.tmp.name)/"data.sqlite3")
  self.a.start();self.b.start()
 def tearDown(self):
  self.b.stop();self.a.stop();self.tmp.cleanup()
 def test_image_graph_roundtrip(self):
  out=io.BytesIO();Image.new("RGB",(16,16),"green").save(out,"PNG")
  asset=board_assets.store(out.getvalue())
  doc={"nodes":[{"id":"w","type":"word","text":"Tasse","x":1,"y":2},{"id":"p","type":"image","text":"Чашка","x":3,"y":4,"asset_id":asset["asset_id"]}],"edges":[{"from":"w","to":"p","relation":"association"}]}
  bid=spatial_board.save(doc)["id"]
  self.assertEqual(spatial_board.load(bid)["edges"][0]["relation"],"association")
  self.assertIsNotNone(board_assets.read(asset["asset_id"]))
 def test_bad_relation(self):
  with self.assertRaises(ValueError):
   spatial_board.validate({"nodes":[{"id":"a","type":"letter"},{"id":"b","type":"word"}],"edges":[{"from":"a","to":"b","relation":"invalid"}]})
if __name__=="__main__":unittest.main()
