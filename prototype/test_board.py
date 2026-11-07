import unittest
from pathlib import Path
class BoardTests(unittest.TestCase):
    def test_board_has_four_lanes_and_safe_dom(self):
        html=Path(__file__).with_name("board.html").read_text(encoding="utf-8")
        for x in ("Словарь","Звуки и образы","Предложение","Моя библиотека","/v1/mnemonics","/v1/translate"):
            self.assertIn(x,html)
        self.assertNotIn("innerHTML",html)
if __name__=="__main__":unittest.main()
