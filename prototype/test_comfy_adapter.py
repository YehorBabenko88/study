import os,unittest
from unittest.mock import patch
import comfy_adapter
class ComfyTests(unittest.TestCase):
 def test_disabled(self):
  with patch.dict(os.environ,{"STUDY_COMFYUI_ENABLED":"0"}):
   self.assertEqual(comfy_adapter.submit("A cup")["status"],"unavailable")
 def test_workflow(self):
  with patch.dict(os.environ,{"STUDY_COMFYUI_CHECKPOINT":"reviewed.safetensors"}):
   w=comfy_adapter.workflow("A surreal cup")
   self.assertEqual(w["7"]["class_type"],"SaveImage")
   self.assertEqual(w["5"]["inputs"]["seed"],0)
 def test_reject_prompt(self):
  with self.assertRaises(ValueError):comfy_adapter.workflow("")
if __name__=="__main__":unittest.main()
