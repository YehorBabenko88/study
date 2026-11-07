import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from io import BytesIO
from PIL import Image
import board_assets
class BoardAssetTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  self.p=patch.object(board_assets,"ROOT",Path(self.tmp.name))
  self.p.start()
 def tearDown(self):
  self.p.stop();self.tmp.cleanup()
 def test_png(self):
  b=BytesIO();Image.new("RGB",(12,12),"blue").save(b,"PNG")
  a=board_assets.store(b.getvalue())
  self.assertTrue(board_assets.read(a["asset_id"]).startswith(b"\\x89PNG".replace(b"\\x89",bytes([137]))))
 def test_invalid(self):
  with self.assertRaises(ValueError):board_assets.store(b"bad")
 def test_bad_lang(self):
  b=BytesIO();Image.new("RGB",(12,12)).save(b,"PNG")
  with self.assertRaises(ValueError):board_assets.recognize(b.getvalue(),"xxx")
if __name__=="__main__":unittest.main()
