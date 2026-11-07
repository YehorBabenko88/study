"""Distribution building archives only a clean committed release; no installation."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

SOURCE = Path(__file__).resolve().parents[1]


class InstallerBundleTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('installer_bundle_fixture', SOURCE/'deploy/ls5/build_bundle.py')
        self.builder = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.builder)
        self.tmp = tempfile.TemporaryDirectory(prefix='study-bundle-fixture-'); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)/'source'; self.root.mkdir()
        self.git('init', '-q')
        for name in ('release_catalog.json', 'manifest_validation.py', 'setup.ps1', 'comfy_cpu_lock_candidate.json'):
            target = self.root/'deploy/ls5'/name; target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((SOURCE/'deploy/ls5'/name).read_bytes())
        (self.root/'prototype').mkdir(); (self.root/'prototype/web_app.py').write_text('# fixture only')
        self.git('add', '.'); self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture')

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.root, text=True, stderr=subprocess.STDOUT).strip()

    def test_bundle_binds_exact_source_hash_and_study_closed_lock(self):
        destination = Path(self.tmp.name)/'installer.zip'
        result = self.builder.build_bundle(self.root, destination)
        self.assertEqual(result['source_sha'], self.git('rev-parse', 'HEAD'))
        with zipfile.ZipFile(destination) as archive:
            metadata = json.loads(archive.read('release.json'))
            manifest = json.loads(archive.read('release_manifest.json'))
            self.assertEqual(metadata['source_sha'], result['source_sha'])
            self.assertIn('payload/study.zip', archive.namelist())
            source = next(item for item in manifest['artifacts'] if item.get('local_path') == 'payload/study.zip')
            import hashlib
            self.assertEqual(source['sha256'], hashlib.sha256(archive.read('payload/study.zip')).hexdigest())
            self.assertTrue(manifest['components']['study']['dependency_lock_complete'])
            self.assertFalse(manifest.get('release_ready'), 'Managed cannot be advertised as released')
            self.assertNotIn('ls5-audit-report.json', archive.namelist())
            candidates = metadata['optional_managed_cpu_candidate_manifests']
            self.assertTrue(candidates)
            cpu = json.loads(archive.read(candidates[0]))
            self.assertEqual(cpu['runtime_acceptance'], 'not_tested')
            self.assertTrue(cpu['requires_real_generation_smoke'])

    def test_dirty_or_tracked_user_data_are_refused_before_bundle_write(self):
        destination = Path(self.tmp.name)/'installer.zip'
        (self.root/'prototype/web_app.py').write_text('# dirty fixture')
        with self.assertRaises(ValueError): self.builder.build_bundle(self.root, destination)
        self.assertFalse(destination.exists())
        self.git('add', '.'); self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'update')
        data = self.root/'prototype/document_uploads/book.pdf'; data.parent.mkdir(); data.write_bytes(b'private fixture PDF')
        self.git('add', '.'); self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'bad user data fixture')
        with self.assertRaises(ValueError): self.builder.build_bundle(self.root, destination)
        self.assertFalse(destination.exists())
