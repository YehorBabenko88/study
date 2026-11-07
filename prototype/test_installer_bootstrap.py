"""Native Windows setup fixtures; no downloads, production installs or executable payloads."""
import hashlib
from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch
import zipfile

LS5=Path(__file__).resolve().parents[1]/'deploy/ls5'
spec=importlib.util.spec_from_file_location('installer_cli_fixture',LS5/'installer_cli.py')
cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
SHELL=shutil.which('powershell') or shutil.which('pwsh')


class InstallerCLIReadOnlyTests(unittest.TestCase):
    def test_three_modes_readonly_do_not_create_paths_or_select_hardware(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'must-not-exist'
            for mode in ('managed','external','disabled'):
                result=cli.readonly_summary({'release_ready':False,'artifacts':[]},{'app_root':str(root)},mode=mode)
                self.assertEqual(result['mode'],mode);self.assertFalse(result['filesystem_mutation']);self.assertFalse(result['network_performed'])
                self.assertFalse(root.exists())
    def test_execution_host_is_not_spoofed_by_environment(self):
        with patch.object(cli.socket,'gethostname',return_value='PC1'),patch.dict(os.environ,{'COMPUTERNAME':'LS5'}):
            with self.assertRaises(ValueError):cli.assert_execution_host()
    def test_approval_needs_exact_hash_license_and_download_confirmation(self):
        digest=lambda obj:hashlib.sha256(json.dumps(obj,sort_keys=True).encode()).hexdigest()
        with self.assertRaises(ValueError):cli.ask_approval({}, {}, digest,input_fn=lambda prompt:'')
        answers=iter([digest({}),'LICENSES NONE','DOWNLOAD 0'])
        approval=cli.ask_approval({}, {}, digest,input_fn=lambda prompt:next(answers))
        self.assertTrue(approval['approved']);self.assertFalse(approval['hardware_changes_approved'])
    def test_saved_uninstall_plan_recovery_is_forwarded_without_rebuilding(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            config={'app_root':str(root/'app'),'study':{'data_dir':str(root/'data')}}
            plan={'schema_version':1,'operation':'uninstall','target_host':'LS5','component':'study','app_root':config['app_root'],'data_dir':config['study']['data_dir'],'transaction_id':'already-deactivated-fixture'}
            files={name:root/(name+'.json') for name in ('manifest','config','audit','plan','approval')}
            for name,value in [('manifest',{}),('config',config),('audit',{}),('plan',plan),('approval',{'approved':True})]:files[name].write_text(json.dumps(value))
            calls=[]
            module=types.ModuleType('installer_uninstall')
            module.build_uninstall_plan=lambda *args:(_ for _ in ()).throw(AssertionError('Recovery must not rebuild random transaction'))
            module.execute_uninstall=lambda received,approval:calls.append((received,approval)) or {'state':'removed'}
            engine=types.ModuleType('installer_engine');engine.canonical_digest=lambda value:'fixture-plan-hash';engine.validate_audit=lambda audit:audit
            service=types.ModuleType('study_service');service.load_config=lambda path:dict(config)
            args=['--action','uninstall','--mode','disabled','--component','study']
            for name in files:args+=['--'+('plan-file' if name=='plan' else 'approval-file' if name=='approval' else name),str(files[name])]
            with patch.dict(sys.modules,{'installer_uninstall':module,'installer_engine':engine,'study_service':service}),patch.object(cli.socket,'gethostname',return_value='LS5'),redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(args),0)
            self.assertEqual(calls,[(plan,{'approved':True})])
            self.assertFalse((root/'app').exists())
    def test_model_license_url_hash_and_source_card_are_shown_before_approval(self):
        license_url='https://example.invalid/model/revision/LICENSE.md';card='https://example.invalid/model/revision/README.md';license_sha='a'*64
        manifest={'artifacts':[{'id':'fixture-model','kind':'model','version':'reviewed-1','source_revision':'immutable-fixture','size':123456,'license_id':'fixture-license','sha256':'b'*64,'url':'https://example.invalid/model.bin','source_model_card':card,'license_document':{'url':license_url,'sha256':license_sha}}]}
        plan={'artifact_ids':['fixture-model'],'accepted_licenses':['fixture-license'],'approved_download_bytes':123456}
        output=io.StringIO();answers=iter(['fixture-plan-hash','LICENSES fixture-license','DOWNLOAD 123456'])
        def respond(prompt):
            self.assertIn(license_url,output.getvalue());self.assertIn(license_sha,output.getvalue());self.assertIn(card,output.getvalue());self.assertIn('123456',output.getvalue())
            return next(answers)
        with redirect_stdout(output):cli.ask_approval(plan,manifest,lambda value:'fixture-plan-hash',input_fn=respond)
        del manifest['artifacts'][0]['license_document']
        with self.assertRaisesRegex(ValueError,'pinned license document'):cli.ask_approval(plan,manifest,lambda value:'hash',input_fn=lambda prompt:self.fail('Approval prompted before pinned legal evidence'))


@unittest.skipUnless(SHELL and os.name=='nt','Requires Windows PowerShell fixture runtime')
class InstallerNativeBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='study-bootstrap-fixture-');self.root=Path(self.tmp.name)
        self.script=self.root/'setup.ps1';shutil.copy2(LS5/'setup.ps1',self.script)
    def tearDown(self):self.tmp.cleanup()
    def run_script(self,body):
        test=self.root/'fixture.ps1'
        test.write_text("$ErrorActionPreference='Stop'\n. $args[0]\n"+body,encoding='utf-8')
        return subprocess.run([SHELL,'-NoProfile','-NonInteractive','-File',str(test),str(self.script)],capture_output=True,text=True,timeout=30)
    def cached_archive(self,unsafe=False):
        payload=self.root/'fixture.zip'
        with zipfile.ZipFile(payload,'w') as archive:
            archive.writestr('../escape.txt' if unsafe else 'python.exe',b'FIXTURE BYTES ONLY - NEVER EXECUTE')
            archive.writestr('python313._pth',b'python313.zip\n.\n')
        data=payload.read_bytes();sha=hashlib.sha256(data).hexdigest()
        stage=self.root/'app/staging'/('bootstrap-'+sha);stage.mkdir(parents=True)
        shutil.copy2(payload,stage/'python-embed.zip')
        (stage/'bootstrap-owned.json').write_text(json.dumps({'owner':'study-installer-bootstrap-v1','sha256':sha}))
        plan={'app_root':str(self.root/'app'),'artifact':{'runtime_kind':'embedded','sha256':sha,'size_bytes':len(data),'python_executable':'python.exe','license_id':'PSF-2.0','url':'https://www.python.org/ftp/python/3.13.12/python-3.13.12-embed-amd64.zip'}}
        path=self.root/'plan.json';path.write_text(json.dumps(plan));return path,stage
    def test_default_native_plan_needs_no_python_no_writes_no_network(self):
        config=self.root/'config.json';catalog=self.root/'catalog.json';audit=self.root/'absent-audit.json'
        app=self.root/'not-created';config.write_text(json.dumps({'app_root':str(app),'target_host':'LS5'}));catalog.write_text(json.dumps({'release_ready':False,'artifacts':[]}))
        result=subprocess.run([SHELL,'-NoProfile','-NonInteractive','-File',str(self.script),'-Config',str(config),'-Manifest',str(catalog),'-Audit',str(audit)],capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr);plan=json.loads(result.stdout)
        self.assertEqual(plan['status'],'READ_ONLY');self.assertFalse(plan['network_performed']);self.assertFalse(app.exists())
    def test_pc1_execution_refused_before_bootstrap(self):
        if socket.gethostname().upper()=='LS5':self.skipTest('PC1 refusal fixture is for non-LS5 hosts')
        config=self.root/'config.json';catalog=self.root/'catalog.json';app=self.root/'not-created'
        config.write_text(json.dumps({'app_root':str(app),'target_host':'LS5'}));catalog.write_text('{}')
        result=subprocess.run([SHELL,'-NoProfile','-NonInteractive','-File',str(self.script),'-Action','Install','-Config',str(config),'-Manifest',str(catalog)],capture_output=True,text=True,timeout=15)
        self.assertNotEqual(result.returncode,0);self.assertFalse(app.exists())
    def test_missing_pin_and_wrong_approval_are_refused(self):
        result=self.run_script("$bad=$false;try {Assert-BootstrapPin $null} catch {$bad=$true};if (-not $bad) {throw 'Missing pin accepted'};try {Assert-BootstrapApproval ([pscustomobject]@{schema_version=1;phase='bootstrap';approved=$true;plan_sha256='other';license_accepted=$true;large_download_approved=$true;expires_at=[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()+60}) 'expected';throw 'Wrong approval accepted'} catch {if ($_.Exception.Message -eq 'Wrong approval accepted') {throw}}")
        self.assertEqual(result.returncode,0,result.stderr)
    def test_cached_fixture_zip_integrity_extraction_and_tamper_refusal(self):
        plan,stage=self.cached_archive()
        body="function Assert-SetupTarget {}\n$plan=Get-Content -LiteralPath '"+str(plan).replace("'","''")+"' -Raw | ConvertFrom-Json\n$exe=Get-VerifiedBootstrap $plan 'fixture-approved-digest'\n[IO.File]::WriteAllText($exe,'TAMPERED FIXTURE')\n$refused=$false;try {Get-VerifiedBootstrap $plan 'fixture-approved-digest' | Out-Null} catch {$refused=$true};if (-not $refused) {throw 'Tampered runtime accepted'}"
        result=self.run_script(body);self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue((stage/'python/python.exe').exists())
    def test_fixture_archive_path_escape_is_refused(self):
        plan,stage=self.cached_archive(unsafe=True)
        body="function Assert-SetupTarget {}\n$plan=Get-Content -LiteralPath '"+str(plan).replace("'","''")+"' -Raw | ConvertFrom-Json\n$refused=$false;try {Get-VerifiedBootstrap $plan 'fixture' | Out-Null} catch {$refused=$true};if (-not $refused) {throw 'ZIP escape accepted'}"
        result=self.run_script(body);self.assertEqual(result.returncode,0,result.stderr)
        self.assertFalse((stage/'escape.txt').exists());self.assertFalse((self.root/'escape.txt').exists())
    def test_external_disabled_and_unmarked_components_are_not_lifecycle_owned(self):
        path=self.root/'descriptors.json'
        path.write_text(json.dumps({'app_root':str(self.root/'app'),'external':{'owner':'external','mode':'external','url':'http://127.0.0.1:8188'},'disabled':{'mode':'disabled'},'unmarked':{'owner':'study-installer','mode':'managed','root':str(self.root/'app/releases/tx/comfy')}}))
        body="$cases=Get-Content -LiteralPath '"+str(path).replace("'","''")+"' -Raw | ConvertFrom-Json\nforeach ($name in @('external','disabled','unmarked')) {$refused=$false;try {Assert-ManagedActiveComponent $cases.$name 'comfy' $cases.app_root | Out-Null} catch {$refused=$true};if (-not $refused) {throw ('Unsafe lifecycle ownership accepted: '+$name)}}"
        result=self.run_script(body);self.assertEqual(result.returncode,0,result.stderr)
        self.assertFalse((self.root/'app').exists())
    def test_bootstrap_range_resume_uses_fixture_stream_and_verifies_final_hash(self):
        plan,stage=self.cached_archive()
        archive=stage/'python-embed.zip';data=archive.read_bytes();archive.unlink()
        partial=Path(str(archive)+'.part');partial.write_bytes(data[:23])
        remainder=self.root/'remainder';remainder.write_bytes(data[23:])
        body="function Assert-SetupTarget {}\n$plan=Get-Content -LiteralPath '"+str(plan).replace("'","''")+"' -Raw | ConvertFrom-Json\n$script:rest=[IO.File]::ReadAllBytes('"+str(remainder).replace("'","''")+"')\nfunction Get-SetupWebResponse($Request) {if ($Request.Headers['Range'] -ne 'bytes=23-') {throw 'Range missing'};$headers=New-Object Collections.Specialized.NameValueCollection;$headers.Add('Content-Range',('bytes 23-"+str(len(data)-1)+"/"+str(len(data))+"'));$response=[pscustomobject]@{StatusCode=206;ContentLength=$script:rest.Length;Headers=$headers};$response | Add-Member ScriptMethod GetResponseStream {return [IO.MemoryStream]::new($script:rest,$false)};$response | Add-Member ScriptMethod Dispose {};return $response}\nGet-VerifiedBootstrap $plan 'fixture-resume' | Out-Null"
        result=self.run_script(body);self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(archive.read_bytes(),data);self.assertFalse(partial.exists())
    def test_interrupted_extraction_part_is_rebuilt_then_atomically_published(self):
        plan,stage=self.cached_archive();parts=stage/'extract-parts';parts.mkdir()
        partial=parts/(hashlib.sha256(b'python.exe').hexdigest()+'.part');partial.write_bytes(b'FIX')
        body="function Assert-SetupTarget {}\n$plan=Get-Content -LiteralPath '"+str(plan).replace("'","''")+"' -Raw | ConvertFrom-Json\nGet-VerifiedBootstrap $plan 'fixture-resume-extraction' | Out-Null"
        result=self.run_script(body);self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual((stage/'python/python.exe').read_bytes(),b'FIXTURE BYTES ONLY - NEVER EXECUTE')
        self.assertFalse(partial.exists());self.assertEqual(len(list(parts.glob('*.interrupted-*'))),1)
        result=self.run_script(body);self.assertEqual(result.returncode,0,result.stderr)
    def test_bootstrap_exclusive_handle_denies_concurrent_process_then_crash_releases(self):
        plan,stage=self.cached_archive();sha=json.loads(plan.read_text())['artifact']['sha256']
        lock=stage.parent/('bootstrap-'+sha+'.lock');ready=self.root/'lock-held'
        holder=self.root/'hold-lock.ps1'
        holder.write_text("param([string]$Lock,[string]$Ready)\n$held=[IO.File]::Open($Lock,[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)\n[IO.File]::WriteAllText($Ready,'held')\nStart-Sleep -Seconds 20\n$held.Dispose()\n",encoding='utf-8')
        child=subprocess.Popen([SHELL,'-NoProfile','-NonInteractive','-File',str(holder),'-Lock',str(lock),'-Ready',str(ready)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            deadline=time.monotonic()+8
            while not ready.exists() and time.monotonic()<deadline:time.sleep(.05)
            self.assertTrue(ready.exists(),'Fixture holder did not acquire its temporary lock')
            body="function Assert-SetupTarget {}\n$plan=Get-Content -LiteralPath '"+str(plan).replace("'","''")+"' -Raw | ConvertFrom-Json\n$refused=$false;try {Get-VerifiedBootstrap $plan 'fixture-concurrent' | Out-Null} catch {$refused=$true};if (-not $refused) {throw 'Concurrent bootstrap accepted'}"
            result=self.run_script(body);self.assertEqual(result.returncode,0,result.stderr)
            self.assertFalse((stage/'python').exists())
        finally:
            child.kill();child.communicate(timeout=8)
        self.assertTrue(lock.exists(),'Persistent lock file should not need stale-PID deletion')
        body="function Assert-SetupTarget {}\n$plan=Get-Content -LiteralPath '"+str(plan).replace("'","''")+"' -Raw | ConvertFrom-Json\nGet-VerifiedBootstrap $plan 'fixture-after-holder-crash' | Out-Null"
        result=self.run_script(body);self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue((stage/'python/python.exe').is_file())
    def test_cached_unlisted_runtime_file_remains_refused(self):
        plan,stage=self.cached_archive()
        prefix="function Assert-SetupTarget {}\n$plan=Get-Content -LiteralPath '"+str(plan).replace("'","''")+"' -Raw | ConvertFrom-Json\n"
        result=self.run_script(prefix+"Get-VerifiedBootstrap $plan 'fixture' | Out-Null");self.assertEqual(result.returncode,0,result.stderr)
        (stage/'python/unlisted.py').write_bytes(b'FIXTURE; NEVER IMPORT')
        result=self.run_script(prefix+"$refused=$false;try {Get-VerifiedBootstrap $plan 'fixture' | Out-Null} catch {$refused=$true};if (-not $refused) {throw 'Unlisted cached file accepted'}")
        self.assertEqual(result.returncode,0,result.stderr)
