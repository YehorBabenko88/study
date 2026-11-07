import unittest
from pathlib import Path
ROOT=Path(__file__).parent
class CompositeGenerationContract(unittest.TestCase):
 def test_opt_in_and_existing_routes(self):
  canvas=(ROOT/"canvas.html").read_text(encoding="utf-8")
  app=(ROOT/"web_app.py").read_text(encoding="utf-8")
  for term in ('id="generateComposite"','window.confirm(', 'buildCompositePrompt(', '"/v1/comfy/generate"', '"/v1/comfy/jobs/"', '"/v1/board-assets"', 'original.disabled=true', 'original.disabled=false'):
   self.assertIn(term,canvas)
  self.assertIn('"/v1/comfy/generate"',app)
 def test_non_destructive_graph(self):
  canvas=(ROOT/"canvas.html").read_text(encoding="utf-8")
  self.assertIn('edges.push({from:base.id,to:generated.id,relation:"association"})',canvas)
  self.assertIn('image_assets:[saved.asset_id]',canvas)
 def test_comfy_is_opt_in(self):
  adapter=(ROOT/"comfy_adapter.py").read_text(encoding="utf-8")
  self.assertIn('STUDY_COMFYUI_ENABLED',adapter)
  self.assertIn('127.0.0.1:8188',adapter)
if __name__=="__main__":unittest.main()
