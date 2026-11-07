"""Fixture-only installer engine tests; no production commands or LS5 mutations."""
import hashlib,io,json,socket,tempfile,time,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
import installer_engine as e

class EngineTests(unittest.TestCase):
    def fixture(self,root):
        payload=root/'bundle'/'payload';payload.mkdir(parents=True)
        def archive(name,files,kind='zip',**metadata):
            file=payload/name
            with zipfile.ZipFile(file,'w') as output:
                for key,value in files.items():output.writestr(key,value)
            return dict(id=name.replace('.','-'),local_path='payload/'+name,kind=kind,size=file.stat().st_size,sha256=hashlib.sha256(file.read_bytes()).hexdigest(),**metadata)
        python=archive('python.zip',{'python.exe':b'fixture','python313._pth':'python313.zip\n.\n#import site\n'},kind='python',runtime_kind='embedded',python_executable='python.exe',python_tag='cp313',platform='win_amd64')
        pip=archive('pip.whl',{'pip/__init__.py':'#fixture'},kind='wheel',distribution='pip',version='25.3')
        source=archive('study.zip',{'prototype/web_app.py':'#fixture','deploy/ls5/study_service.py':'#fixture'})
        wheel=archive('fixture-1.0-py3-none-any.whl',{'fixture/__init__.py':'#fixture'},kind='wheel',distribution='fixture',version='1.0',python_tag='py3',platform='any')
        self.artifacts=[python,pip,source,wheel]
        manifest={'schema_version':1,'allowed_hosts':['www.python.org'],'artifacts':self.artifacts,'components':{'study':{'artifact_ids':[source['id']],'python_artifact_id':python['id'],'pip_artifact_id':pip['id'],'runtime_kind':'embedded','wheel_ids':[wheel['id']],'requirements_lock':[{'distribution':'fixture','version':'1.0','artifact_id':wheel['id'],'requires':[]}],'dependency_lock_complete':True,'dependency_lock_audited':True,'entrypoint':'deploy/ls5/study_service.py'}}}
        audit={'schema_version':1,'status':'COLLECTED_READ_ONLY','hostname':'LS5','collected_at_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'os':[{'Caption':'Microsoft Windows 11 Pro','BuildNumber':'26100','OSArchitecture':'64-bit'}],'cpu':[{'Name':'fixture CPU','NumberOfCores':8}],'ram':[{'TotalPhysicalMemory':32*1024**3}],'disks':[{'DeviceID':str(root.anchor),'FreeSpace':100*1024**3,'Size':200*1024**3}],'gpu':{'nvidia_smi':None,'wmi':[]},'listening_ports_8188_8766':[],'changes_performed':[]}
        config={'target_host':'LS5','app_root':str(root/'app'),'bundle_root':str(root/'bundle'),'study':{'host':'127.0.0.1','port':8766,'data_dir':str(root/'app'/'data')},'comfy':{'host':'127.0.0.1','port':8188}}
        plan=e.build_plan(manifest,audit,config,mode='disabled',components=['study'])
        approval={'schema_version':1,'approved':True,'plan_sha256':e.canonical_digest(plan),'manifest_sha256':e.canonical_digest(manifest),'expires_at':time.time()+300}
        return manifest,audit,config,plan,approval
    def test_unapproved_or_pc1_never_mutates(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);manifest,audit,config,plan,approval=self.fixture(root)
            with self.assertRaises(ValueError):e.InstallerEngine(manifest,plan,dict(approval,approved=False),audit).execute()
            with patch.object(e.socket,'gethostname',return_value='PC1'):
                with self.assertRaises(ValueError):e.InstallerEngine(manifest,plan,approval,audit).execute()
            self.assertFalse((root/'app').exists())
    def test_success_is_atomic_and_failed_update_keeps_active_and_user_data(self):
        class Runner:
            fail=False
            def __init__(self):self.calls=[]
            def run(self,args,**kwargs):
                self.calls.append(args)
                if self.fail:raise RuntimeError('fixture install failure')
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);manifest,audit,config,plan,approval=self.fixture(root);runner=Runner()
            with patch.object(e.socket,'gethostname',return_value='LS5'),patch.object(e,'assert_components_offline'):
                installed=e.InstallerEngine(manifest,plan,approval,audit,runner=runner).execute()
                self.assertEqual(installed['state'],'committed')
                active=Path(config['app_root'])/'run'/'active.json';before=active.read_bytes()
                data=Path(config['study']['data_dir']);(data/'learner.txt').write_text('never lose')
                newer=e.build_plan(manifest,audit,config,mode='disabled',components=['study'],release_label='v2')
                approved=dict(approval,plan_sha256=e.canonical_digest(newer));runner.fail=True
                with self.assertRaises(RuntimeError):e.InstallerEngine(manifest,newer,approved,audit,runner=runner).execute()
                self.assertEqual(active.read_bytes(),before);self.assertEqual((data/'learner.txt').read_text(),'never lose')
                self.assertTrue(any('--no-index' in call and '--require-hashes' in call for call in runner.calls))
    def test_stale_audit_and_changed_plan_fail_before_writes(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);manifest,audit,config,plan,approval=self.fixture(root)
            with patch.object(e.socket,'gethostname',return_value='LS5'):
                with self.assertRaises(ValueError):e.InstallerEngine(manifest,dict(plan,mode='managed'),approval,audit).execute()
                audit['collected_at_utc']='2000-01-01T00:00:00Z'
                with self.assertRaises(ValueError):e.InstallerEngine(manifest,plan,approval,audit).execute()
            self.assertFalse((root/'app').exists())
    def test_external_api_requires_no_paths_and_never_starts_or_stops_it(self):
        class Runner:
            def run(self,*args,**kwargs):pass
            def start(self,*args,**kwargs):raise AssertionError('external service started')
            def stop(self,*args,**kwargs):raise AssertionError('external service stopped')
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);manifest,audit,config,_,approval=self.fixture(root)
            config['comfy']={'host':'127.0.0.1','port':8188,'checkpoint':'existing.safetensors'}
            plan=e.build_plan(manifest,audit,config,mode='external',components=['study'])
            approval['plan_sha256']=e.canonical_digest(plan)
            with patch.object(e.socket,'gethostname',return_value='LS5'),patch.object(e,'assert_components_offline'),patch.object(e,'external_health',return_value={'state':'reachable','inference_verified':False}):
                result=e.InstallerEngine(manifest,plan,approval,audit,runner=Runner()).execute()
            descriptor=result['active']['components']['comfy']
            self.assertEqual(descriptor['mode'],'external');self.assertFalse(descriptor['enabled'])
            self.assertNotIn('root',descriptor);self.assertNotIn('python',descriptor)

    def test_repeated_approved_plan_is_idempotent_and_rollback_preserves_data(self):
        class Runner:
            def __init__(self):self.calls=[]
            def run(self,args,**kwargs):self.calls.append(args)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);manifest,audit,config,plan,approval=self.fixture(root);runner=Runner()
            with patch.object(e.socket,'gethostname',return_value='LS5'),patch.object(e,'assert_components_offline'):
                first=e.InstallerEngine(manifest,plan,approval,audit,runner=runner).execute();calls=len(runner.calls)
                again=e.InstallerEngine(manifest,plan,approval,audit,runner=runner).execute()
                self.assertEqual(again['transaction_id'],first['transaction_id']);self.assertEqual(len(runner.calls),calls)
                data=Path(config['study']['data_dir']);(data/'learner.txt').write_text('new learner progress')
                newer=e.build_plan(manifest,audit,config,mode='disabled',components=['study'],release_label='second')
                accepted=dict(approval,plan_sha256=e.canonical_digest(newer))
                second=e.InstallerEngine(manifest,newer,accepted,audit,runner=runner).execute()
                self.assertTrue(Path(second['active']['backup']).is_dir())
                rollback=e.build_plan(manifest,audit,config,mode='disabled',components=['study'],action='rollback',rollback_transaction_id=second['transaction_id'])
                accepted=dict(approval,plan_sha256=e.canonical_digest(rollback))
                restored=e.InstallerEngine(manifest,rollback,accepted,audit,runner=runner).rollback()
            self.assertEqual(restored['active']['components']['study']['transaction_id'],first['transaction_id'])
            self.assertEqual((data/'learner.txt').read_text(),'new learner progress')
            self.assertTrue(restored['data_preserved'])

    def test_interrupted_preparation_resumes_and_rejects_modified_component(self):
        class Runner:
            fail=True
            def run(self,*args,**kwargs):
                if self.fail:raise OSError('fixture power loss')
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);manifest,audit,config,plan,approval=self.fixture(root);runner=Runner()
            with patch.object(e.socket,'gethostname',return_value='LS5'),patch.object(e,'assert_components_offline'):
                engine=e.InstallerEngine(manifest,plan,approval,audit,runner=runner)
                with self.assertRaises(OSError):engine.execute()
                transaction=engine.journal['transaction_id'];self.assertFalse((Path(config['app_root'])/'run/active.json').exists())
                self.assertEqual(engine.recover()['transactions'][0]['state'],'failed')
                runner.fail=False;resumed=e.InstallerEngine(manifest,plan,approval,audit,runner=runner).execute()
                self.assertEqual(resumed['transaction_id'],transaction)
                self.assertTrue(list((Path(config['app_root'])/'quarantine').iterdir()))
                descriptor=resumed['active']['components']['study']
                Path(descriptor['entrypoint']).write_text('tampered')
                with self.assertRaises(ValueError):engine._verify_component(descriptor)

    def test_managed_candidate_catalogue_blocks_before_mutation(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);manifest,audit,config,_,approval=self.fixture(root)
            manifest['release_ready']=False;manifest['components']['comfy']=dict(manifest['components']['study'])
            plan=e.build_plan(manifest,audit,config,mode='managed',components=['study','comfy'])
            approval.update(plan_sha256=e.canonical_digest(plan),manifest_sha256=e.canonical_digest(manifest))
            with patch.object(e.socket,'gethostname',return_value='LS5'):
                with self.assertRaisesRegex(ValueError,'release gate incomplete'):e.InstallerEngine(manifest,plan,approval,audit).execute()
            self.assertFalse(Path(config['app_root']).exists())

    def test_stale_lock_and_committed_pointer_recover_after_power_loss(self):
        class Runner:
            def run(self,*args,**kwargs):pass
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);manifest,audit,config,plan,approval=self.fixture(root)
            with patch.object(e.socket,'gethostname',return_value='LS5'),patch.object(e,'assert_components_offline'):
                installed=e.InstallerEngine(manifest,plan,approval,audit,runner=Runner()).execute()
                run=Path(config['app_root'])/'run';journal=run/'transactions'/(installed['transaction_id']+'.json')
                value=json.loads(journal.read_text());value['state']='activating';journal.write_text(json.dumps(value))
                (run/'lifecycle.lock').write_text('999999')
                with patch.object(e,'_pid_alive',return_value=False):result=e.InstallerEngine(manifest,plan,approval,audit,runner=Runner()).execute()
            self.assertEqual(result['state'],'committed');self.assertTrue(result['recovered_after_activation'])
            self.assertTrue(list(run.glob('lifecycle.lock.stale-*')))
    def test_managed_fixture_prepares_both_runtimes_and_requires_real_smoke_boundary(self):
        class Runner:
            def __init__(self):self.starts=[];self.stops=[]
            def run(self,*args,**kwargs):pass
            def start(self,args,**kwargs):self.starts.append(args);return object()
            def stop(self,handle):self.stops.append(handle)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);manifest,audit,config,_,approval=self.fixture(root)
            payload=root/'bundle'/'payload';source=payload/'comfy.zip'
            flags=' '.join(['--disable-auto-launch','--disable-api-nodes','--disable-all-custom-nodes','--extra-model-paths-config','--output-directory','--user-directory'])
            with zipfile.ZipFile(source,'w') as archive:
                archive.writestr('main.py','#fixture');archive.writestr('comfy/cli_args.py','# '+flags)
            source_artifact={'id':'comfy-source','local_path':'payload/comfy.zip','kind':'zip','size':source.stat().st_size,'sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
            model=payload/'fixture.safetensors';model.write_bytes(b'fixture model never executed')
            model_artifact={'id':'fixture-model','local_path':'payload/fixture.safetensors','kind':'model','size':model.stat().st_size,'sha256':hashlib.sha256(model.read_bytes()).hexdigest(),'license_id':'fixture-license','workflow_family':'sd1','hardware_requirements_reviewed':True,'min_ram_bytes':1,'min_vram_bytes':1}
            manifest['artifacts']+=[source_artifact,model_artifact]
            component=dict(manifest['components']['study']);component.update(artifact_ids=['comfy-source','fixture-model'],model_artifact_id='fixture-model',entrypoint='main.py')
            manifest['components']['comfy']=component;manifest['release_ready']=True
            manifest['licenses']=[{'id':'fixture-license','sha256':hashlib.sha256(b'fixture license').hexdigest()}]
            plan=e.build_plan(manifest,audit,config,mode='managed',components=['study','comfy'],device='cpu',cpu_opt_in=True,accepted_licenses=['fixture-license'],hardware_review={'audit_sha256':e.canonical_digest(audit),'component_compatibility':'approved'})
            approval.update(plan_sha256=e.canonical_digest(plan),manifest_sha256=e.canonical_digest(manifest),model_license_accepted=True)
            runner=Runner()
            def fixture_smoke(checkpoint,output,study,runner):
                output.mkdir(parents=True,exist_ok=True);png=output/'fixture.png';png.write_bytes(b'fixture image - verifier must reject')
                return {'state':'complete','proof_type':'fixture_comfy_http','checkpoint':checkpoint,'image_path':str(png),'sha256':hashlib.sha256(png.read_bytes()).hexdigest(),'prompt_id':'fixture','workflow_sha256':hashlib.sha256(b'workflow').hexdigest()}
            with patch.object(e.socket,'gethostname',return_value='LS5'),patch.object(e,'assert_components_offline'),patch.object(e,'external_health',return_value={'state':'reachable'}):
                engine=e.InstallerEngine(manifest,plan,approval,audit,runner=runner,smoke=fixture_smoke)
                with self.assertRaisesRegex(ValueError,'Actual Comfy HTTP generation proof'):engine.execute()
                self.assertFalse((Path(config['app_root'])/'run/active.json').exists())
                self.assertEqual(len(runner.starts),1);self.assertEqual(len(runner.stops),1)
                # Fixture-only transaction mechanics: bypass proof verifier explicitly.
                # This success is not production inference acceptance.
                with patch.object(e.InstallerEngine,'_validate_proof') as verification:
                    result=e.InstallerEngine(manifest,plan,approval,audit,runner=runner,smoke=fixture_smoke).execute()
                verification.assert_called_once();self.assertEqual(result['state'],'committed')
            study=result['active']['components']['study'];comfy=result['active']['components']['comfy']
            self.assertNotEqual(study['python'],comfy['python'])
            self.assertTrue(Path(comfy['checkpoint']).is_relative_to(Path(config['app_root'])/'models'))
            self.assertTrue((Path(study['root'])/'.study-managed-component.json').is_file())
            self.assertEqual(len(runner.starts),len(runner.stops))

            disabled=e.build_plan(manifest,audit,config,mode='disabled',components=['study'],release_label='disable-generation-only')
            accepted=dict(approval,plan_sha256=e.canonical_digest(disabled))
            with patch.object(e.socket,'gethostname',return_value='LS5'),patch.object(e,'assert_components_offline'):
                changed=e.InstallerEngine(manifest,disabled,accepted,audit,runner=runner).execute()
            retained=changed['active']['components']['comfy']
            self.assertEqual(retained['root'],comfy['root']);self.assertEqual(retained['mode'],'managed')
            self.assertFalse(retained['enabled']);self.assertEqual(changed['active']['comfy_mode'],'disabled')
    def test_rollback_reads_current_pointer_only_after_lifecycle_lock(self):
        from contextlib import contextmanager
        class Runner:
            def run(self,*args,**kwargs):pass
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);manifest,audit,config,plan,approval=self.fixture(root)
            with patch.object(e.socket,'gethostname',return_value='LS5'),patch.object(e,'assert_components_offline'):
                e.InstallerEngine(manifest,plan,approval,audit,runner=Runner()).execute()
                second=e.build_plan(manifest,audit,config,release_label='second')
                installed=e.InstallerEngine(manifest,second,dict(approval,plan_sha256=e.canonical_digest(second)),audit,runner=Runner()).execute()
                active=Path(config['app_root'])/'run/active.json'
                @contextmanager
                def lock_with_concurrent_update(config):
                    value=json.loads(active.read_text());value['components']['comfy']={'owner':'external','mode':'external','enabled':False,'checkpoint_name':'concurrent-external'}
                    active.write_text(json.dumps(value));yield
                rollback=e.build_plan(manifest,audit,config,action='rollback',rollback_transaction_id=installed['transaction_id'])
                with patch.object(e,'transaction_lock',lock_with_concurrent_update):
                    result=e.InstallerEngine(manifest,rollback,dict(approval,plan_sha256=e.canonical_digest(rollback)),audit).rollback()
            self.assertEqual(result['active']['components']['comfy'].get('checkpoint_name'),'concurrent-external')

    def test_prepared_runtime_rejects_unlisted_import_hook(self):
        class Runner:
            def run(self,*args,**kwargs):pass
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);manifest,audit,config,plan,approval=self.fixture(root)
            with patch.object(e.socket,'gethostname',return_value='LS5'),patch.object(e,'assert_components_offline'):
                engine=e.InstallerEngine(manifest,plan,approval,audit,runner=Runner());result=engine.execute()
                component=result['active']['components']['study'];hook=Path(component['root'])/'runtime/Lib/site-packages/extra.pth';hook.write_text('import sitecustomize')
                with self.assertRaises(ValueError):engine._verify_component(component)

    def test_two_stale_lock_reclaimers_cannot_steal_new_live_lock(self):
        import threading
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);run=root/'run';run.mkdir();lock=run/'lifecycle.lock';lock.write_text('999999')
            before_a=threading.Event();before_b=threading.Event();allow_a=threading.Event();inside_a=threading.Event();release_a=threading.Event()
            counts={'active':0,'maximum':0};counter_lock=threading.Lock();errors=[];replace=e.os.replace
            def intercepted(source,target):
                if Path(source)==lock:
                    if threading.current_thread().name=='reclaimer-a':before_a.set();allow_a.wait(2)
                    elif threading.current_thread().name=='reclaimer-b':before_b.set();inside_a.wait(2)
                return replace(source,target)
            def worker():
                try:
                    with e.transaction_lock({'app_root':str(root)}):
                        with counter_lock:counts['active']+=1;counts['maximum']=max(counts['maximum'],counts['active'])
                        if threading.current_thread().name=='reclaimer-a':inside_a.set();release_a.wait(2)
                        with counter_lock:counts['active']-=1
                except (ValueError,OSError) as exc:errors.append(exc)
            with patch.object(e,'_pid_alive',side_effect=lambda pid:pid!=999999),patch.object(e.os,'replace',side_effect=intercepted):
                a=threading.Thread(target=worker,name='reclaimer-a');b=threading.Thread(target=worker,name='reclaimer-b')
                a.start();self.assertTrue(before_a.wait(1));b.start();crossed_reclamation_guard=before_b.wait(.2);allow_a.set();self.assertTrue(inside_a.wait(1));time.sleep(.2);release_a.set();a.join(3);b.join(3)
            self.assertFalse(a.is_alive());self.assertFalse(b.is_alive());self.assertEqual(counts['maximum'],1)
            self.assertFalse(crossed_reclamation_guard,'second reclaimer inspected stale lock before exclusive guard released')

    def test_whole_data_backup_checks_all_owned_writers_but_allows_external(self):
        config={'app_root':'fixture'}
        with patch.object(e,'assert_components_offline') as check:
            e.assert_data_writers_offline(config,{'components':{'comfy':{'owner':e.OWNER,'mode':'managed'}}})
            check.assert_called_once_with(config,['study','comfy'])
            check.reset_mock()
            e.assert_data_writers_offline(config,{'components':{'comfy':{'owner':'external','mode':'external'}}})
            check.assert_called_once_with(config,['study'])

    def test_parent_proof_boundary_invokes_owned_python_verification(self):
        class Runner:
            def run(self,args,**kwargs):
                if '--verify-only' in args:raise ValueError('Pillow rejected malformed fixture PNG')
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);manifest,audit,config,plan,approval=self.fixture(root)
            with patch.object(e.socket,'gethostname',return_value='LS5'),patch.object(e,'assert_components_offline'):
                engine=e.InstallerEngine(manifest,plan,approval,audit,runner=Runner());result=engine.execute()
            engine._attestation_study=result['active']['components']['study']
            output=Path(config['app_root'])/'staging'/'proof';output.mkdir(parents=True)
            image=output/'invalid.png';image.write_bytes(b'not a PNG but self-consistent hash')
            proof={'state':'complete','proof_type':'real_comfy_http','checkpoint':'fixture.safetensors','image_path':str(image),'sha256':hashlib.sha256(image.read_bytes()).hexdigest(),'prompt_id':'12345678-1234-1234-1234-123456789012','workflow_sha256':'a'*64}
            (output/'proof.json').write_text(json.dumps(proof))
            with self.assertRaisesRegex(ValueError,'Pillow rejected'):engine._validate_proof(proof,'fixture.safetensors',output)
    def test_backup_rechecks_owned_comfy_and_never_blocks_external_writer(self):
        class Runner:
            def run(self,*args,**kwargs):pass
        for mode in ('managed','external'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);manifest,audit,config,plan,approval=self.fixture(root)
                with patch.object(e.socket,'gethostname',return_value='LS5'),patch.object(e,'assert_components_offline'):
                    e.InstallerEngine(manifest,plan,approval,audit,runner=Runner()).execute()
                active=Path(config['app_root'])/'run/active.json';value=json.loads(active.read_text())
                value['components']['comfy']={'mode':mode,'owner':e.OWNER if mode=='managed' else 'external','enabled':False}
                active.write_text(json.dumps(value));before=active.read_bytes()
                def offline(config,components):
                    if 'comfy' in components:raise ValueError('owned shared-data writer is running')
                updated=e.build_plan(manifest,audit,config,mode=mode,components=['study'],release_label='writer-check')
                accepted=dict(approval,plan_sha256=e.canonical_digest(updated))
                with patch.object(e.socket,'gethostname',return_value='LS5'),patch.object(e,'assert_components_offline',side_effect=offline),patch.object(e,'external_health',return_value={'state':'reachable'}):
                    engine=e.InstallerEngine(manifest,updated,accepted,audit,runner=Runner())
                    if mode=='managed':
                        with self.assertRaisesRegex(ValueError,'shared-data writer'):engine.execute()
                        self.assertEqual(active.read_bytes(),before)
                    else:self.assertEqual(engine.execute()['state'],'committed')

    def test_writer_starting_after_backup_blocks_activation(self):
        class Runner:
            def run(self,*args,**kwargs):pass
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);manifest,audit,config,plan,approval=self.fixture(root)
            with patch.object(e.socket,'gethostname',return_value='LS5'),patch.object(e,'assert_components_offline'):
                e.InstallerEngine(manifest,plan,approval,audit,runner=Runner()).execute()
            active=Path(config['app_root'])/'run/active.json';before=active.read_bytes();started={'value':False}
            backup=e.ops.backup_data
            def copy_then_writer(*args):
                result=backup(*args);started['value']=True;return result
            def offline(config,components):
                if started['value']:raise ValueError('writer started before activation')
            updated=e.build_plan(manifest,audit,config,release_label='activation-recheck')
            with patch.object(e.socket,'gethostname',return_value='LS5'),patch.object(e,'assert_components_offline',side_effect=offline),patch.object(e.ops,'backup_data',side_effect=copy_then_writer):
                with self.assertRaisesRegex(ValueError,'before activation'):e.InstallerEngine(manifest,updated,dict(approval,plan_sha256=e.canonical_digest(updated)),audit,runner=Runner()).execute()
            self.assertEqual(active.read_bytes(),before)
    def test_pip_commands_are_isolated_and_pin_the_owned_destination(self):
        class Runner:
            def __init__(self):self.calls=[]
            def run(self,args,**kwargs):self.calls.append(list(map(str,args)))
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);manifest,audit,config,plan,approval=self.fixture(root);runner=Runner()
            with patch.object(e.socket,'gethostname',return_value='LS5'),patch.object(e,'assert_components_offline'),patch.dict(e.os.environ,{'PIP_TARGET':str(root/'outside'),'PIP_INDEX_URL':'https://evil.example/simple'}):
                result=e.InstallerEngine(manifest,plan,approval,audit,runner=runner).execute()
            component=result['active']['components']['study'];target=str(Path(component['root'])/'runtime/Lib/site-packages')
            for command in runner.calls:
                self.assertIn('--isolated',command);self.assertIn('--disable-pip-version-check',command)
            install=next(command for command in runner.calls if 'install' in command)
            self.assertIn('--no-cache-dir',install)
            self.assertEqual(install[install.index('--target')+1],target)
            self.assertFalse((root/'outside').exists())

    def test_default_runner_scrubs_hostile_pip_environment_without_executing(self):
        with tempfile.TemporaryDirectory() as folder,patch.dict(e.os.environ,{'PIP_TARGET':'outside','PIP_PREFIX':'outside','PIP_ROOT':'outside','PIP_INDEX_URL':'https://evil.example/simple','PIP_CONFIG_FILE':'hostile.ini'}),patch.object(e.subprocess,'run') as child:
            e.Runner().run(['owned-python','-I','-B','-m','pip','--isolated','check'],cwd=Path(folder),timeout=1,log_path=Path(folder)/'fixture.log')
            environment=child.call_args.kwargs['env']
            self.assertEqual(environment.get('PIP_CONFIG_FILE'),e.os.devnull)
            self.assertEqual({key for key in environment if key.upper().startswith('PIP_')},{'PIP_CONFIG_FILE'})
