"""Real Chromium UI against real Study HTTP and explicitly fake local Comfy."""
import os
import unittest
import comfy_adapter
import test_independent_mock_generation as mock

@unittest.skipUnless(hasattr(comfy_adapter,'JobRegistry') and os.getenv('STUDY_E2E_URL'), 'Requires registry, Playwright, and explicit browser run')
class IndependentGenerationBrowser(unittest.TestCase):
    def test_click_confirm_generate_preserves_graph_and_stores_gallery(self):
        from playwright.sync_api import sync_playwright
        owner=self
        def browser(base):
            with sync_playwright() as p:
                browser=p.chromium.launch(headless=True)
                try:
                    page=browser.new_page(viewport={'width':1440,'height':900})
                    page.goto(base+'/canvas',wait_until='networkidle')
                    original=page.evaluate("""() => {nodes=[{id:'root',type:'word',text:'blue cube',x:0,y:0},{id:'child',type:'word',text:'cloud',x:250,y:0}];edges=[{from:'root',to:'child',relation:'association'}];selected='root';draw();return JSON.stringify(nodes)}""")
                    page.once('dialog',lambda dialog:dialog.accept())
                    page.locator('#generateComposite').click()
                    page.wait_for_function('nodes.length===3',timeout=15000)
                    result=page.evaluate("""() => ({original:JSON.stringify(nodes.slice(0,2)),generated:nodes[2],edge:edges[1]})""")
                    owner.assertEqual(result['original'],original)
                    owner.assertEqual(len(result['generated']['image_assets']),1)
                    owner.assertEqual(result['edge'],{'from':'root','to':result['generated']['id'],'relation':'association'})
                    asset=result['generated']['image_assets'][0]
                    response=page.request.get(base+'/v1/board-assets/'+asset)
                    owner.assertEqual(response.status,200)
                    owner.assertTrue(response.body().startswith(b'\x89PNG'))
                finally:browser.close()
        fixture=mock.IndependentMockGeneration('test_generate_poll_fetch_png_over_actual_http')
        fixture.browser_hook=browser
        fixture.test_generate_poll_fetch_png_over_actual_http()
