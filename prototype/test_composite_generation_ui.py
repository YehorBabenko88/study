import unittest
from pathlib import Path
ROOT=Path(__file__).parent
class CompositeGenerationContract(unittest.TestCase):
 def test_opt_in_and_existing_routes(self):
  canvas=(ROOT/"canvas.html").read_text(encoding="utf-8")
  app=(ROOT/"web_app.py").read_text(encoding="utf-8")
  flow=(ROOT/"composition-canvas.js").read_text(encoding="utf-8")
  for term in ('id="generateComposite"','id="compositionPrompt"','id="saveCompositionRevision"','id="generateReviewedComposition"','id="cancelCompositionJob"','/composition-canvas.js'):
   self.assertIn(term,canvas)
  for term in ('/v1/compositions','/generate','/cancel','user_prompt','parameters','direction:'):
   self.assertIn(term,flow)
  self.assertIn('composition_dispatch',app)
 def test_non_destructive_graph(self):
  flow=(ROOT/"composition-canvas.js").read_text(encoding="utf-8")
  for term in ('generation_revision_id','generation_job_id','generation_provenance','image_assets:[item.asset_id]',"relation:'association'",'appliedOutputs'):
   self.assertIn(term,flow)
 def test_comfy_is_opt_in(self):
  adapter=(ROOT/"comfy_adapter.py").read_text(encoding="utf-8")
  self.assertIn('STUDY_COMFYUI_ENABLED',adapter)
  self.assertIn('127.0.0.1:8188',adapter)
if __name__=="__main__":unittest.main()
