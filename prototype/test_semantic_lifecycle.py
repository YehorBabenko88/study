"""Run B's lifecycle through an actual A registry and loopback HTTP transport.

Set STUDY_SEMANTIC_ADAPTER_FILE to A's exact comfy_adapter.py. The base branch
adapter lacks JobRegistry/all four parameters; this test reports an explicit skip
there. The server below is a protocol fixture, never a diffusion inference engine.
"""
import importlib.util
import inspect
import copy
import json
import os
import tempfile
import threading
import time
import unittest
from io import BytesIO
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import semantic_composer as sc
import semantic_composer_example as example


def load_adapter():
    path = os.environ.get('STUDY_SEMANTIC_ADAPTER_FILE')
    if not path:
        import comfy_adapter
        return comfy_adapter
    spec = importlib.util.spec_from_file_location('semantic_lifecycle_adapter', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.adapter = load_adapter()
        if not hasattr(self.adapter, 'JobRegistry'):
            self.skipTest('Select A adapter via STUDY_SEMANTIC_ADAPTER_FILE (base has no registry)')
        params = inspect.signature(self.adapter.JobRegistry.submit).parameters
        if not {'seed', 'width', 'height', 'steps', 'request_id'} <= set(params):
            self.fail('A adapter cannot consume the complete agreed v1 parameter contract')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name)
        self.store = sc.CompositionStore(self.data / 'composer.sqlite')
        self.posts = []
        self.pending = False
        self.upstream_id = str(uuid4())
        # Generate a valid PNG including CRCs; A validates downloaded bytes.
        from PIL import Image
        png = BytesIO()
        Image.new('RGB', (2, 2), 'green').save(png, format='PNG')
        self.png = png.getvalue()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, payload, content_type='application/json'):
                data = json.dumps(payload).encode() if content_type == 'application/json' else payload
                self.send_response(200)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                if self.path != '/prompt':
                    self.send_error(404)
                    return
                owner.posts.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                self.reply({'prompt_id': owner.upstream_id})

            def do_GET(self):
                if self.path == '/history/' + owner.upstream_id:
                    self.reply({} if owner.pending else {owner.upstream_id: {'outputs': {'7': {'images': [
                        {'filename': 'Study_fixture.png', 'subfolder': '', 'type': 'output'}]}}}})
                elif self.path.startswith('/view?'):
                    self.reply(owner.png, 'image/png')
                else:
                    self.send_error(404)

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.base = patch.object(self.adapter, 'BASE', f'http://127.0.0.1:{self.server.server_port}')
        self.base.start()
        self.addCleanup(self.base.stop)
        self.env = patch.dict(os.environ, {'STUDY_COMFYUI_CHECKPOINT': 'fixture.safetensors',
                                           'STUDY_COMFYUI_ENABLED': '1'})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.registry = self.adapter.JobRegistry(self.data / 'jobs.sqlite', poll=.01, timeout=3)
        self.addCleanup(lambda: self.registry.close())
        self.registry_patch = patch.object(self.adapter, '_registry', self.registry)
        self.registry_patch.start()
        self.addCleanup(self.registry_patch.stop)

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def wait(self, job):
        end = time.monotonic() + 5
        while time.monotonic() < end:
            result = self.registry.result(job['prompt_id'])
            if result['status'] in self.adapter.TERMINAL:
                return result
            time.sleep(.01)
        self.fail('actual A worker failed to reach a terminal state')

    def test_create_edit_generate_download_save_and_restart(self):
        cases = json.loads(Path(__file__).with_name('semantic_composer_cards.json').read_text(encoding='utf-8'))
        for case in cases:
            with self.subTest(cards=case['name']):
                original = self.store.create(case['graph'], case['roots'])
                revision = self.store.revise(original['revision_id'],
                                            user_prompt='A giant cup rides a tiny train.',
                                            parameters={'seed': 9007199254740991, 'width': 768,
                                                        'height': 512, 'steps': 35})
                job = example.submit_revision(self.store, self.registry, revision['revision_id'])
                self.assertEqual(self.wait(job)['status'], 'complete')
                self.assertEqual(self.registry.result(job['prompt_id'])['request_id'], job['request_id'])
                self.assertNotEqual(job['prompt_id'], self.upstream_id)
                posted = self.posts[-1]['prompt']
                self.assertEqual(posted['2']['inputs']['text'], 'A giant cup rides a tiny train.')
                self.assertEqual(posted['5']['inputs']['seed'], 9007199254740991)
                self.assertEqual(posted['5']['inputs']['steps'], 35)
                self.assertEqual(posted['4']['inputs']['width'], 768)
                self.assertEqual(posted['4']['inputs']['height'], 512)
                result = example.collect_result(self.store, self.adapter, job,
                                                example.DirectoryAssets(self.data / 'assets').save)
                self.assertEqual(result['status'], 'complete')
                asset = self.data / 'assets' / (result['outputs'][0]['asset_id'] + '.png')
                self.assertEqual(asset.read_bytes(), self.png)
                import hashlib
                self.assertEqual(result['outputs'][0]['sha256'], hashlib.sha256(self.png).hexdigest())
                reopened = sc.CompositionStore(self.data / 'composer.sqlite')
                self.assertEqual(reopened.find_job(job['prompt_id'], backend='study_local'), job)
                self.assertEqual(reopened.job_history(revision['revision_id'])[0]['result'], result)
                self.assertEqual(len(reopened.history(original['composition_id'])), 2)
                self.assertEqual(json.loads(reopened.get(original['revision_id'])['source_graph_json']), case['graph'])
                self.assertEqual(reopened.recovery_state(), {'unlinked_submissions': [], 'unfinished_jobs': []})
                # Re-collecting is read-only and creates no second output asset.
                self.assertEqual(example.collect_result(reopened, self.adapter, job,
                    example.DirectoryAssets(self.data / 'assets').save), result)
        self.assertEqual(len(self.posts), 2)
        self.assertEqual(len(list((self.data / 'assets').glob('*.png'))), 2)

    def test_acceptance_before_bind_recovers_same_local_job_without_resubmit(self):
        source = {'nodes': [{'id': 'w', 'type': 'word', 'text': 'Tasse'}], 'edges': []}
        revision = self.store.create(source, ['w'], parameters={'width': 768, 'steps': 29})
        intent = self.store.prepare_submission(revision['revision_id'])
        request = intent['request']
        accepted = self.registry.submit(request['prompt'], **request['parameters'], request_id=intent['request_id'])
        self.wait(accepted)
        # Crash window: A accepted it, B did not yet persist the job link.
        self.registry.close()
        self.registry = self.adapter.JobRegistry(self.data / 'jobs.sqlite', poll=.01, timeout=3)
        self.adapter._registry = self.registry
        reopened = sc.CompositionStore(self.data / 'composer.sqlite')
        pending = reopened.recovery_state()['unlinked_submissions'][0]
        recovered = example.resume_submission(reopened, self.registry, pending)
        self.assertEqual(recovered['prompt_id'], accepted['prompt_id'])
        self.assertEqual(self.registry.result(recovered['prompt_id'])['status'], 'complete')
        self.assertEqual(len(self.posts), 1)
        self.assertEqual(len(self.registry.list()), 1)
        result = example.collect_result(reopened, self.adapter, recovered,
                                        example.DirectoryAssets(self.data / 'assets').save)
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(reopened.recovery_state(), {'unlinked_submissions': [], 'unfinished_jobs': []})

    def test_final_v1_consumer_rejects_parameter_reuse_and_image_mode(self):
        revision = self.store.create({'nodes': [{'id': 'w', 'type': 'word', 'text': 'cup'}]}, ['w'],
                                     parameters={'seed': 876, 'width': 768, 'height': 768, 'steps': 28})
        intent = self.store.prepare_submission(revision['revision_id'])
        accepted = self.adapter.consume_generation_request(intent['request'], request_id=intent['request_id'])
        self.wait(accepted)
        job = example.resume_submission(self.store, self.adapter, intent)
        self.assertEqual(job['prompt_id'], accepted['prompt_id'])
        changed = copy.deepcopy(intent['request'])
        changed['parameters']['steps'] = 27
        with self.assertRaises(ValueError):
            self.adapter.consume_generation_request(changed, request_id=intent['request_id'])
        changed['mode'] = 'image_conditioned'
        with self.assertRaises(ValueError):
            self.adapter.consume_generation_request(changed, request_id='must-not-generate')
        posted = self.posts[0]['prompt']
        self.assertEqual((posted['5']['inputs']['seed'], posted['4']['inputs']['width'],
                          posted['4']['inputs']['height'], posted['5']['inputs']['steps']),
                         (876, 768, 768, 28))
        self.assertEqual(len(self.posts), 1)
        self.assertEqual(len(self.registry.list()), 1)

    def test_running_job_restart_is_recorded_interrupted_without_new_generation(self):
        self.pending = True
        revision = self.store.create({'nodes': [{'id': 'w', 'type': 'word', 'text': 'cup'}]}, ['w'])
        job = example.submit_revision(self.store, self.registry, revision['revision_id'])
        end = time.monotonic() + 3
        while not self.posts and time.monotonic() < end:
            time.sleep(.01)
        self.assertEqual(len(self.posts), 1)
        self.assertEqual(self.registry.result(job['prompt_id'])['status'], 'running')
        self.registry.close()
        self.registry = self.adapter.JobRegistry(self.data / 'jobs.sqlite', poll=.01, timeout=3)
        self.adapter._registry = self.registry
        reopened = sc.CompositionStore(self.data / 'composer.sqlite')
        recovered = reopened.recovery_state()['unfinished_jobs'][0]
        result = example.collect_result(reopened, self.adapter, recovered,
                                        example.DirectoryAssets(self.data / 'assets').save)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(json.loads(result['error'])['backend_status'], 'interrupted')
        self.assertEqual(len(self.posts), 1)
        self.assertEqual(reopened.recovery_state()['unfinished_jobs'], [])


if __name__ == '__main__':
    unittest.main()
