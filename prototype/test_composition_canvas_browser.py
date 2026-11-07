"""Actual Chromium scene review UI; composition APIs are explicit browser fixtures."""
import os
import unittest
import threading
import tempfile
from pathlib import Path
from http.server import ThreadingHTTPServer
try:
    from playwright.async_api import async_playwright, expect
except ImportError:
    async_playwright=None

@unittest.skipUnless(async_playwright and os.getenv('STUDY_E2E_URL'),'Requires explicit Chromium browser run')
class CompositionCanvasBrowser(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import visual_memory,web_app
        self.tmp=tempfile.TemporaryDirectory(prefix='study-composition-ui-')
        self.old_db=visual_memory.DB
        visual_memory.DB=Path(self.tmp.name)/'isolated.sqlite3'
        self.server=ThreadingHTTPServer(('127.0.0.1',0),web_app.Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url='http://127.0.0.1:'+str(self.server.server_port)
        self.play=await async_playwright().start();self.browser=await self.play.chromium.launch()
        self.page=await self.browser.new_page(viewport={'width':1440,'height':900})
        self.rev={'revision_id':'rev-1','composition_id':'scene-1','version':1,'source_description':'A cup stands beside a table.','suggested_prompt':'Cup beside table','user_prompt':'','effective_prompt':'Cup beside table','parameters':{'seed':4,'width':512,'height':512,'steps':20},'selected_node_ids':['root','child'],'reference_images_transmitted':False,'jobs':[]}
        self.revisions=[self.rev];self.job=None;self.requests=[];self.auto_complete=True;self.unavailable=False
        async def route(r):
            request=r.request;path=request.url.split(self.url)[-1];body=request.post_data_json if request.method=='POST' else None
            self.requests.append((request.method,path,body))
            if path=='/v1/compositions' and request.method=='POST':value=self.rev
            elif path=='/v1/compositions':value={'items':[self.revisions[-1]]}
            elif path=='/v1/compositions/scene-1':value={'items':list(reversed(self.revisions))}
            elif path.endswith('/generate'):
                self.job={'job_id':'job-1','revision_id':self.revisions[-1]['revision_id'],'status':'unavailable' if self.unavailable else 'running','result':None};self.revisions[-1]['jobs']=[self.job.copy()];value=self.job
            elif path.endswith('/cancel'):
                self.job['status']='cancelled';self.job['result']={'error':{'message':'Cancelled by user'}};value=self.job
            elif '/jobs/' in path:
                if self.job is None:
                    await r.fulfill(status=404,json={'error':'Unknown fixture job'});return
                if self.job['status']=='unavailable' and not self.unavailable:self.job['status']='running'
                if self.auto_complete and self.job['status']=='running':self.job['status']='complete';self.job['result']={'outputs':[{'asset_id':'00000000-0000-4000-8000-000000000003','sha256':'a'*64}]}
                self.revisions[-1]['jobs']=[self.job.copy()];value=self.job
            elif '/revisions/' in path:
                value={**self.rev,'revision_id':'rev-2','version':2,'user_prompt':body['user_prompt'],'effective_prompt':body['user_prompt'],'parameters':body['parameters'],'jobs':[]};self.revisions.append(value)
            else:raise AssertionError(path)
            await r.fulfill(status=503 if isinstance(value,dict) and value.get('job_id') and value.get('status')=='unavailable' else 200,json=value)
        await self.page.route('**/v1/compositions**',route)
        await self.page.route('**/v1/board-assets/*',lambda r:r.fulfill(status=200,content_type='image/png',body=__import__('base64').b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=')))
        await self.page.goto(self.url+'/canvas')
        await self.page.wait_for_function('draftReady')
        await self.page.evaluate("""() => {nodes=[{id:'root',type:'word',text:'cup',x:0,y:0},{id:'child',type:'word',text:'table',x:230,y:0}];edges=[{from:'root',to:'child',relation:'association'}];selected='root';offset={x:20,y:20};draw()}""")

    async def asyncTearDown(self):
        try:
            await self.browser.close()
        finally:
            try:await self.play.stop()
            finally:
                self.server.shutdown();self.server.server_close();self.thread.join()
                import visual_memory
                visual_memory.DB=self.old_db;self.tmp.cleanup()

    async def test_review_edit_version_generate_reopen_without_duplicate(self):
        original=await self.page.evaluate('JSON.stringify({nodes,edges})')
        await self.page.locator('#generateComposite').click()
        await expect(self.page.locator('#sceneDescription')).to_have_text(self.rev['source_description'])
        await self.page.locator('#compositionPrompt').fill('My reviewed cup and table scene')
        await self.page.locator('#compositionSeed').fill('42')
        await self.page.locator('#compositionWidth').fill('768')
        await self.page.locator('#compositionHeight').fill('768')
        await self.page.locator('#compositionSteps').fill('28')
        self.assertTrue(await self.page.locator('#generateReviewedComposition').is_disabled())
        await self.page.locator('#saveCompositionRevision').click()
        await expect(self.page.locator('#compositionVersion')).to_contain_text('Версия 2')
        await self.page.locator('#generateReviewedComposition').click()
        await self.page.wait_for_function('nodes.length===3')
        self.assertEqual(self.revisions[-1]['parameters'],{'seed':42,'width':768,'height':768,'steps':28})
        self.assertEqual(self.revisions[-1]['effective_prompt'],'My reviewed cup and table scene')
        self.assertEqual(await self.page.evaluate('JSON.stringify({nodes:nodes.slice(0,2),edges:edges.slice(0,1)})'),original)
        self.assertEqual(await self.page.evaluate('nodes[2].generation_revision_id'),'rev-2')
        self.assertEqual(await self.page.evaluate('nodes[2].generation_provenance.sha256'),'a'*64)
        await self.page.wait_for_timeout(450)
        await self.page.reload();await self.page.wait_for_function('draftReady')
        await expect(self.page.locator('#compositionVersion')).to_contain_text('Версия 2')
        await expect(self.page.locator('#attachCompositionResult')).to_be_enabled()
        self.assertEqual(await self.page.evaluate('nodes.length'),3)
        await self.page.locator('#attachCompositionResult').click()
        self.assertEqual(await self.page.evaluate('nodes.length'),3)
        create=next(body for method,path,body in self.requests if method=='POST' and path=='/v1/compositions')
        self.assertEqual(create['roots'],['root']);self.assertEqual(create['direction'],'both')
        self.assertEqual(len(create['graph']['nodes']),2)

    async def test_cancel_and_history_reopen(self):
        self.auto_complete=False
        await self.page.locator('#generateComposite').click()
        await expect(self.page.locator('#compositionReview')).to_be_visible()
        await self.page.locator('#generateReviewedComposition').click()
        await expect(self.page.locator('#cancelCompositionJob')).to_be_enabled()
        await self.page.wait_for_timeout(450)
        await self.page.reload()
        await expect(self.page.locator('#cancelCompositionJob')).to_be_enabled()
        await self.page.locator('#cancelCompositionJob').click()
        await expect(self.page.locator('#generationStatus')).to_contain_text('cancelled')
        await self.page.locator('#refreshCompositions').click()
        await self.page.locator('#compositionHistory').select_option('scene-1')
        await expect(self.page.locator('#generationStatus')).to_contain_text('cancelled')
        self.assertEqual(await self.page.evaluate('nodes.length'),2)
        self.assertTrue(any(path.endswith('/cancel') for method,path,body in self.requests))

    async def test_unsaved_prompt_edits_restore_and_block_generation(self):
        await self.page.locator('#generateComposite').click()
        await expect(self.page.locator('#compositionReview')).to_be_visible()
        await self.page.locator('#compositionPrompt').fill('Unsaved prompt draft')
        await self.page.locator('#compositionSeed').fill('123')
        await self.page.wait_for_timeout(450)
        await self.page.reload()
        await expect(self.page.locator('#compositionPrompt')).to_have_value('Unsaved prompt draft')
        await expect(self.page.locator('#compositionSeed')).to_have_value('123')
        await expect(self.page.locator('#generateReviewedComposition')).to_be_disabled()

    async def test_unavailable_reservation_reloads_resumes_same_job_and_cancels(self):
        self.unavailable=True;self.auto_complete=False
        await self.page.locator('#generateComposite').click()
        await expect(self.page.locator('#compositionReview')).to_be_visible()
        await self.page.locator('#generateReviewedComposition').click()
        await expect(self.page.locator('#generationStatus')).to_contain_text('unavailable')
        await expect(self.page.locator('#generateReviewedComposition')).to_be_disabled()
        await expect(self.page.locator('#cancelCompositionJob')).to_be_enabled()
        await self.page.wait_for_timeout(450)
        await self.page.reload()
        await expect(self.page.locator('#generationStatus')).to_contain_text('unavailable')
        await expect(self.page.locator('#generateReviewedComposition')).to_be_disabled()
        self.unavailable=False
        await expect(self.page.locator('#generationStatus')).to_contain_text('running',timeout=4000)
        await self.page.locator('#cancelCompositionJob').click()
        await expect(self.page.locator('#generationStatus')).to_contain_text('cancelled')
        self.assertEqual(sum(path.endswith('/generate') for method,path,body in self.requests),1)
        self.assertTrue(any(path=='/v1/compositions/jobs/job-1/cancel' for method,path,body in self.requests))

    async def test_history_preview_does_not_change_unrelated_board_until_attach(self):
        self.job={'job_id':'history-job','revision_id':'rev-1','status':'complete','result':{'outputs':[{'asset_id':'00000000-0000-4000-8000-000000000003','sha256':'b'*64}]}}
        self.rev['jobs']=[self.job.copy()]
        original=await self.page.evaluate('JSON.stringify({nodes,edges})')
        await self.page.locator('#refreshCompositions').click()
        await self.page.locator('#compositionHistory').select_option('scene-1')
        await expect(self.page.locator('#attachCompositionResult')).to_be_enabled()
        self.assertEqual(await self.page.evaluate('JSON.stringify({nodes,edges})'),original)
        await self.page.locator('#attachCompositionResult').click()
        self.assertEqual(await self.page.evaluate('nodes.length'),3)

    async def test_dropped_generate_response_retries_synchronously_persisted_key(self):
        await self.page.locator('#generateComposite').click()
        await expect(self.page.locator('#compositionReview')).to_be_visible()
        sent=[]
        async def generate_route(route):
            body=route.request.post_data_json
            persisted=await self.page.evaluate('JSON.parse(localStorage.getItem(draftKey)).compositionUIState')
            self.assertEqual(persisted['request_id'],body['request_id'])
            self.assertEqual(persisted['request_revision_id'],'rev-1')
            sent.append(body['request_id'])
            if len(sent)==1:await route.abort('failed')
            else:await route.fulfill(json={'job_id':'job-recovered','revision_id':'rev-1','status':'cancelled','result':{'outputs':[]}})
        await self.page.route('**/v1/compositions/revisions/rev-1/generate',generate_route)
        await self.page.locator('#generateReviewedComposition').click()
        await expect(self.page.locator('#generationStatus')).to_contain_text('не подтверждён')
        await self.page.reload()
        await expect(self.page.locator('#resumeCompositionRequest')).to_be_visible()
        await self.page.locator('#resumeCompositionRequest').click()
        await expect(self.page.locator('#generationStatus')).to_contain_text('cancelled')
        self.assertEqual(len(sent),2)
        self.assertEqual(sent[0],sent[1])
