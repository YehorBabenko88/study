import unittest
from pathlib import Path
class CanvasTests(unittest.TestCase):
    def test_canvas_core_controls(self):
        s=Path(__file__).with_name("canvas.html").read_text(encoding="utf-8")
        for marker in ("pointerdown","pointermove","wheel","/v1/boards","Слог","Разбить на слова","Связать"):
            self.assertIn(marker,s)
        self.assertNotIn("innerHTML",s)
if __name__=="__main__":unittest.main()
