"""Real browser acceptance: STUDY_E2E_URL=http://127.0.0.1:8766."""
import os
import unittest
try:
    from playwright.async_api import async_playwright
except ImportError:
    async_playwright = None

URL = os.environ.get('STUDY_E2E_URL', '').rstrip('/')
ASSETS = ['00000000-0000-4000-8000-000000000001',
          '00000000-0000-4000-8000-000000000002']


@unittest.skipUnless(URL and async_playwright, 'Requires Playwright and STUDY_E2E_URL')
class CanvasUXBrowserTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.play = await async_playwright().start()
        self.browser = await self.play.chromium.launch()
        self.context = await self.browser.new_context(viewport={'width': 1440, 'height': 1000}, device_scale_factor=2)
        self.page = await self.context.new_page()
        self.page.set_default_timeout(5000)
        await self.page.goto(URL + '/canvas')
        await self.page.locator('.node.word').first.wait_for()

    async def asyncTearDown(self):
        await self.context.close()
        await self.browser.close()
        await self.play.stop()

    async def seed_gallery(self):
        await self.page.evaluate('''assets => {
            const n=nodes.find(n=>n.type==='word');
            attachImage(n,assets[0]);attachImage(n,assets[1]);select(n);
        }''', ASSETS)

    async def test_exact_hover_uses_rendered_bounds(self):
        result = await self.page.evaluate('''() => {
            const n=nodes.find(n=>n.type==='word');n.text='A very tall card '.repeat(35);
            scale=.7;offset={x:30,y:10};draw();renderTransform();
            const el=document.querySelector('.node.word'), r=el.getBoundingClientRect();
            return {inside:nodeAtCanvas(r.left+5,r.bottom-5)?.id===n.id,
                outside:nodeAtCanvas(r.right+3,r.top+3)?.id===n.id};
        }''')
        self.assertEqual(result, {'inside': True, 'outside': False})

    async def test_gallery_reorder_remove_undo_redo_and_preview(self):
        await self.seed_gallery()
        card = self.page.locator('.node.word').first
        await card.get_by_role('button', name='Переместить образ 2 влево', exact=True).click()
        self.assertEqual(await self.page.evaluate("nodes.find(n=>n.type==='word').image_assets"), ASSETS[::-1])
        await card.get_by_role('button', name='Удалить образ 1', exact=True).click()
        self.assertEqual(await self.page.evaluate("nodes.find(n=>n.type==='word').image_assets"), [ASSETS[0]])
        await self.page.locator('#undo').click()
        self.assertEqual(await self.page.evaluate("nodes.find(n=>n.type==='word').image_assets"), ASSETS[::-1])
        await self.page.locator('#redo').click()
        self.assertEqual(await card.count(), 1)
        await self.page.locator('#previewComposition').click()
        await self.page.locator('#compositionPreview[open]').wait_for()
        self.assertEqual(await self.page.locator('#compositionPreview img').count(), 1)
        self.assertFalse(await self.page.evaluate("nodes.some(n=>n.text.startsWith('Композиция:'))"))

    async def test_gallery_pointer_reorder(self):
        await self.seed_gallery()
        items = self.page.locator('.node.word .gallery-item')
        a, b = await items.nth(0).bounding_box(), await items.nth(1).bounding_box()
        await self.page.mouse.move(a['x']+12, a['y']+12)
        await self.page.mouse.down()
        await self.page.mouse.move(b['x']+12, b['y']+12, steps=12)
        await self.page.mouse.up()
        self.assertEqual(await self.page.evaluate("nodes.find(n=>n.type==='word').image_assets"), ASSETS[::-1])

    async def test_autosave_reload_restore_gallery_and_title(self):
        await self.seed_gallery()
        await self.page.locator('#title').fill('Recovery example')
        await self.page.wait_for_function("localStorage.getItem('study.canvas.draft.v1:new')?.includes('Recovery example')")
        await self.page.reload()
        await self.page.locator('#restoreDraft').click()
        self.assertEqual(await self.page.locator('#title').input_value(), 'Recovery example')
        self.assertEqual(await self.page.evaluate("nodes.find(n=>n.type==='word').image_assets"), ASSETS)

    async def test_corrupt_draft_not_overwritten(self):
        await self.page.evaluate("localStorage.setItem('study.canvas.draft.v1:new','{broken')")
        await self.page.reload()
        await self.page.locator('#draftRecovery').wait_for(state='visible')
        await self.page.locator('[data-add=note]').click()
        await self.page.wait_for_timeout(800)
        self.assertEqual(await self.page.evaluate("localStorage.getItem('study.canvas.draft.v1:new')"), '{broken')
        self.assertTrue(await self.page.locator('#restoreDraft').is_disabled())

    async def test_drag_escape_and_keyboard_move_history(self):
        card = self.page.locator('.node.word').first
        before = await self.page.evaluate("JSON.stringify({nodes,edges})")
        box = await card.bounding_box()
        await self.page.mouse.move(box['x']+25, box['y']+25)
        await self.page.mouse.down()
        await self.page.mouse.move(box['x']+120, box['y']+80, steps=10)
        await self.page.keyboard.press('Escape')
        await self.page.mouse.up()
        self.assertEqual(await self.page.evaluate("JSON.stringify({nodes,edges})"), before)
        await card.focus()
        x = await self.page.evaluate("nodes.find(n=>n.type==='word').x")
        await self.page.keyboard.press('ArrowRight')
        self.assertEqual(await self.page.evaluate("nodes.find(n=>n.type==='word').x"), x+10)
        await self.page.keyboard.press('Control+z')
        self.assertEqual(await self.page.evaluate("nodes.find(n=>n.type==='word').x"), x)

    async def test_split_hover_and_cancel(self):
        await self.page.goto(URL + '/workspace')
        board = self.page.frame_locator('iframe[src="/canvas"]')
        lab = self.page.frame_locator('iframe[src="/phonovision-3d"]')
        await lab.locator('#sphere').scroll_into_view_if_needed()
        src = await lab.locator('#sphere').bounding_box()
        dst = await board.locator('.node.word').first.bounding_box()
        await self.page.mouse.move(src['x']+30, src['y']+30)
        await self.page.mouse.down()
        await self.page.mouse.move(dst['x']+20, dst['y']+20, steps=16)
        await board.locator('.node.word.drop-target').wait_for()
        await self.page.keyboard.press('Escape')
        await self.page.mouse.up()
        self.assertEqual(await board.locator('.drop-target').count(), 0)
        self.assertEqual(await board.locator('.node.word img').count(), 0)

    async def test_mobile_keyboard_fit(self):
        await self.page.set_viewport_size({'width': 390, 'height': 844})
        await self.page.locator('#fit').click()
        stage = await self.page.locator('#stage').bounding_box()
        self.assertGreater(stage['width'], 180)
        self.assertEqual(await self.page.locator('#stage').get_attribute('tabindex'), '0')

    async def test_pointer_move_undo_redo(self):
        card=self.page.locator('.node.word').first
        box=await card.bounding_box()
        before=await self.page.evaluate("nodes.find(n=>n.type==='word').x")
        await self.page.mouse.move(box['x']+20,box['y']+20)
        await self.page.mouse.down()
        await self.page.mouse.move(box['x']+100,box['y']+40,steps=12)
        await self.page.mouse.up()
        after=await self.page.evaluate("nodes.find(n=>n.type==='word').x")
        self.assertGreater(after,before)
        await self.page.locator('#undo').click()
        self.assertEqual(await self.page.evaluate("nodes.find(n=>n.type==='word').x"),before)
        await self.page.locator('#redo').click()
        self.assertEqual(await self.page.evaluate("nodes.find(n=>n.type==='word').x"),after)

    async def test_cross_tab_conflict_preserves_other_draft(self):
        await self.seed_gallery()
        await self.page.wait_for_function("localStorage.getItem('study.canvas.draft.v1:new')!==null")
        other=await self.context.new_page()
        await other.goto(URL+'/canvas')
        await other.locator('#restoreDraft').click()
        await other.locator('#title').fill('Other tab version')
        await other.wait_for_function("localStorage.getItem('study.canvas.draft.v1:new')?.includes('Other tab version')")
        await self.page.locator('#draftRecovery').wait_for(state='visible')
        await self.page.locator('#title').fill('Conflicting local version')
        await self.page.wait_for_timeout(600)
        self.assertIn('Other tab version',await self.page.evaluate("localStorage.getItem('study.canvas.draft.v1:new')"))

    async def test_keyboard_transfer_both_directions(self):
        await self.page.goto(URL+'/workspace')
        board=self.page.frame_locator('iframe[src="/canvas"]')
        lab=self.page.frame_locator('iframe[src="/phonovision-3d"]')
        card=board.locator('.node.word').first
        await card.get_by_role('button',name='↗ В 3D Lab',exact=True).focus()
        await self.page.keyboard.press('Enter')
        await self.page.wait_for_timeout(150)
        self.assertIn('Tasse',await lab.locator('#imagePrompt').input_value())
        await card.focus()
        await self.page.keyboard.press('Enter')
        await lab.locator('#sendSphereToBoard').focus()
        await self.page.keyboard.press('Enter')
        await board.locator('.node.word img').first.wait_for(timeout=15000)

    async def test_saved_board_gallery_roundtrip(self):
        await self.seed_gallery()
        await self.page.locator('.node.word').first.get_by_role('button',name='Переместить образ 2 влево',exact=True).click()
        await self.page.locator('#title').fill('Gallery roundtrip test')
        await self.page.locator('#save').click()
        await self.page.wait_for_function('boardId!==null')
        bid=await self.page.evaluate('boardId')
        saved=await self.page.request.get(URL+'/v1/boards/'+bid)
        document=await saved.json()
        self.assertEqual(next(n['image_assets'] for n in document['nodes'] if n['type']=='word'),ASSETS[::-1])

    async def test_restore_copy_survives_reload(self):
        await self.seed_gallery()
        await self.page.locator('#title').fill('Copy recovery')
        await self.page.wait_for_function("localStorage.getItem('study.canvas.draft.v1:new')?.includes('Copy recovery')")
        original=await self.page.evaluate("localStorage.getItem('study.canvas.draft.v1:new')")
        await self.page.reload()
        await self.page.get_by_role('button',name='Восстановить как новую доску',exact=True).click()
        await self.page.locator('#title').fill('Recovered copy')
        await self.page.wait_for_timeout(650)
        self.assertEqual(await self.page.evaluate("localStorage.getItem('study.canvas.draft.v1:new')"),original)
        await self.page.reload()
        await self.page.locator('#restoreDraft').click()
        self.assertEqual(await self.page.locator('#title').input_value(),'Recovered copy')

    async def test_storage_quota_keeps_last_good_draft(self):
        await self.seed_gallery()
        await self.page.wait_for_function("localStorage.getItem('study.canvas.draft.v1:new')!==null")
        original=await self.page.evaluate("localStorage.getItem('study.canvas.draft.v1:new')")
        await self.page.evaluate("() => {Storage.prototype.setItem=function(){throw new DOMException('Full','QuotaExceededError')}}")
        await self.page.locator('#title').fill('Unsaved quota example')
        await self.page.wait_for_timeout(650)
        self.assertIn('не сохранён',await self.page.locator('#draftStatus').inner_text())
        self.assertEqual(await self.page.evaluate("localStorage.getItem('study.canvas.draft.v1:new')"),original)
        self.assertEqual(await self.page.locator('#title').input_value(),'Unsaved quota example')

    async def test_unlink_undo_and_image_add_history(self):
        await self.seed_gallery()
        await self.page.locator('#undo').click()
        self.assertEqual(await self.page.evaluate("nodes.find(n=>n.type==='word').image_assets"),ASSETS[:1])
        await self.page.locator('#redo').click()
        count=await self.page.evaluate('edges.length')
        await self.page.get_by_role('button',name='Убрать связи выбранной карточки',exact=True).click()
        self.assertEqual(await self.page.evaluate('edges.length'),0)
        await self.page.locator('#undo').click()
        self.assertEqual(await self.page.evaluate('edges.length'),count)

    async def test_image_card_drop_inside_board(self):
        await self.page.evaluate('''asset=>{
            const n=add('image','Movable image',420,190);n.asset_id=asset;draw();
        }''',ASSETS[0])
        source=await self.page.locator('.node.image').bounding_box()
        target=await self.page.locator('.node.word').first.bounding_box()
        await self.page.mouse.move(source['x']+20,source['y']+20)
        await self.page.mouse.down()
        await self.page.mouse.move(target['x']+20,target['y']+20,steps=15)
        await self.page.locator('.node.word.drop-target').wait_for()
        await self.page.mouse.up()
        self.assertEqual(await self.page.evaluate("nodes.find(n=>n.type==='word').image_assets"),ASSETS[:1])
        self.assertEqual(await self.page.locator('.node.image').count(),1)
        await self.page.locator('#undo').click()
        self.assertIsNone(await self.page.evaluate("nodes.find(n=>n.type==='word').image_assets||null"))

    async def test_split_image_card_drop_inside_board(self):
        await self.page.goto(URL+'/workspace')
        board=self.page.frame_locator('iframe[src="/canvas"]')
        await board.locator('body').evaluate('''(el,asset)=>{
            const n=add('image','Movable image',270,190);n.asset_id=asset;draw();
        }''',ASSETS[0])
        source=await board.locator('.node.image').bounding_box()
        target=await board.locator('.node.word').first.bounding_box()
        await self.page.mouse.move(source['x']+20,source['y']+20)
        await self.page.mouse.down()
        await self.page.mouse.move(target['x']+20,target['y']+20,steps=15)
        await board.locator('.node.word.drop-target').wait_for()
        await self.page.mouse.up()
        await board.locator('.node.word img').first.wait_for()
        self.assertEqual(await board.locator('body').evaluate("()=>nodes.find(n=>n.type==='word').image_assets"),ASSETS[:1])

    async def test_fit_measures_offscreen_tall_card(self):
        await self.page.evaluate('''()=>{
            nodes=[{id:crypto.randomUUID(),type:'note',text:'A very tall card '.repeat(100),x:3000,y:3000}];
            edges=[];draw();fitBoard();
        }''')
        stage=await self.page.locator('#stage').bounding_box()
        card=await self.page.locator('.node.note').bounding_box()
        self.assertGreaterEqual(card['y'],stage['y'])
        self.assertLessEqual(card['y']+card['height'],stage['y']+stage['height'])


if __name__ == '__main__':
    unittest.main()
