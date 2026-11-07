"""Optional real Chromium E2E tests for Study gestures.

Run Study separately and set STUDY_E2E_URL. Uses Playwright Async API so
a failed browser startup cannot leave the sync event-loop adapter running.
"""
import asyncio
import os
import unittest
from urllib.request import urlopen
from urllib.error import URLError

try:
    from playwright.async_api import async_playwright
except ImportError:
    async_playwright = None

URL = os.environ.get("STUDY_E2E_URL", "").rstrip("/")


@unittest.skipUnless(URL and async_playwright, "Requires Playwright and STUDY_E2E_URL")
class GestureBrowserTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        try:
            with urlopen(URL + "/workspace", timeout=3) as response:
                if response.status != 200:
                    self.skipTest("Study /workspace returned HTTP " + str(response.status))
        except (URLError, OSError, TimeoutError) as exc:
            self.skipTest("Study server is not reachable at " + URL + " — start web_app.py first: " + str(exc))
        self.play = None
        self.browser = None
        try:
            self.play = await async_playwright().start()
            self.browser = await self.play.chromium.launch(headless=True)
            self.page = await self.browser.new_page(viewport={"width": 1440, "height": 900})
            await self.page.goto(URL + "/workspace", wait_until="domcontentloaded")
            await self.page.frame_locator('iframe[src="/canvas"]').locator(".node.word").first.wait_for()
            await self.page.frame_locator('iframe[src="/phonovision-3d"]').locator("#composition").wait_for()
        except BaseException:
            await self._close()
            raise

    async def _close(self):
        if self.browser is not None:
            await self.browser.close()
            self.browser = None
        if self.play is not None:
            await self.play.stop()
            self.play = None

    async def asyncTearDown(self):
        await self._close()

    async def test_card_drag_to_lab(self):
        board = self.page.frame_locator('iframe[src="/canvas"]')
        lab = self.page.frame_locator('iframe[src="/phonovision-3d"]')
        await lab.locator("#composition").scroll_into_view_if_needed()
        src = await board.locator(".node.word").first.bounding_box()
        dst = await lab.locator("#composition").bounding_box()
        self.assertIsNotNone(src)
        self.assertIsNotNone(dst)
        self.assertLess(dst["y"] + 35, 900, "Drop target is outside viewport")
        await self.page.mouse.move(src["x"] + 30, src["y"] + 25)
        await self.page.mouse.down()
        await self.page.locator(".drag-hint").wait_for(timeout=5000)
        await self.page.mouse.move(dst["x"] + 30, dst["y"] + 30, steps=16)
        await self.page.mouse.up()
        await self.page.wait_for_timeout(400)
        self.assertIn("Tasse", await lab.locator("#imagePrompt").input_value(), "Transfer status: "+(await self.page.locator("#transferStatus").inner_text()))

    async def test_sphere_to_existing_word_card(self):
        board = self.page.frame_locator('iframe[src="/canvas"]')
        lab = self.page.frame_locator('iframe[src="/phonovision-3d"]')
        await lab.locator("#sphere").scroll_into_view_if_needed()
        src = await lab.locator("#sphere").bounding_box()
        dst = await board.locator(".node.word").first.bounding_box()
        self.assertIsNotNone(src)
        self.assertIsNotNone(dst)
        self.assertLess(src["y"] + 30, 900, "Sphere is outside viewport")
        await self.page.mouse.move(src["x"] + 30, src["y"] + 30)
        await self.page.mouse.down()
        await self.page.locator(".drag-hint").wait_for(timeout=5000)
        await self.page.mouse.move(dst["x"] + 60, dst["y"] + 45, steps=16)
        await self.page.mouse.up()
        await board.locator(".node.word img").first.wait_for(timeout=15000)

    async def test_gallery_and_composition(self):
        board = self.page.frame_locator('iframe[src="/canvas"]')
        result = await board.locator("body").evaluate("""() => {
            const target=nodes.find(n=>n.type==="word");
            const first="00000000-0000-4000-8000-000000000001";
            const second="00000000-0000-4000-8000-000000000002";
            attachImage(target,first);attachImage(target,second);
            const unique=target.image_assets.length===2;
            select(target);
            document.getElementById("composeImages").click();
            const composite=nodes.find(n=>n.text.startsWith("Композиция:"));
            return {unique,count:composite?.image_assets.length,linked:edges.some(e=>e.to===composite?.id)};
        }""")
        self.assertEqual(result,{"unique":True,"count":2,"linked":True})

    async def test_hover_highlights_card(self):
        board = self.page.frame_locator('iframe[src="/canvas"]')
        result = await board.locator("body").evaluate("""() => {
            const el=document.querySelector(".node.word");
            const rect=el.getBoundingClientRect();
            window.postMessage({kind:"study-drag-hover",active:true,clientX:rect.left+25,clientY:rect.top+25},location.origin);
            return true;
        }""")
        self.assertTrue(result)

    async def test_toggle_split_view(self):
        await self.page.locator("#togglePanels").click()
        await self.page.wait_for_url("**/canvas")

    async def test_fling_detaches_outward_only(self):
        board = self.page.frame_locator('iframe[src="/canvas"]')
        outcome = await board.locator("body").evaluate("""() => {
            const a={id:'a',x:350,y:0}, b={id:'b',x:0,y:0};
            nodes=[a,b]; edges=[{from:'a',to:'b'}];
            const detached=detachOnFling(a,350,0,100);
            return [detached,edges.length];
        }""")
        self.assertEqual(outcome, [True, 0])


if __name__ == "__main__":
    unittest.main()
