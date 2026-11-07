"""Real Chromium UI against real Study HTTP and explicitly fake local Comfy."""
import os
import unittest
import tempfile
from unittest.mock import patch
import composition_service
import comfy_adapter
import test_independent_mock_generation as mock

@unittest.skipUnless(hasattr(comfy_adapter,'JobRegistry') and os.getenv('STUDY_E2E_URL'), 'Requires registry, Playwright, and explicit browser run')
class IndependentGenerationBrowser(unittest.TestCase):
    def test_reviewed_revision_generate_preserves_graph_and_stores_gallery(self):
        from playwright.sync_api import sync_playwright
        owner=self
        def browser(base):
            with sync_playwright() as p:
                browser=p.chromium.launch(headless=True)
                try:
                    page=browser.new_page(viewport={'width':1440,'height':900})
                    page.goto(base+'/canvas',wait_until='networkidle')
                    original=page.evaluate("""() => {nodes=[{id:'root',type:'word',text:'blue cube',x:0,y:0},{id:'child',type:'word',text:'cloud',x:250,y:0}];edges=[{from:'root',to:'child',relation:'association'}];selected='root';draw();return JSON.stringify(nodes)}""")
                    page.locator('#generateComposite').click()
                    page.locator('#compositionReview').wait_for(state='visible')
                    page.locator('#compositionPrompt').fill('A blue cube floating beside a cloud, one scene')
                    page.locator('#saveCompositionRevision').click()
                    page.wait_for_function("document.getElementById('compositionVersion').textContent.includes('Версия 2')")
                    page.locator('#generateReviewedComposition').click()
                    page.wait_for_function('nodes.length===3',timeout=15000)
                    result=page.evaluate("""() => ({original:JSON.stringify(nodes.slice(0,2)),generated:nodes[2],generatedEdges:edges.slice(1)})""")
                    owner.assertEqual(result['original'],original)
                    owner.assertEqual(len(result['generated']['image_assets']),1)
                    owner.assertEqual({edge['from'] for edge in result['generatedEdges']},{'root','child'})
                    owner.assertTrue(all(edge['to']==result['generated']['id'] and edge['relation']=='association' for edge in result['generatedEdges']))
                    asset=result['generated']['image_assets'][0]
                    response=page.request.get(base+'/v1/board-assets/'+asset)
                    owner.assertEqual(response.status,200)
                    owner.assertTrue(response.body().startswith(b'\x89PNG'))
                    saved=page.request.get(base+'/v1/compositions/'+result['generated']['composition_id']).json()['items']
                    reviewed=next(v for v in saved if v['revision_id']==result['generated']['generation_revision_id'])
                    owner.assertEqual(reviewed['effective_prompt'],'A blue cube floating beside a cloud, one scene')
                    owner.assertEqual(reviewed['version'],2)
                    page.wait_for_timeout(400)
                    page.reload(wait_until='networkidle')
                    page.locator('#attachCompositionResult').wait_for()
                    owner.assertEqual(page.evaluate('nodes.length'),3)
                finally:browser.close()
        fixture=mock.IndependentMockGeneration('test_generate_poll_fetch_png_over_actual_http')
        fixture.browser_hook=browser
        with tempfile.TemporaryDirectory(prefix='study-real-canvas-') as tmp, patch.object(composition_service,'_service',composition_service.CompositionService(tmp+'/compositions.sqlite')):
            fixture.test_generate_poll_fetch_png_over_actual_http()
