"""Owned-component removal fixtures preserve models, external services and legacy data."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

DIRECTORY = Path(__file__).resolve().parents[1]/'deploy/ls5'
sys.path.insert(0, str(DIRECTORY))


class InstallerUninstallTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('installer_uninstall_fixture', DIRECTORY/'installer_uninstall.py')
        self.module = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.module)
        self.tmp = tempfile.TemporaryDirectory(prefix='study-owned-uninstall-'); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)/'app'; self.root.mkdir()
        self.config = {'version': 1, 'target_host': 'LS5', 'app_root': str(self.root),
                       'study': {'data_dir': str(self.root/'data')}}
        self.data = self.root/'data'; self.data.mkdir(); (self.data/'book.pdf').write_bytes(b'keep PDF')
        self.models = self.root/'models'; self.models.mkdir(); (self.models/'model.safetensors').write_bytes(b'keep model')
        self.components = {}
        for name in ('study', 'comfy'):
            root = self.root/'releases'/'installed-transaction'/name; (root/'code').mkdir(parents=True)
            (root/'code/main.py').write_text('# installed fixture', encoding='utf-8')
            marker = {'schema_version': 1, 'owner': 'study-installer', 'component': name,
                      'transaction_id': 'installed-transaction', 'manifest_sha256': 'a'*64, 'component_root': str(root)}
            (root/'.study-managed-component.json').write_text(json.dumps(marker), encoding='utf-8')
            self.components[name] = {**marker, 'mode': 'managed', 'root': str(root), 'code': str(root/'code'),
                                     'python': str(root/'runtime/python.exe')}
        (self.root/'run').mkdir()
        self.active = self.root/'run/active.json'
        self.active.write_text(json.dumps({'schema_version': 1, 'target_host': 'LS5', 'components': self.components,
                                           'comfy_mode': 'managed', 'data_dir': str(self.data)}), encoding='utf-8')

    def approve(self, plan):
        return {'approved': True, 'plan_sha256': self.module.canonical_digest(plan), 'expires_at': time.time()+300}

    def execute(self, plan):
        with patch.object(self.module.socket, 'gethostname', return_value='LS5'), patch.object(self.module, 'assert_component_offline'):
            return self.module.execute_uninstall(plan, self.approve(plan))

    def test_remove_one_owned_component_keeps_other_component_data_models(self):
        plan = self.module.build_uninstall_plan(self.config, 'comfy')
        result = self.execute(plan)
        self.assertEqual(result['state'], 'removed')
        self.assertFalse(Path(self.components['comfy']['root']).exists())
        self.assertTrue(Path(self.components['study']['root']).is_dir())
        self.assertEqual((self.data/'book.pdf').read_bytes(), b'keep PDF')
        self.assertEqual((self.models/'model.safetensors').read_bytes(), b'keep model')
        active = json.loads(self.active.read_text())
        self.assertNotIn('comfy', active['components']); self.assertEqual(active['comfy_mode'], 'disabled')

    def test_external_mode_and_missing_ownership_cannot_remove_anything(self):
        active = json.loads(self.active.read_text()); active['components']['comfy'] = {'mode': 'external', 'url': 'http://127.0.0.1:8188'}
        self.active.write_text(json.dumps(active))
        with self.assertRaises(ValueError): self.module.build_uninstall_plan(self.config, 'comfy')
        Path(self.components['study']['root'], '.study-managed-component.json').unlink()
        with self.assertRaises(ValueError): self.module.build_uninstall_plan(self.config, 'study')
        self.assertTrue(Path(self.components['comfy']['root']).exists())

    def test_legacy_pdf_audio_images_are_retained_before_owned_code_removal(self):
        code = Path(self.components['study']['code'])/'prototype'
        for name, content in (('document_uploads/book.pdf', b'legacy PDF'), ('speech_audio/word.wav', b'legacy WAV'),
                              ('board_assets/image.png', b'legacy PNG'), ('study_local.sqlite3', b'legacy DB fixture')):
            path = code/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(content)
        plan = self.module.build_uninstall_plan(self.config, 'study')
        self.assertEqual(len(plan['retained_files']), 4)
        result = self.execute(plan)
        retained = Path(result['retained_root'])
        self.assertEqual((retained/'code/prototype/document_uploads/book.pdf').read_bytes(), b'legacy PDF')
        self.assertEqual((retained/'code/prototype/speech_audio/word.wav').read_bytes(), b'legacy WAV')
        self.assertEqual((retained/'code/prototype/study_local.sqlite3').read_bytes(), b'legacy DB fixture')

    def test_stale_plan_pc1_and_retention_failure_leave_originals_intact(self):
        code = Path(self.components['study']['code'])/'prototype'; code.mkdir(); (code/'study_local.sqlite3').write_bytes(b'keep')
        plan = self.module.build_uninstall_plan(self.config, 'study')
        with patch.object(self.module.socket, 'gethostname', return_value='PC1'):
            with self.assertRaises(ValueError): self.module.execute_uninstall(plan, self.approve(plan))
        self.assertTrue(code.exists())
        with patch.object(self.module.socket, 'gethostname', return_value='LS5'), patch.object(self.module, 'assert_component_offline'), patch.object(self.module.shutil, 'copy2', side_effect=OSError('fixture disk full')):
            with self.assertRaises(OSError): self.module.execute_uninstall(plan, self.approve(plan))
        self.assertEqual((code/'study_local.sqlite3').read_bytes(), b'keep')
        self.assertIn('study', json.loads(self.active.read_text())['components'])
        self.active.write_text(self.active.read_text()+' ')
        with patch.object(self.module.socket, 'gethostname', return_value='LS5'), patch.object(self.module, 'assert_component_offline'):
            with self.assertRaises(ValueError): self.module.execute_uninstall(plan, self.approve(plan))

    def test_interrupted_code_removal_resumes_only_after_verified_retention(self):
        code = Path(self.components['study']['code'])/'prototype'; code.mkdir()
        (code/'study_local.sqlite3').write_bytes(b'power-loss protected')
        plan = self.module.build_uninstall_plan(self.config, 'study')
        with patch.object(self.module.socket, 'gethostname', return_value='LS5'), patch.object(self.module, 'assert_component_offline'), patch.object(self.module, '_remove_owned_tree', side_effect=OSError('simulated power interruption')):
            with self.assertRaises(OSError): self.module.execute_uninstall(plan, self.approve(plan))
        self.assertNotIn('study', json.loads(self.active.read_text())['components'])
        self.assertEqual((Path(plan['retained_root'])/'code/prototype/study_local.sqlite3').read_bytes(), b'power-loss protected')
        recovered = self.execute(plan)
        self.assertEqual(recovered['state'], 'removed')
        self.assertFalse(Path(plan['component_root']).exists())
        self.assertEqual(self.execute(plan)['state'], 'removed')

    def test_power_loss_after_pointer_swap_before_journal_update_is_recoverable(self):
        plan = self.module.build_uninstall_plan(self.config, 'comfy')
        original = self.module.atomic_json
        def interrupted(path, value):
            if value.get('state') == 'deactivated': raise OSError('power loss after active pointer swap')
            return original(path, value)
        with patch.object(self.module.socket, 'gethostname', return_value='LS5'), patch.object(self.module, 'assert_component_offline'), patch.object(self.module, 'atomic_json', side_effect=interrupted):
            with self.assertRaises(OSError): self.module.execute_uninstall(plan, self.approve(plan))
        self.assertNotIn('comfy', json.loads(self.active.read_text())['components'])
        self.assertEqual(self.execute(plan)['state'], 'removed')

    def test_recovery_refuses_replaced_ownership_or_new_unlisted_files(self):
        plan = self.module.build_uninstall_plan(self.config, 'comfy')
        with patch.object(self.module.socket, 'gethostname', return_value='LS5'), patch.object(self.module, 'assert_component_offline'), patch.object(self.module, '_remove_owned_tree', side_effect=OSError('interrupted')):
            with self.assertRaises(OSError): self.module.execute_uninstall(plan, self.approve(plan))
        root = Path(plan['component_root']); extra = root/'new-user-file.txt'; extra.write_text('must survive')
        with self.assertRaises(ValueError): self.execute(plan)
        self.assertEqual(extra.read_text(), 'must survive')
        extra.unlink(); marker = root/'.study-managed-component.json'; marker.write_text('{}')
        with self.assertRaises(ValueError): self.execute(plan)
        self.assertTrue(root.exists())

    def test_partial_preservation_resumes_without_losing_original_or_copied_files(self):
        code = Path(self.components['study']['code'])/'prototype/board_assets'; code.mkdir(parents=True)
        (code/'one.png').write_bytes(b'original one'); (code/'two.png').write_bytes(b'original two')
        plan = self.module.build_uninstall_plan(self.config, 'study'); original_copy = self.module.shutil.copy2; calls = []
        def interrupted(source, target):
            calls.append(str(source))
            if len(calls) == 2:
                Path(target).write_bytes(b'partial'); raise OSError('power failure during copy')
            return original_copy(source, target)
        with patch.object(self.module.socket, 'gethostname', return_value='LS5'), patch.object(self.module, 'assert_component_offline'), patch.object(self.module.shutil, 'copy2', side_effect=interrupted):
            with self.assertRaises(OSError): self.module.execute_uninstall(plan, self.approve(plan))
        self.assertEqual((code/'two.png').read_bytes(), b'original two')
        result = self.execute(plan)
        kept = Path(result['retained_root'])/'code/prototype/board_assets'
        self.assertEqual((kept/'one.png').read_bytes(), b'original one')
        self.assertEqual((kept/'two.png').read_bytes(), b'original two')

    def test_real_mid_file_removal_retains_marker_and_recovers_after_orphan_lock(self):
        root = Path(self.components['study']['root']); victim = root/'code/main.py'
        plan = self.module.build_uninstall_plan(self.config, 'study'); original_unlink = Path.unlink
        def interrupted(path, *args, **kwargs):
            result = original_unlink(path, *args, **kwargs)
            if path == victim: raise OSError('power loss after one recorded file was deleted')
            return result
        with patch.object(self.module.socket, 'gethostname', return_value='LS5'), patch.object(self.module, 'assert_component_offline'), patch.object(Path, 'unlink', interrupted):
            with self.assertRaises(OSError): self.module.execute_uninstall(plan, self.approve(plan))
        self.assertFalse(victim.exists()); self.assertTrue((root/'.study-managed-component.json').is_file())
        (self.root/'run/lifecycle.lock').write_text('2147483646')
        import installer_engine
        with patch.object(installer_engine, '_pid_alive', return_value=False):
            self.assertEqual(self.execute(plan)['state'], 'removed')
        self.assertFalse(root.exists()); self.assertEqual((self.data/'book.pdf').read_bytes(), b'keep PDF')
