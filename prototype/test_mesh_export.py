import unittest
import mesh_export
class MeshTests(unittest.TestCase):
 def test_gltf(self):
  d=mesh_export.mesh([[.1,.8,.2]],"vase",label="Tasse")
  self.assertEqual(d["asset"]["version"],"2.0")
  self.assertEqual(d["nodes"][0]["name"],"Tasse")
  self.assertEqual(d["accessors"][1]["count"],32*64*6)
 def test_profile(self):
  d=mesh_export.mesh([[.5]],profile=[1]*9)
  self.assertIn("buffers",d)
 def test_bad_shape(self):
  with self.assertRaises(ValueError):mesh_export.mesh([[.1]],"cat")
if __name__=="__main__":unittest.main()
