import unittest
from pathlib import Path
ROOT=Path(__file__).parent
class NavigationTests(unittest.TestCase):
    def test_current_primary_routes(self):
        for filename in ("home.html","canvas.html","acoustic_studio.html"):
            html=(ROOT/filename).read_text(encoding="utf-8")
            for route in ('href="/"','href="/phonovision-3d"','href="/canvas"','href="/workspace"'):
                self.assertIn(route,html,(filename,route))
    def test_recording_on_3d_lab_and_legacy_relief(self):
        app=(ROOT/"web_app.py").read_text(encoding="utf-8")
        studio=(ROOT/"acoustic_studio.html").read_text(encoding="utf-8")
        self.assertIn('"/phonovision-3d"',app)
        self.assertIn('"/legacy-spectral-relief"',app)
        for control in ('id="record"','id="stop"','id="file"','id="localASR"','id="pitch"','id="mesh"'):
            self.assertIn(control,studio)
if __name__=="__main__":unittest.main()
