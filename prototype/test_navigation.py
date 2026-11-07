import unittest
from pathlib import Path

ROOT=Path(__file__).parent
class NavigationTests(unittest.TestCase):
    def test_all_pages_have_primary_routes(self):
        for filename in ("study.html","board.html","canvas.html","acoustic_studio.html","phonovision_3d.html"):
            html=(ROOT/filename).read_text(encoding="utf-8")
            for route in ('href="/phonovision-3d"','href="/spectral-relief"','href="/canvas"','href="/board"'):
                self.assertIn(route,html,(filename,route))
    def test_recording_is_on_primary_3d_lab(self):
        app=(ROOT/"web_app.py").read_text(encoding="utf-8")
        studio=(ROOT/"acoustic_studio.html").read_text(encoding="utf-8")
        self.assertIn('("/acoustic-studio", "/phonovision-3d")',app)
        self.assertIn('parsed.path == "/spectral-relief"',app)
        for control in ('id="record"','id="stop"','id="file"','id="localASR"','id="pitch"','id="mesh"'):
            self.assertIn(control,studio)
if __name__=="__main__":
    unittest.main()
