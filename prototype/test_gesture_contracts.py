import unittest
from pathlib import Path
ROOT=Path(__file__).parent
class CrossPanelGestureContracts(unittest.TestCase):
 def test_overlay_and_messages(self):
  s=(ROOT/"workspace.html").read_text(encoding="utf-8")
  for term in ("study-transfer-start","study-transfer-deliver","transfer-shield","pointermove","pointerup","frameAt"):
   self.assertIn(term,s)
 def test_canvas_drag_and_fling(self):
  s=(ROOT/"canvas.html").read_text(encoding="utf-8")
  for term in ("e.button!==0","detachOnFling","movedAway","attachImage","nodeAtCanvas","study-transfer-deliver"):
   self.assertIn(term,s)
 def test_lab_sphere_and_images(self):
  s=(ROOT/"acoustic_studio.html").read_text(encoding="utf-8")
  for term in ('$("sphere").addEventListener("pointerdown"','$("referencePreview").addEventListener("pointerdown"','$("comfyImage").addEventListener("pointerdown"'):
   self.assertIn(term,s)
 def test_any_card_can_hold_image(self):
  s=(ROOT/"spatial_board.py").read_text(encoding="utf-8")
  self.assertIn('if "asset_id" in n:',s)
  self.assertNotIn('n["type"]!="image" or not isinstance(n["asset_id"]',s)
if __name__=="__main__":
 unittest.main()
