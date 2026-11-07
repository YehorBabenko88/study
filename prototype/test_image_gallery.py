import unittest
from spatial_board import validate
class ImageGalleryTests(unittest.TestCase):
 def node(self,**extra):
  return {"id":"node-1","type":"word","text":"Tasse","x":10,"y":20,**extra}
 def test_multiple_images_on_word(self):
  ids=["00000000-0000-4000-8000-000000000001","00000000-0000-4000-8000-000000000002"]
  doc=validate({"nodes":[self.node(image_assets=ids)],"edges":[]})
  self.assertEqual(doc["nodes"][0]["image_assets"],ids)
 def test_invalid_id_rejected(self):
  with self.assertRaises(ValueError):validate({"nodes":[self.node(image_assets=["bad"])],"edges":[]})
 def test_duplicate_rejected(self):
  uid="00000000-0000-4000-8000-000000000001"
  with self.assertRaises(ValueError):validate({"nodes":[self.node(image_assets=[uid,uid])],"edges":[]})
 def test_too_many_rejected(self):
  ids=[f"00000000-0000-4000-8000-{i:012d}" for i in range(13)]
  with self.assertRaises(ValueError):validate({"nodes":[self.node(image_assets=ids)],"edges":[]})
if __name__=="__main__":unittest.main()
