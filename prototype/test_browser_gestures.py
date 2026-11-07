"""Optional Chromium end-to-end tests. Set STUDY_E2E_URL and install Playwright."""
import os
import unittest
try:
 from playwright.sync_api import sync_playwright
except ImportError:
 sync_playwright=None
URL=os.environ.get("STUDY_E2E_URL")
@unittest.skipUnless(URL and sync_playwright,"Requires Playwright and STUDY_E2E_URL")
class GestureBrowserTests(unittest.TestCase):
 def setUp(self):
  self.play=sync_playwright().start()
  self.browser=self.play.chromium.launch(headless=True)
  self.page=self.browser.new_page(viewport={"width":1440,"height":900})
  self.page.goto(URL.rstrip("/")+"/workspace")
 def tearDown(self):
  self.browser.close();self.play.stop()
 def test_card_drag_to_lab(self):
  canvas=self.page.frame_locator('iframe[src="/canvas"]')
  lab=self.page.frame_locator('iframe[src="/phonovision-3d"]')
  src=canvas.locator(".node.word").first.bounding_box()
  dst=lab.locator("#composition").bounding_box()
  self.page.mouse.move(src["x"]+30,src["y"]+25)
  self.page.mouse.down()
  self.page.mouse.move(dst["x"]+80,dst["y"]+55,steps=16)
  self.page.mouse.up()
  self.assertIn("Tasse",lab.locator("#imagePrompt").input_value())
 def test_sphere_to_existing_word_card(self):
  canvas=self.page.frame_locator('iframe[src="/canvas"]')
  lab=self.page.frame_locator('iframe[src="/phonovision-3d"]')
  src=lab.locator("#sphere").bounding_box()
  dst=canvas.locator(".node.word").first.bounding_box()
  self.page.mouse.move(src["x"]+100,src["y"]+100)
  self.page.mouse.down()
  self.page.mouse.move(dst["x"]+60,dst["y"]+45,steps=16)
  self.page.mouse.up()
  canvas.locator(".node.word img").first.wait_for(timeout=15000)
 def test_toggle_split_view(self):
  self.page.locator("#togglePanels").click()
  self.page.wait_for_url("**/canvas")
 def test_fling_detaches_outward_only(self):
  canvas=self.page.frame_locator('iframe[src="/canvas"]')
  outcome=canvas.locator("body").evaluate("""() => {
    const a={id:'a',x:350,y:0},b={id:'b',x:0,y:0};
    nodes=[a,b];edges=[{from:'a',to:'b'}];
    const detached=detachOnFling(a,350,0,100);
    return [detached,edges.length];
  }""")
  self.assertEqual(outcome,[True,0])
if __name__=="__main__":
 unittest.main()
