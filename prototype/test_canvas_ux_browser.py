"""Browser UX regressions. Requires a disposable Study server via STUDY_E2E_URL."""
import unittest
import test_browser_gestures as baseline

class CanvasUXBrowserTests(baseline.GestureBrowserTests):
    # Do not inherit the five baseline tests into this suite.
    test_card_drag_to_lab = None
    test_sphere_to_existing_word_card = None
    test_gallery_and_composition = None
    test_toggle_split_view = None
    test_fling_detaches_outward_only = None

    async def test_dom_hit_area_and_gallery_draft(self):
        board = self.page.frame_locator('iframe[src="/canvas"]')
        await board.locator('body').evaluate('''() => {
          nodes=[{id:'test',type:'word',text:'Tall card '.repeat(12),x:0,y:0,
            image_assets:['00000000-0000-4000-8000-000000000001','00000000-0000-4000-8000-000000000002']}];edges=[];
          offset={x:20,y:20};scale=.8;renderTransform();
        }''')
        result = await board.locator('.node').evaluate('''el => {const r=el.getBoundingClientRect();return [nodeAtCanvas(r.left+10,r.bottom-5)?.id,nodeAtCanvas(r.right+3,r.top+5)?.id||null]}''')
        self.assertEqual(result, ['test', None])
        # The parent is the trusted sender; use its actual bridge instead of a synthetic origin.
        await self.page.evaluate("""() => {const f=document.querySelector('iframe[src="/canvas"]');const card=f.contentDocument.querySelector('.node');const r=card.getBoundingClientRect();f.contentWindow.postMessage({kind:'study-drag-hover',active:true,clientX:r.left+10,clientY:r.bottom-5},location.origin)}""")
        await board.locator('.node.drop-target').wait_for()
        await board.get_by_role('button', name='Образ 2: раньше', exact=True).click()
        await board.get_by_role('button', name='Образ 2: удалить', exact=True).click()
        await board.locator('#title').fill('UX isolated browser board')
        await board.locator('#save').click()
        await self.page.wait_for_timeout(450)
        saved = await board.locator('body').evaluate("async()=>{const r=await fetch('/v1/boards/'+boardId);return (await r.json()).nodes[0].image_assets}")
        self.assertEqual(saved, ['00000000-0000-4000-8000-000000000002'])
        await self.page.reload()
        board = self.page.frame_locator('iframe[src="/canvas"]')
        await board.locator('.node').first.wait_for()
        self.assertEqual(await board.locator('body').evaluate('nodes[0].image_assets'), ['00000000-0000-4000-8000-000000000002'])

    async def test_escape_cancels_real_drag(self):
        board = self.page.frame_locator('iframe[src="/canvas"]')
        src = await board.locator('.node.word').first.bounding_box()
        before = await board.locator('body').evaluate('JSON.stringify({nodes,edges})')
        await self.page.mouse.move(src['x']+25, src['y']+25)
        await self.page.mouse.down()
        await self.page.locator('.drag-hint').wait_for()
        await self.page.keyboard.press('Escape')
        await self.page.mouse.up()
        self.assertEqual(await self.page.locator('.drag-hint').count(), 0)
        # Transient drag timing is diagnostic only.
        after = await board.locator('body').evaluate('JSON.stringify({nodes,edges},(k,v)=>k==="_dragStarted"?undefined:v)')
        import json
        old=json.loads(before)
        for n in old['nodes']: n.pop('_dragStarted',None)
        self.assertEqual(json.loads(after), old)
        self.assertIn('отменён', await self.page.locator('#transferStatus').inner_text())

    async def test_mobile_dpi_hit_testing(self):
        context = await self.browser.new_context(viewport={'width':390,'height':844}, device_scale_factor=2, is_mobile=True, has_touch=True)
        try:
            page = await context.new_page()
            await page.goto(__import__('test_browser_gestures').URL+'/canvas')
            await page.locator('.node').first.wait_for()
            self.assertTrue(await page.locator('body').evaluate('''() => {nodes=[{id:'mobile',type:'word',text:'Mobile',x:0,y:0}];offset={x:5,y:5};scale=.6;renderTransform();const r=document.querySelector('.node').getBoundingClientRect();return nodeAtCanvas(r.left+3,r.top+3)?.id==='mobile'}'''))
        finally:
            await context.close()


    async def test_keyboard_move_and_transfer_confirmation(self):
        board = self.page.frame_locator('iframe[src="/canvas"]')
        lab = self.page.frame_locator('iframe[src="/phonovision-3d"]')
        card = board.locator('.node.word').first
        before = await card.evaluate("el=>nodes.find(n=>n.id===el.dataset.id).x")
        await card.focus()
        await self.page.keyboard.press('ArrowRight')
        self.assertEqual(await board.locator('.node.word').first.evaluate("el=>nodes.find(n=>n.id===el.dataset.id).x"), before+10)
        await board.locator('.node.word').first.get_by_role('button',name='↗ В 3D Lab').focus()
        await self.page.keyboard.press('Enter')
        await self.page.wait_for_timeout(100)
        self.assertIn('Tasse',await lab.locator('#imagePrompt').input_value())
        self.assertIn('приняты',await self.page.locator('#transferStatus').inner_text())

    async def test_lab_reports_terminal_generation_errors(self):
        lab = self.page.frame_locator('iframe[src="/phonovision-3d"]')
        await self.page.route('**/v1/comfy/generate', lambda route: route.fulfill(json={'status':'queued','prompt_id':'fixture-job'}))
        await lab.locator('#imagePrompt').fill('A cup')
        for state in ('failed','cancelled','timed_out','interrupted'):
            await self.page.route('**/v1/comfy/jobs/fixture-job', lambda route, request, state=state: route.fulfill(json={'status':state,'error':{'message':'Fixture '+state}}))
            await lab.locator('#comfyGenerate').click()
            await self.page.wait_for_timeout(2200)
            self.assertIn('Fixture '+state,await lab.locator('#comfyStatus').inner_text())
            await self.page.unroute('**/v1/comfy/jobs/fixture-job')

