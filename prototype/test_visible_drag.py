import unittest
from pathlib import Path
ROOT=Path(__file__).parent
class VisibleDragTests(unittest.TestCase):
 def test_floating_preview(self):
  s=(ROOT/"workspace.html").read_text(encoding="utf-8")
  for marker in ("drag-hint","ghost-label","transform:rotate(-2deg)","document.addEventListener(\"pointermove\"","document.addEventListener(\"pointerup\"","frameAt(e.clientX,e.clientY)"):
   self.assertIn(marker,s)
 def test_canvas_visual_feedback(self):
  s=(ROOT/"canvas.html").read_text(encoding="utf-8")
  for marker in (".node.dragging","drag-active","el.classList.add(\"dragging\")","margin=45","offset.x-=7","pointercancel"):
   self.assertIn(marker,s)
if __name__=="__main__":unittest.main()
