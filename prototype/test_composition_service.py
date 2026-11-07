"""Isolated durable service tests; fake loopback only, no models or user data."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from uuid import uuid4
from PIL import Image

import board_assets
import comfy_adapter
from composition_service import CompositionService


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {'STUDY_COMFYUI_ENABLED': '1', 'STUDY_COMFYUI_CHECKPOINT': 'reviewed.safetensors'})
        self.env.start(); self.addCleanup(self.env.stop)
        self.assets = patch.object(board_assets, 'ROOT', self.root/'assets')
        self.assets.start(); self.addCleanup(self.assets.stop)
        self.registry = comfy_adapter.JobRegistry(self.root/'queue.sqlite', start_workers=False)
        self.registry_patch = patch.object(comfy_adapter, 'registry', return_value=self.registry)
        self.registry_patch.start(); self.addCleanup(self.registry_patch.stop)
        self.addCleanup(self.registry.close)
        self.service = CompositionService(self.root/'compositions.sqlite')
        self.graph = {'nodes': [{'id': 'a', 'type': 'word', 'text': 'cat'}, {'id': 'b', 'type': 'action', 'text': 'runs'}],
                      'edges': [{'from': 'a', 'to': 'b', 'relation': 'action'}]}
        status, self.revision = self.service.dispatch('POST', '/v1/compositions', {'graph': self.graph, 'roots': ['a'], 'parameters': {'width': 768, 'height': 512, 'steps': 12, 'seed': 44}})
        self.assertEqual(status, 201)

    def generate(self, revision=None, key='click-1'):
        return self.service.generate((revision or self.revision)['revision_id'], key)

    def finish(self, job, state='complete'):
        remote = str(uuid4())
        with self.registry.lock:
            self.registry.db.execute('UPDATE jobs SET state=?,remote=?,images=?,error=? WHERE id=?',
                (state, remote, json.dumps([{'filename': 'result.png', 'subfolder': '', 'type': 'output'}]) if state == 'complete' else '[]', None, job['prompt_id']))
            self.registry.db.commit()
        return remote

    @staticmethod
    def png():
        data = BytesIO(); Image.new('RGB', (8, 8), 'red').save(data, format='PNG'); return data.getvalue()

    def test_revision_exact_parameters_and_bound_idempotency(self):
        job = self.generate()
        self.assertEqual(job['prompt_id_kind'], 'local')
        row = self.registry.db.execute('SELECT payload FROM jobs').fetchone()
        workflow = json.loads(row[0])['prompt']
        self.assertEqual(workflow['4']['inputs']['width'], 768)
        self.assertEqual(workflow['5']['inputs']['steps'], 12)
        revised = self.service.store.revise(self.revision['revision_id'], user_prompt='Reviewed cat prompt', parameters={'seed': 9})
        self.assertEqual(self.generate()['job_id'], job['job_id'])
        with self.assertRaises(ValueError): self.generate(revised)
        new = self.generate(revised, key='click-2')
        self.assertNotEqual(new['job_id'], job['job_id'])
        self.assertEqual(new['request']['prompt'], 'Reviewed cat prompt')
        self.assertEqual(job['request']['parameters']['seed'], 44)
        for bad in ({'width': 1024}, {'steps': True}):
            with self.assertRaises(ValueError): self.registry.submit('test', request_id=str(uuid4()), **bad)

    def test_restart_between_submit_and_record_has_one_adapter_job(self):
        original = self.service.store.record_job
        with patch.object(self.service.store, 'record_job', side_effect=RuntimeError('crash')):
            with self.assertRaises(RuntimeError): self.generate()
        restarted = CompositionService(self.root/'compositions.sqlite')
        job = restarted.generate(self.revision['revision_id'], 'click-1')
        self.assertEqual(len(self.registry.list()), 1)
        self.assertEqual(job['status'], 'queued')

    def test_cancel_and_history_survive_restart(self):
        job = self.generate()
        cancelled = self.service.status(job['job_id'], cancel=True)
        self.assertEqual(cancelled['result']['status'], 'cancelled')
        restarted = CompositionService(self.root/'compositions.sqlite')
        status, history = restarted.dispatch('GET', '/v1/compositions/'+self.revision['composition_id'])
        self.assertEqual(status, 200)
        self.assertEqual(history['items'][0]['jobs'][0]['status'], 'cancelled')
        self.assertEqual(restarted.status(job['job_id'])['result'], cancelled['result'])
        self.assertEqual(restarted.dispatch('GET', '/v1/compositions')[1]['items'][0]['revision_id'], self.revision['revision_id'])

    def test_output_saved_once_hash_and_append_only(self):
        job = self.generate(); remote = self.finish(job)
        with patch.object(comfy_adapter, 'image_bytes', return_value=self.png()) as fetch:
            result = self.service.status(job['job_id'])
            restarted = CompositionService(self.root/'compositions.sqlite')
            self.assertEqual(restarted.status(job['job_id'])['result'], result['result'])
            self.assertEqual(fetch.call_count, 1)
            another = self.generate(key='click-2'); self.finish(another)
            result2 = self.service.status(another['job_id'])
        self.assertEqual(result['result']['outputs'], result2['result']['outputs'])
        self.assertEqual(len(list(board_assets.ROOT.glob('*.png'))), 1)
        import hashlib
        output = result['result']['outputs'][0]
        self.assertEqual(hashlib.sha256(board_assets.read(output['asset_id'])).hexdigest(), output['sha256'])
        with self.assertRaises(ValueError): self.service.store.record_result(job['job_id'], status='failed', error='later')

    def test_immutable_asset_id(self):
        aid = str(uuid4())
        self.assertEqual(board_assets.store(self.png(), asset_id=aid), board_assets.store(self.png(), asset_id=aid))
        other = BytesIO(); Image.new('RGB', (8, 8), 'blue').save(other, format='PNG')
        with self.assertRaises(ValueError): board_assets.store(other.getvalue(), asset_id=aid)

    def test_unavailable_reservation_and_route_rejections(self):
        with patch.dict(os.environ, {'STUDY_COMFYUI_ENABLED': '0'}):
            job = self.generate(); self.assertEqual(job['status'], 'unavailable')
        self.assertEqual(self.service.status(job['job_id'])['status'], 'queued')
        self.assertEqual(self.service.dispatch('POST', '/v1/compositions/revisions/'+self.revision['revision_id']+'/generate', {'prompt': 'unreviewed'})[0], 400)
        self.assertEqual(self.service.dispatch('GET', '/v1/compositions/jobs/missing')[0], 404)
        self.assertIsNone(self.service.dispatch('GET', '/other'))

    def test_cancel_unavailable_reservation_does_not_enqueue_later(self):
        with patch.dict(os.environ, {'STUDY_COMFYUI_ENABLED': '0'}):
            job = self.generate()
        cancelled = self.service.status(job['job_id'], cancel=True)
        self.assertEqual(cancelled['status'], 'cancelled')
        restarted = CompositionService(self.root/'compositions.sqlite')
        self.assertEqual(restarted.status(job['job_id'])['status'], 'cancelled')
        self.assertEqual(self.registry.list(), [])

    def test_terminal_failures_and_queue_restart_are_durable(self):
        for index, state in enumerate(('failed', 'timed_out', 'interrupted')):
            job = self.generate(key='failure-'+str(index))
            self.finish(job, state)
            result = self.service.status(job['job_id'])
            self.assertEqual(result['result']['status'], state)
            self.assertEqual(result['result']['outputs'], [])
        job = self.generate(key='running-restart')
        self.finish(job, 'running')
        # A separate reopened adapter marks running work interrupted truthfully.
        reopened = comfy_adapter.JobRegistry(self.root/'queue.sqlite', start_workers=False)
        try:
            with patch.object(comfy_adapter, 'registry', return_value=reopened):
                self.assertEqual(self.service.status(job['job_id'])['status'], 'interrupted')
        finally: reopened.close()

    def test_asset_crash_recovery_and_http_conflict(self):
        original = board_assets.store
        calls = []
        def save_then_crash(*args, **kwargs):
            result = original(*args, **kwargs); calls.append(result); raise RuntimeError('crash after bytes saved')
        with patch.object(board_assets, 'store', side_effect=save_then_crash):
            with self.assertRaises(RuntimeError): self.service._save_image(self.png())
        saved = self.service._save_image(self.png())
        self.assertEqual(saved['asset_id'], calls[0]['asset_id'])
        self.assertEqual(len(list(board_assets.ROOT.glob('*.png'))), 1)
        self.generate()
        revised = self.service.store.revise(self.revision['revision_id'], user_prompt='new review')
        status, _ = self.service.dispatch('POST', '/v1/compositions/revisions/'+revised['revision_id']+'/generate', {'request_id': 'click-1'})
        self.assertEqual(status, 409)

    def test_fake_loopback_generation_end_to_end(self):
        png = self.png(); remote = str(uuid4()); captured = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                captured.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                body = json.dumps({'prompt_id': remote}).encode(); self.send_response(200); self.end_headers(); self.wfile.write(body)
            def do_GET(self):
                if self.path.startswith('/history/'):
                    body = json.dumps({remote: {'outputs': {'7': {'images': [{'filename': 'result.png', 'subfolder': '', 'type': 'output'}]}}, 'status': {'completed': True}}}).encode()
                else: body = png
                self.send_response(200); self.end_headers(); self.wfile.write(body)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        with patch.object(comfy_adapter, 'BASE', 'http://127.0.0.1:'+str(server.server_port)):
            worker = threading.Thread(target=self.registry._worker, daemon=True); self.registry.threads.append(worker); worker.start()
            job = self.generate()
            deadline = time.monotonic()+4
            while time.monotonic() < deadline:
                result = self.service.status(job['job_id'])
                if result['status'] == 'complete': break
                time.sleep(.02)
            self.assertEqual(result['status'], 'complete')
            self.assertEqual(result['upstream_prompt_id'], remote)
            self.assertNotEqual(result['prompt_id'], remote)
            self.assertEqual(captured[0]['prompt']['2']['inputs']['text'], self.revision['effective_prompt'])
            self.assertEqual(len(result['result']['outputs']), 1)
            restarted = CompositionService(self.root/'compositions.sqlite')
            self.assertEqual(restarted.status(job['job_id'])['upstream_prompt_id'], remote)

if __name__ == '__main__': unittest.main()
