import unittest
from pathlib import Path
ROOT=Path(__file__).parent
class CrossPanelTests(unittest.TestCase):
 def test_workspace(self):
  s=(ROOT/"workspace.html").read_text(encoding="utf-8")
  self.assertIn('src="/canvas"',s)
  self.assertIn('src="/phonovision-3d"',s)
 def test_inline_edit_and_drag(self):
  s=(ROOT/"canvas.html").read_text(encoding="utf-8")
  self.assertIn('"dblclick"',s)
  self.assertIn("application/x-study-node",s)
  self.assertIn("application/x-study-asset",s)
 def test_lab_composer(self):
  s=(ROOT/"acoustic_studio.html").read_text(encoding="utf-8")
  self.assertIn('id="composition"',s)
  self.assertIn('id="imagePrompt"',s)
  self.assertIn("application/x-study-asset",s)
if __name__=="__main__":unittest.main()
