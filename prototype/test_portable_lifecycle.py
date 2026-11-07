"""Portable lifecycle fixtures only: never start services or change host configuration."""
from contextlib import closing
import importlib.util
import json
from pathlib import Path
import sqlite3
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
LS5=Path(__file__).resolve().parents[1]/'deploy/ls5'
sys.path.insert(0,str(LS5))
import portable_ops as ops

class PortableLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='study-lifecycle-')
        self.root=Path(self.tmp.name);self.app=self.root/'app';self.release=self.app/'releases/v1';self.data=self.root/'data'
        self.release.mkdir(parents=True);self.data.mkdir()
        self.config={'version':1,'target_host':'LS5','app_root':str(self.app),'study':{'host':'127.0.0.1','port':8766,'python':str(self.root/'study-env/Scripts/python.exe'),'release_dir':str(self.release),'data_dir':str(self.data)},'comfy':{'enabled':True,'host':'127.0.0.1','port':8188,'python':str(self.root/'comfy-env/Scripts/python.exe'),'directory':str(self.root/'ComfyUI'),'checkpoint':'fixture.safetensors'}}
        for name in ('study','comfy'):
            exe=Path(self.config[name]['python']);exe.parent.mkdir(parents=True);exe.write_bytes(b'fixture; not executable')
        for path in (self.release/'deploy/ls5/study_service.py',self.release/'prototype/web_app.py',self.root/'ComfyUI/main.py',self.root/'ComfyUI/models/checkpoints/fixture.safetensors'):
            path.parent.mkdir(parents=True,exist_ok=True);path.write_text('# fixture only',encoding='utf-8')
        flags=self.root/'ComfyUI/comfy/cli_args.py';flags.parent.mkdir();flags.write_text('--disable-auto-launch --disable-api-nodes --disable-all-custom-nodes --output-directory --user-directory',encoding='utf-8')
        self.configfile=self.root/'config.json';self.configfile.write_text(json.dumps(self.config),encoding='utf-8')
    def tearDown(self):self.tmp.cleanup()
    def test_independent_launch_arguments_and_external_output(self):
        cfg=ops.load_config(self.configfile)
        study=ops.launch_plan(cfg,'study');comfy=ops.launch_plan(cfg,'comfy')
        self.assertNotEqual(study['executable'],comfy['executable'])
        self.assertEqual(study['args'][0],'-B');self.assertEqual(comfy['args'][0],'-B')
        self.assertEqual(study['args'][2:],['--config',str(self.configfile)])
        self.assertIn('--disable-auto-launch',comfy['args']);self.assertIn('--disable-api-nodes',comfy['args'])
        self.assertIn('--disable-all-custom-nodes',comfy['args'])
        self.assertEqual(comfy['args'][comfy['args'].index('--port')+1],'8188')
        self.assertTrue(all(ops.inside(Path(p),self.data) and not ops.inside(Path(p),self.release) for p in comfy['create_dirs']))
        Path(cfg['comfy']['python']).unlink()
        self.assertEqual(ops.launch_plan(cfg,'study')['service'],'study')
        with self.assertRaises(ValueError):ops.launch_plan(cfg,'comfy')
    def test_guard_cannot_be_bypassed_by_environment_host_or_username(self):
        with patch.object(ops.socket,'gethostname',return_value='PC1'),patch.dict(ops.os.environ,{'COMPUTERNAME':'LS5'}):
            with self.assertRaises(ValueError):ops.target_guard(self.config)
        with patch.object(ops.socket,'gethostname',return_value='LS-5'):
            with self.assertRaises(ValueError):ops.target_guard(self.config)
        with patch.object(ops.socket,'gethostname',return_value='ls5'):ops.target_guard(self.config)
    def test_sqlite_backup_restore_assets_hashes_and_handle_cleanup(self):
        database=self.data/'study.sqlite3'
        with closing(sqlite3.connect(database)) as db:
            db.execute('CREATE TABLE cards(text)');db.execute("INSERT INTO cards VALUES('retained card')");db.commit()
        asset=self.data/'assets/image.png';asset.parent.mkdir();asset.write_bytes(b'fixture asset bytes')
        backup=self.root/'backup';manifest=ops.backup_data(self.data,backup)
        self.assertEqual({f['kind'] for f in manifest['files']},{'sqlite','file'})
        restored=self.root/'restored';ops.restore_data(backup,restored)
        with closing(sqlite3.connect(restored/'study.sqlite3')) as db:self.assertEqual(db.execute('SELECT text FROM cards').fetchone()[0],'retained card')
        self.assertEqual(ops.digest(asset),ops.digest(restored/'assets/image.png'))
        # Windows catches leaked SQLite handles when removing these fixture trees.
        (backup/'study.sqlite3').unlink();(restored/'study.sqlite3').unlink();database.unlink()
    def test_restore_refuses_existing_data_tamper_and_manifest_escape(self):
        (self.data/'asset').write_text('preserve',encoding='utf-8');backup=self.root/'backup';ops.backup_data(self.data,backup)
        with self.assertRaises(ValueError):ops.restore_data(backup,self.data)
        self.assertEqual((self.data/'asset').read_text(),'preserve')
        (backup/'asset').write_text('corrupt',encoding='utf-8')
        with self.assertRaises(ValueError):ops.restore_data(backup,self.root/'new1')
        manifest=json.loads((backup/'backup-manifest.json').read_text());manifest['files'][0]['path']='../escape';(backup/'backup-manifest.json').write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):ops.restore_data(backup,self.root/'new2')
        self.assertFalse((self.root/'new2').exists())
    def test_uninstall_guard_retains_data_environments_and_other_release(self):
        cfg=ops.load_config(self.configfile)
        self.assertEqual(ops.uninstall_candidate(cfg,self.release),str(self.release))
        for candidate in (self.app,self.app/'releases',self.data,Path(cfg['comfy']['directory']),self.app/'releases/other'):
            with self.assertRaises(ValueError):ops.uninstall_candidate(cfg,candidate)
        self.assertTrue(self.data.is_dir());self.assertTrue(Path(cfg['study']['python']).is_file());self.assertTrue(Path(cfg['comfy']['python']).is_file())
        (self.release/'prototype/web_app.py').unlink()
        with self.assertRaises(ValueError):ops.uninstall_candidate(cfg,self.release)
    def test_lifecycle_lock_excludes_starts_and_operations_and_releases(self):
        cfg=ops.load_config(self.configfile)
        with ops.lifecycle_lock(cfg):
            with self.assertRaises(FileExistsError):
                with ops.lifecycle_lock(cfg):pass
        with ops.lifecycle_lock(cfg):pass
        self.assertFalse((self.app/'run/lifecycle.lock').exists())
    def test_unsupported_comfy_version_and_source_nested_backup_refused(self):
        cfg=ops.load_config(self.configfile);(self.root/'ComfyUI/comfy/cli_args.py').write_text('--listen --port')
        with self.assertRaises(ValueError):ops.launch_plan(cfg,'comfy')
        with self.assertRaises(ValueError):ops.backup_data(self.data,self.data/'backup')
    def test_linked_data_root_refused_before_resolution(self):
        alias=self.root/'alias'
        try:alias.symlink_to(self.data,target_is_directory=True)
        except OSError:
            shell=shutil.which('powershell') or shutil.which('pwsh')
            if os.name!='nt' or not shell:self.skipTest('Fixture link/junction facility unavailable')
            script=self.root/'create-fixture-junction.ps1'
            script.write_text("param([string]$Link,[string]$Target)\n$ErrorActionPreference='Stop'\nNew-Item -ItemType Junction -Path $Link -Target $Target | Out-Null\n",encoding='utf-8')
            result=subprocess.run([shell,'-NoProfile','-NonInteractive','-File',str(script),'-Link',str(alias),'-Target',str(self.data)],capture_output=True,text=True,timeout=15)
            if result.returncode:self.skipTest('Fixture junction refused: '+result.stderr[:160])
        with self.assertRaises(ValueError):ops.backup_data(alias,self.root/'backup')
        if alias.is_symlink():alias.unlink()
        else:alias.rmdir()
        self.assertTrue(self.data.is_dir())

    def test_uninstall_refuses_legacy_learner_storage_without_removing_it(self):
        cfg=ops.load_config(self.configfile)
        for name in ('study_local.sqlite3','study_lexicon.sqlite3-wal','board_assets','compositions.sqlite'):
            legacy=self.release/'prototype'/name
            legacy.write_bytes(b'learner fixture')
            with self.assertRaisesRegex(ValueError,'Legacy learner storage'):ops.uninstall_candidate(cfg,self.release)
            self.assertEqual(legacy.read_bytes(),b'learner fixture')
            legacy.unlink()

    def test_offline_guard_refuses_comfy_writer_and_managed_records(self):
        cfg=ops.load_config(self.configfile)
        class Connection:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def settimeout(self,value):pass
            def connect_ex(self,address):return 0 if address[1]==8188 else 1
        with patch.object(ops.socket,'socket',return_value=Connection()):
            with self.assertRaisesRegex(ValueError,'comfy port'):ops.assert_offline(cfg)
        run=self.app/'run';run.mkdir();(run/'comfy.json').write_text('{}')
        with patch.object(ops.socket,'socket',return_value=Connection()):
            with self.assertRaisesRegex(ValueError,'managed comfy'):ops.assert_offline(cfg)
    def test_native_lock_owner_stamp_matches_process_and_flushes_ascii(self):
        shell=shutil.which('powershell') or shutil.which('pwsh')
        if os.name!='nt' or not shell:self.skipTest('Requires Windows PowerShell fixture runtime')
        common=self.root/'common.ps1';shutil.copy2(LS5/'common.ps1',common)
        script=self.root/'lock-fixture.ps1';lock=self.root/'lifecycle.lock'
        script.write_text("param([string]$Common,[string]$Path)\n$ErrorActionPreference='Stop'\n. $Common\n$handle=[IO.File]::Open($Path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)\ntry {Write-LS5LockOwner $handle} finally {$handle.Dispose()}\nif ([IO.File]::ReadAllText($Path) -cne [string]$PID) {throw 'Lock owner PID missing/mismatched'}\n",encoding='utf-8')
        result=subprocess.run([shell,'-NoProfile','-NonInteractive','-File',str(script),'-Common',str(common),'-Path',str(lock)],capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue(lock.read_bytes().isdigit())
    def test_external_comfy_listener_does_not_block_owned_study_backup(self):
        cfg=ops.load_config(self.configfile);run=self.app/'run';run.mkdir()
        active={'schema_version':1,'target_host':'LS5','components':{'comfy':{'owner':'external','mode':'external','url':'http://127.0.0.1:8188'}}}
        (run/'active.json').write_text(json.dumps(active))
        (self.data/'learner.txt').write_text('retained')
        visited=[]
        class Connection:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def settimeout(self,value):pass
            def connect_ex(self,address):visited.append(address[1]);return 0 if address[1]==8188 else 1
        with patch.object(ops.socket,'socket',return_value=Connection()):
            ops.assert_offline(cfg)
            result=ops.backup_data(self.data,self.root/'external-independent-backup')
        self.assertEqual(visited,[8766]);self.assertEqual(len(result['files']),1)
        active['components']['comfy']={'owner':'study-installer','mode':'managed'}
        (run/'active.json').write_text(json.dumps(active))
        with patch.object(ops.socket,'socket',return_value=Connection()):
            with self.assertRaisesRegex(ValueError,'comfy port'):ops.assert_offline(cfg)
