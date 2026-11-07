"""Installer validation uses real local HTTP and explicitly fake Comfy, never inference."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from uuid import uuid4
from PIL import Image

PATH = Path(__file__).resolve().parents[1] / 'deploy/ls5/comfy_smoke.py'


def module():
    spec = importlib.util.spec_from_file_location('installer_smoke_probe', PATH)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result


class InstallerSmokeTests(unittest.TestCase):
    def setUp(self):
        self.probe = module()
        self.tmp = tempfile.TemporaryDirectory(prefix='study-installer-smoke-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.remote = str(uuid4()); self.failed = False; self.posts = 0
        output = io.BytesIO(); Image.new('RGB', (5, 4), 'blue').save(output, format='PNG')
        self.png = output.getvalue(); owner = self
        class Fake(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def send(self, value):
                raw = value if isinstance(value, bytes) else json.dumps(value).encode()
                self.send_response(200); self.send_header('Content-Length', str(len(raw)))
                self.end_headers(); self.wfile.write(raw)
            def do_POST(self):
                owner.posts += 1
                payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                owner.workflow = payload['prompt']
                self.send({'prompt_id': owner.remote})
            def do_GET(self):
                if self.path == '/system_stats': return self.send({'devices': [{'name': 'explicit fake CPU'}]})
                if self.path.startswith('/view?'): return self.send(owner.png)
                self.send({owner.remote: {'status': {'status_str': 'error' if owner.failed else 'success', 'completed': True},
                    'outputs': {'7': {'images': [{'filename': 'test.png', 'subfolder': '', 'type': 'output'}]}}}})
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Fake)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.addCleanup(self.thread.join); self.addCleanup(self.server.server_close); self.addCleanup(self.server.shutdown)
        self.base = 'http://127.0.0.1:' + str(self.server.server_port)

    def run_probe(self):
        return self.probe.run_probe('reviewed.safetensors', self.root/'validation', timeout=2,
                                    base_url=self.base, _fixture=True)

    def test_http_generation_saves_verified_proof_and_reuses_completed_result(self):
        result = self.run_probe()
        self.assertEqual(result['state'], 'complete')
        self.assertEqual(result['proof_type'], 'fixture_comfy_http')
        self.assertEqual(result['prompt_id'], self.remote)
        self.assertEqual(Path(result['image_path']).read_bytes(), self.png)
        self.assertEqual(result['sha256'], hashlib.sha256(self.png).hexdigest())
        self.assertEqual(result['image_dimensions'], [5, 4])
        self.assertEqual(self.workflow['1']['inputs']['ckpt_name'], 'reviewed.safetensors')
        self.assertEqual(self.run_probe(), result)
        self.assertEqual(self.posts, 1)

    def test_failure_or_corrupt_png_cannot_write_success_proof(self):
        self.failed = True
        with self.assertRaises(self.probe.SmokeError): self.run_probe()
        self.assertFalse((self.root/'validation/proof.json').exists())
        self.failed = False; self.png = b'not an image'
        with self.assertRaises(self.probe.SmokeError): self.run_probe()
        self.assertFalse((self.root/'validation/proof.json').exists())

    def test_checkpoint_rebinding_and_output_tampering_are_rejected(self):
        result = self.run_probe()
        with self.assertRaises(self.probe.SmokeError):
            self.probe.run_probe('other.safetensors', self.root/'validation', timeout=2, base_url=self.base, _fixture=True)
        Path(result['image_path']).write_bytes(b'corrupt')
        with self.assertRaises(self.probe.SmokeError): self.run_probe()

    def test_production_target_guard_and_loopback_guard_precede_side_effects(self):
        with patch.object(self.probe.socket, 'gethostname', return_value='PC1'):
            with self.assertRaises(self.probe.SmokeError):
                self.probe.run_probe('reviewed.safetensors', self.root/'not-created')
        self.assertFalse((self.root/'not-created').exists())

    def test_offline_parent_verification_never_submits_and_rejects_forged_metadata(self):
        with self.assertRaises(self.probe.SmokeError):
            self.probe.run_probe('reviewed.safetensors', self.root/'missing', base_url=self.base, _fixture=True, verify_only=True)
        self.assertEqual(self.posts, 0); self.assertFalse((self.root/'missing').exists())
        proof = self.run_probe()
        self.probe.run_probe('reviewed.safetensors', self.root/'validation', base_url=self.base, _fixture=True, verify_only=True)
        self.assertEqual(self.posts, 1)
        path = self.root/'validation/proof.json'
        for changes in ({'prompt_id': 'not-a-job'}, {'workflow_sha256': 'a'*64}, {'image_dimensions': [1, 1]}):
            path.write_text(json.dumps({**proof, **changes}), encoding='utf-8')
            with self.assertRaises(self.probe.SmokeError):
                self.probe.run_probe('reviewed.safetensors', self.root/'validation', base_url=self.base, _fixture=True, verify_only=True)
        self.assertEqual(self.posts, 1)
        with self.assertRaises(self.probe.SmokeError):
            self.probe.run_probe('reviewed.safetensors', self.root/'not-created', base_url='https://remote.invalid', _fixture=True)
        self.assertFalse((self.root/'not-created').exists())
