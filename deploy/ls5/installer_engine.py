"""Approval-bound LS5 installation transactions; importing performs no mutations.

Only pinned payloads enter inactive owned versions. No system Python, drivers,
external process control, arbitrary plan commands, or pip network resolution.
"""
import copy,hashlib,json,os,re,socket,subprocess,time,uuid
from datetime import datetime,timezone
from contextlib import contextmanager,ExitStack
from pathlib import Path,PurePosixPath
import portable_ops as ops
from resumable_download import atomic_json,download,extract_zip,_safe_ancestors

OWNER='study-installer'

def canonical_digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()

def validate_manifest(manifest,**kwargs):
    from manifest_validation import validate_manifest as validate
    return validate(manifest,**kwargs)

def _serial(value):
    if isinstance(value,Path):return str(value)
    if isinstance(value,dict):return {key:_serial(item) for key,item in value.items()}
    if isinstance(value,(tuple,list)):return [_serial(item) for item in value]
    return value

def validate_audit(audit,now=None):
    now=time.time() if now is None else now
    if audit.get('schema_version')!=1 or audit.get('status')!='COLLECTED_READ_ONLY' or str(audit.get('hostname','')).upper()!='LS5':raise ValueError('A real LS5 read-only audit is required')
    try:
        timestamp=datetime.fromisoformat(audit['collected_at_utc'].replace('Z','+00:00'))
        if timestamp.tzinfo is None:raise ValueError('Audit needs timezone')
        collected=timestamp.timestamp()
    except (ValueError,KeyError,TypeError):raise ValueError('Audit collection time is missing or invalid')
    if not -60<=now-collected<=1800:raise ValueError('LS5 audit is stale; collect again before installing')
    for key in ('os','cpu','ram','disks'):
        if not isinstance(audit.get(key),list) or not audit[key] or not all(isinstance(item,dict) for item in audit[key]):raise ValueError('Audit lacks '+key)
    system=audit['os'][0]
    if 'windows 11 pro' not in str(system.get('Caption','')).lower() or int(system.get('BuildNumber',0))<22000 or '64' not in str(system.get('OSArchitecture','')):raise ValueError('Audited target must be Windows 11 Pro x64')
    if not audit['cpu'][0].get('Name') or int(audit['ram'][0].get('TotalPhysicalMemory',0))<=0:raise ValueError('CPU/RAM audit is incomplete')
    if not isinstance(audit.get('gpu'),dict) or not isinstance(audit.get('listening_ports_8188_8766'),list):raise ValueError('GPU/VRAM/ports must be audited, even when no GPU is selected')
    if audit.get('changes_performed') not in ([],None):raise ValueError('Read-only audit reported mutations')
    return copy.deepcopy(audit)

def build_plan(manifest,audit,config,mode='disabled',components=('study',),**options):
    validate_audit(audit)
    if mode not in ('managed','external','disabled') or not components or set(components)-{'study','comfy'} or len(set(components))!=len(components):raise ValueError('Select valid mode and components')
    if mode!='managed' and 'comfy' in components:raise ValueError('External/Disabled modes install Study only')
    ids=set()
    for component in components:
        spec=manifest.get('components',{}).get(component,{})
        ids.update(spec.get('artifact_ids',[]));ids.update(spec.get('wheel_ids',[]))
        ids.update(spec[key] for key in ('python_artifact_id','pip_artifact_id','model_artifact_id') if spec.get(key))
    artifacts=[item for item in manifest.get('artifacts',[]) if item.get('id') in ids]
    result={'schema_version':1,'action':'install','target_host':'LS5','manifest_sha256':canonical_digest(manifest),'audit_sha256':canonical_digest(audit),'created_at':audit['collected_at_utc'],'mode':mode,'components':list(components),'config':_serial(config),'artifact_ids':sorted(ids),'download_bytes':sum(item.get('size',0) for item in artifacts),'approved_download_bytes':sum(item.get('size',0) for item in artifacts),'accepted_licenses':[]}
    result.update(_serial(options))
    return result

def _local(path):
    raw=str(path)
    candidate=Path(raw)
    if not candidate.is_absolute() or '..' in candidate.parts or raw.startswith(('\\\\','//')):raise ValueError('Installer paths must be absolute local paths without traversal')
    _safe_ancestors(candidate)
    resolved=candidate.resolve()
    if resolved==Path(resolved.anchor) or str(resolved).startswith(('\\\\','//')):raise ValueError('Use a dedicated local installer directory')
    return resolved

def assert_components_offline(config,components):
    # External Comfy may be running: only our selected services must be offline.
    for component in components:
        if (Path(config['app_root'])/'run'/(component+'.json')).exists():raise ValueError('Stop the owned '+component+' service before installation')
        port=8766 if component=='study' else 8188
        with socket.socket() as connection:
            connection.settimeout(.5)
            if connection.connect_ex(('127.0.0.1',port))==0:raise ValueError('Selected service port is occupied; no process will be stopped automatically')

def external_health():
    import http.client
    connection=http.client.HTTPConnection('127.0.0.1',8188,timeout=2)
    try:
        connection.request('GET','/system_stats');response=connection.getresponse()
        raw=response.read(2_000_001)
        if response.status!=200 or len(raw)>2_000_000:raise ValueError('External API health unavailable')
        result=json.loads(raw)
        if not isinstance(result,dict):raise ValueError('Invalid external API health')
        return {'state':'reachable','system_stats':result,'inference_verified':False}
    except (OSError,ValueError,http.client.HTTPException):return {'state':'unavailable','inference_verified':False}
    finally:connection.close()

def assert_data_writers_offline(config,active):
    """Whole-data snapshots include all owned services, not only updated code."""
    writers=['study']
    comfy=(active or {}).get('components',{}).get('comfy',{})
    if (comfy.get('owner')==OWNER and comfy.get('mode')=='managed') or (Path(config['app_root'])/'run/comfy.json').exists():
        writers.append('comfy')
    assert_components_offline(config,writers)

def _pid_alive(pid):
    if pid==os.getpid():return True
    if os.name=='nt':
        import ctypes
        from ctypes import wintypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        kernel.OpenProcess.restype=wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
        kernel.GetExitCodeProcess.restype=wintypes.BOOL
        kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        handle=kernel.OpenProcess(0x1000,False,pid)
        if not handle:return ctypes.get_last_error()!=87  # access denied/unknown stays locked
        try:
            code=wintypes.DWORD()
            if not kernel.GetExitCodeProcess(handle,ctypes.byref(code)):return True
            return code.value==259
        finally:kernel.CloseHandle(handle)
    try:os.kill(pid,0);return True
    except ProcessLookupError:return False
    except PermissionError:return True

@contextmanager
def _reclamation_guard(directory):
    """Kernel-held byte/file lock; crash release does not depend on a PID file."""
    directory=Path(directory);_safe_ancestors(directory);directory.mkdir(parents=True,exist_ok=True)
    path=directory/'.lifecycle-reclaim.guard';_safe_ancestors(path)
    with path.open('a+b') as stream:
        stream.seek(0,2)
        if stream.tell()==0:stream.write(b'0');stream.flush();os.fsync(stream.fileno())
        stream.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as exc:raise ValueError('Another lifecycle lock acquisition is in progress') from exc
        try:yield
        finally:
            stream.seek(0)
            if os.name=='nt':msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(stream.fileno(),fcntl.LOCK_UN)

@contextmanager
def transaction_lock(config):
    # Caller performs target/approval validation before entering this mutating API.
    directory=Path(config['app_root'])/'run';lock=directory/'lifecycle.lock'
    with ExitStack() as held:
        with _reclamation_guard(directory):
            if lock.exists():
                _safe_ancestors(lock)
                original=lock.read_bytes();stamp=lock.stat()
                try:pid=int(original.decode())
                except ValueError:raise ValueError('Unrecognized lifecycle lock; manual inspection required')
                if pid<=0 or _pid_alive(pid):raise ValueError('Another lifecycle operation is active or cannot be proven stopped')
                if lock.read_bytes()!=original or lock.stat().st_mtime_ns!=stamp.st_mtime_ns:raise ValueError('Lifecycle lock changed during recovery')
                os.replace(lock,lock.with_name('lifecycle.lock.stale-'+uuid.uuid4().hex))
            # New PID lock is acquired while reclamation is still exclusively held.
            held.enter_context(ops.lifecycle_lock(config))
        yield


def _child_environment():
    # Python -I does not isolate pip options/config. PIP_CONFIG_FILE=devnull is
    # pip's explicit all-config disable switch, including with --isolated.
    environment={key:value for key,value in os.environ.items() if not key.upper().startswith('PIP')}
    environment.update(PIP_CONFIG_FILE=os.devnull,PYTHONNOUSERSITE='1')
    return environment

class Runner:
    """No shell, no inherited pip indexes, and only directly owned child handles."""
    def run(self,argv,*,cwd,timeout,log_path):
        env=_child_environment()
        with Path(log_path).open('ab') as log:
            subprocess.run(list(map(str,argv)),cwd=cwd,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,timeout=timeout,check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    def start(self,argv,*,cwd,log_path):
        log=Path(log_path).open('ab')
        try:
            process=subprocess.Popen(list(map(str,argv)),cwd=cwd,env=_child_environment(),stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            return (process,log)
        except BaseException:log.close();raise
    def is_running(self,handle):return handle[0].poll() is None
    def stop(self,handle):
        process,log=handle
        try:
            if process.poll() is None:
                process.terminate()
                try:process.wait(15)
                except subprocess.TimeoutExpired:process.kill();process.wait(15)
        finally:log.close()

def _default_smoke(checkpoint,output_dir,study,runner):
    output_dir.mkdir(parents=True,exist_ok=True)
    runner.run([study['python'],'-I','-B',str(Path(study['code'])/'deploy/ls5/comfy_smoke.py'),'--checkpoint',checkpoint,'--output',str(output_dir),'--timeout','300'],cwd=Path(study['code']),timeout=330,log_path=output_dir/'probe.log')
    return json.loads((output_dir/'proof.json').read_text(encoding='utf-8'))

class InstallerEngine:
    def __init__(self,manifest,plan,approval,audit,*,runner=None,downloader=None,smoke=None):
        self.manifest=copy.deepcopy(manifest);self.plan=copy.deepcopy(plan);self.approval=copy.deepcopy(approval);self.audit=copy.deepcopy(audit)
        self.runner=runner or Runner();self.downloader=downloader or download;self.smoke=smoke or _default_smoke
        self.journal=None;self.journal_file=None

    def _authorize(self,action):
        ops.target_guard({'target_host':self.plan.get('target_host')})
        validate_audit(self.audit)
        approval=self.approval;plan=self.plan
        if plan.get('schema_version')!=1 or plan.get('action')!=action or approval.get('approved') is not True or approval.get('schema_version')!=1:raise ValueError('Explicit approval for this operation is required')
        if plan.get('audit_sha256')!=canonical_digest(self.audit) or plan.get('manifest_sha256')!=canonical_digest(self.manifest) or approval.get('manifest_sha256')!=canonical_digest(self.manifest) or approval.get('plan_sha256')!=canonical_digest(plan):raise ValueError('Audit, manifest or approved plan changed')
        expiry=approval.get('expires_at')
        if type(expiry) not in (int,float) or not time.time()<expiry<=time.time()+86400:raise ValueError('Approval expired or invalid')
        if plan.get('mode') not in ('managed','external','disabled') or not plan.get('components') or set(plan['components'])-{'study','comfy'}:raise ValueError('Invalid installation selection')
        if plan['mode']!='managed' and 'comfy' in plan['components']:raise ValueError('External/Disabled Comfy cannot be installed or changed')
        self.validated=validate_manifest(self.manifest,plan=plan,hardware=self.audit)
        self.config=copy.deepcopy(plan['config']);ops.target_guard(self.config)
        self.root=_local(self.config['app_root']);self.data=_local(self.config['study']['data_dir']);self.bundle=_local(self.config.get('bundle_root',Path(__file__).resolve().parents[2]))
        for name in ('releases','staging','run','cache','models','backups','quarantine'):
            managed=self.root/name
            _safe_ancestors(managed)
            if ops.inside(self.data,managed) or ops.inside(managed,self.data):raise ValueError('User data overlaps installer-owned directories')
        if self.data==self.root:raise ValueError('Use a distinct data directory')
        for service,port in (('study',8766),('comfy',8188)):
            item=self.config.get(service,{})
            if item.get('host')!='127.0.0.1' or item.get('port')!=port:raise ValueError('Only fixed loopback service ports are permitted')
        selected=set(plan.get('artifact_ids',[]));self.artifacts={a['id']:a for a in self.manifest['artifacts'] if a['id'] in selected}
        needed=set()
        for component in plan['components']:
            spec=self.manifest['components'][component]
            needed.update(spec.get('artifact_ids',[]));needed.update(spec.get('wheel_ids',[]))
            needed.update(spec[key] for key in ('python_artifact_id','pip_artifact_id','model_artifact_id') if spec.get(key))
        if needed!=selected or set(self.artifacts)!=selected:raise ValueError('Plan must bind the full selected component manifest')
        if plan['approved_download_bytes']<sum(a['size'] for a in self.artifacts.values()):raise ValueError('Artifact bytes exceed approved budget')
        if sum(a['size'] for a in self.artifacts.values())>100_000_000 and approval.get('large_download_approved') is not True:raise ValueError('Large downloads require separate explicit approval')
        models=[a for a in self.artifacts.values() if a['kind']=='model']
        if models and (approval.get('model_license_accepted') is not True or any(a.get('license_id') not in plan.get('accepted_licenses',[]) for a in models)):raise ValueError('Model source/license acceptance is required')
        disk=[d for d in self.audit['disks'] if str(d.get('DeviceID','')).rstrip('\\/').casefold()==self.root.anchor.rstrip('\\/').casefold()]
        self.disk_free=int(disk[0].get('FreeSpace',0)) if disk else 0
        if not disk or self.disk_free<sum(a['size'] for a in self.artifacts.values())*3+1_000_000_000:raise ValueError('Audited target disk has insufficient staging/rollback headroom')
        return self.config

    def _save(self,state,**values):
        self.journal.update(state=state,updated_at=time.time(),**values);atomic_json(self.journal_file,self.journal)

    def _artifact(self,artifact,cache):
        if artifact.get('local_path'):
            name=PurePosixPath(artifact['local_path'])
            if name.is_absolute() or '..' in name.parts or ':' in str(name) or '\\' in str(name):raise ValueError('Unsafe bundled artifact path')
            path=self.bundle/Path(*name.parts);_safe_ancestors(path)
            if not ops.inside(path,self.bundle) or not path.is_file() or path.stat().st_size!=artifact['size'] or ops.digest(path)!=artifact['sha256']:raise ValueError('Bundled artifact hash/size mismatch')
            return path
        name=urllib_name(artifact)
        return self.downloader(artifact,cache/(artifact['sha256']+'-'+name),self.manifest['allowed_hosts'])

    def _preflight_space(self,files):
        import zipfile
        expanded=0
        for name in self.plan['components']:
            spec=self.manifest['components'][name]
            ids=set(spec['artifact_ids'])|set(spec['wheel_ids'])|{spec['python_artifact_id'],spec['pip_artifact_id']}
            for key in ids:
                if self.artifacts[key]['kind'] in ('zip','wheel','python'):
                    with zipfile.ZipFile(files[key]) as archive:
                        members=archive.infolist()
                        if len(members)>50000:raise ValueError('Archive file count exceeds preflight bound')
                        size=sum(member.file_size for member in members)
                        if size>8_000_000_000:raise ValueError('Archive expansion exceeds preflight bound')
                        expanded+=size
        backup_bytes=sum(path.stat().st_size for path in ops.safe_files(self.data)) if self.data.exists() else 0
        needed=expanded+sum(item['size'] for item in self.artifacts.values())*2+backup_bytes+1_000_000_000
        if needed>self.disk_free:raise ValueError('Verified archive expansion and backup exceed audited disk headroom')

    def _component(self,name,files,transaction):
        spec=self.manifest['components'][name]
        destination=self.root/'releases'/transaction/name
        _safe_ancestors(destination)
        if destination.exists():
            marker=destination/'.study-managed-component.json'
            if not marker.is_file() or json.loads(marker.read_text()).get('owner')!=OWNER:raise ValueError('Unowned incomplete component directory refused')
            ops.safe_files(destination)
            quarantine=self.root/'quarantine';quarantine.mkdir(exist_ok=True)
            os.replace(destination,quarantine/(transaction+'-'+name+'-'+uuid.uuid4().hex))
        destination.mkdir(parents=True)
        atomic_json(destination/'.study-managed-component.json',{'schema_version':1,'owner':OWNER,'transaction_id':transaction,'component':name,'manifest_sha256':canonical_digest(self.manifest),'component_root':str(destination)})
        runtime_artifact=self.artifacts[spec['python_artifact_id']]
        if runtime_artifact.get('runtime_kind',spec.get('runtime_kind'))!='embedded':raise ValueError('Only owned embedded runtimes are supported')
        runtime=destination/'runtime';extract_zip(files[runtime_artifact['id']],runtime,archive_root=runtime_artifact.get('archive_root'))
        python=runtime/relative_member(runtime_artifact.get('python_executable','python.exe'))
        if not python.is_file():raise ValueError('Pinned runtime executable is missing')
        pths=list(runtime.glob('python*._pth'))
        if len(pths)!=1:raise ValueError('Embedded runtime path policy missing or ambiguous')
        entries=[line for line in pths[0].read_text().splitlines() if line.strip() and not line.lstrip().startswith('#') and line.strip()!='import site']
        if any(line.startswith('import ') or Path(line).is_absolute() or '..' in Path(line).parts for line in entries):raise ValueError('Unexpected embedded runtime path policy')
        pths[0].write_text('\n'.join(entries+list(dict.fromkeys([str(destination/'code'),str(destination/'code'/relative_member(spec['entrypoint']).parent),str(destination/'code'/'prototype')] if name=='study' else [str(destination/'code'),str(destination/'code'/relative_member(spec['entrypoint']).parent)]))+['Lib/site-packages','import site'])+'\n',encoding='utf-8')
        pip=spec['pip_artifact_id'];extract_zip(files[pip],runtime/'Lib/site-packages')
        code=destination/'code';source_ids=[key for key in spec['artifact_ids'] if self.artifacts[key]['kind']=='zip']
        if len(source_ids)!=1:raise ValueError('Exactly one pinned source archive per component is required')
        source=self.artifacts[source_ids[0]];extract_zip(files[source['id']],code,archive_root=source.get('archive_root'))
        entrypoint=code/relative_member(spec['entrypoint'])
        if not entrypoint.is_file():raise ValueError('Pinned component entry point is missing')
        wheelhouse=destination/'wheelhouse';wheelhouse.mkdir()
        import shutil
        for key in spec['wheel_ids']:
            artifact=self.artifacts[key];filename=artifact.get('filename') or urllib_name(artifact)
            if not filename.endswith('.whl') or Path(filename).name!=filename:raise ValueError('Reviewed wheel filename is required')
            shutil.copyfile(files[key],wheelhouse/filename)
        requirements=destination/'requirements.lock'
        requirements.write_text(''.join(row['distribution']+'=='+row['version']+' --hash=sha256:'+self.artifacts[row['artifact_id']]['sha256']+'\n' for row in spec['requirements_lock']),encoding='utf-8')
        self.runner.run([python,'-I','-B','-m','pip','--isolated','--disable-pip-version-check','install','--no-cache-dir','--target',runtime/'Lib/site-packages','--no-index','--no-deps','--no-compile','--only-binary=:all:','--require-hashes','--find-links',wheelhouse,'-r',requirements],cwd=destination,timeout=1800,log_path=destination/'pip-install.log')
        self.runner.run([python,'-I','-B','-m','pip','--isolated','--disable-pip-version-check','check'],cwd=destination,timeout=120,log_path=destination/'pip-check.log')
        if name=='comfy':
            (destination/'extra_model_paths.yaml').write_text('study:\n  base_path: '+json.dumps(str(self.root/'models'))+'\n  checkpoints: checkpoints\n',encoding='utf-8')
        atomic_json(destination/'component-manifest.json',{'schema_version':1,'component':name,'manifest_sha256':canonical_digest(self.manifest),'artifacts':[{key:item[key] for key in ('id','size','sha256')} for item in self.artifacts.values() if item['id'] in set(spec['artifact_ids'])|set(spec['wheel_ids'])|{spec['python_artifact_id'],spec['pip_artifact_id']}],'files':[{'path':file.relative_to(destination).as_posix(),'sha256':ops.digest(file),'size':file.stat().st_size} for file in ops.safe_files(destination)]})
        return {'owner':OWNER,'mode':'managed','root':str(destination),'code':str(code),'python':str(python),'entrypoint':str(entrypoint),'manifest_sha256':canonical_digest(self.manifest),'transaction_id':transaction,'component_manifest_sha256':ops.digest(destination/'component-manifest.json')}

    def _verify_component(self,item):
        root=_local(item['root'])
        if item.get('owner')!=OWNER or item.get('mode')!='managed' or not ops.inside(root,self.root/'releases'):raise ValueError('Unowned component cannot be used by installer')
        actual={file.relative_to(root).as_posix() for file in ops.safe_files(root)}
        manifest=root/'component-manifest.json'
        if not manifest.is_file() or ops.digest(manifest)!=item.get('component_manifest_sha256'):raise ValueError('Prepared component manifest changed')
        marker=json.loads((root/'.study-managed-component.json').read_text())
        if marker.get('owner')!=OWNER or marker.get('transaction_id')!=item['transaction_id'] or marker.get('component_root')!=str(root):raise ValueError('Prepared component owner marker mismatch')
        entries=json.loads(manifest.read_text())['files']
        listed=[entry['path'] for entry in entries]
        if len(set(listed))!=len(listed) or actual!=set(listed)|{'component-manifest.json'}:raise ValueError('Unlisted or missing prepared component files')
        for entry in entries:
            path=root/relative_member(entry['path'])
            if not path.is_file() or path.stat().st_size!=entry['size'] or ops.digest(path)!=entry['sha256']:raise ValueError('Prepared component contents changed')

    def _proof(self,descriptor,study,stage):
        spec=self.manifest['components']['comfy'];model=self.artifacts.get(spec.get('model_artifact_id'))
        if not model:raise ValueError('Managed Comfy needs a pinned approved model')
        models=self.root/'models'/'checkpoints';_safe_ancestors(models);models.mkdir(parents=True,exist_ok=True)
        source=self._files[model['id']];checkpoint=model['sha256'][:12]+'-'+urllib_name(model)
        target=models/checkpoint
        if target.exists():
            if not target.is_file() or ops.digest(target)!=model['sha256']:raise ValueError('Existing model cache mismatch; preserved, never overwritten')
        else:
            import shutil
            temporary=models/(checkpoint+'.tmp-'+uuid.uuid4().hex);shutil.copyfile(source,temporary)
            if ops.digest(temporary)!=model['sha256']:raise ValueError('Model cache copy hash mismatch')
            os.replace(temporary,target)
        cli=Path(descriptor['code'])/'comfy/cli_args.py'
        flags=['--disable-auto-launch','--disable-api-nodes','--disable-all-custom-nodes','--extra-model-paths-config','--output-directory','--user-directory']
        if not cli.is_file() or any(flag not in cli.read_text(encoding='utf-8') for flag in flags):raise ValueError('Pinned Comfy source lacks required isolation flags')
        paths=Path(descriptor['root'])/'extra_model_paths.yaml'
        expected_paths='study:\n  base_path: '+json.dumps(str(self.root/'models'))+'\n  checkpoints: checkpoints\n'
        if not paths.is_file() or paths.read_text(encoding='utf-8')!=expected_paths:raise ValueError('Managed model path configuration changed')
        argv=[descriptor['python'],'-I','-B',descriptor['entrypoint'],'--listen','127.0.0.1','--port','8188',*flags[:3],'--extra-model-paths-config',str(paths),'--output-directory',str(stage/'comfy-output'),'--user-directory',str(stage/'comfy-user')]
        if self.plan.get('device')=='cpu':argv+=['--cpu']
        handle=self.runner.start(argv,cwd=Path(descriptor['code']),log_path=stage/'comfy.log')
        try:
            deadline=time.monotonic()+120
            while external_health()['state']!='reachable':
                if hasattr(self.runner,'is_running') and not self.runner.is_running(handle):raise ValueError('Owned Comfy process exited before readiness')
                if time.monotonic()>=deadline:raise TimeoutError('Owned Comfy readiness deadline exceeded')
                time.sleep(.25)
            proof=self.smoke(checkpoint,stage/'smoke',study,self.runner)
        finally:self.runner.stop(handle)
        self._attestation_study=study
        self._validate_proof(proof,checkpoint,stage/'smoke')
        descriptor.update(checkpoint=str(target),checkpoint_name=checkpoint,extra_model_paths=str(paths),smoke=proof,enabled=True)

    def _validate_proof(self,proof,checkpoint,output):
        if proof.get('state')!='complete' or proof.get('proof_type')!='real_comfy_http' or proof.get('checkpoint')!=checkpoint:raise ValueError('Actual Comfy HTTP generation proof is required before enabling Study')
        path=Path(proof.get('image_path',''))
        _safe_ancestors(path)
        if not ops.inside(path,output) or not path.is_file() or path.stat().st_size>8_000_000 or ops.digest(path)!=proof.get('sha256') or not proof.get('prompt_id') or not re.fullmatch('[0-9a-f]{64}',proof.get('workflow_sha256','')):raise ValueError('Comfy smoke PNG proof is incomplete or corrupt')
        try:uuid.UUID(proof['prompt_id'])
        except (ValueError,TypeError,AttributeError):raise ValueError('Comfy prompt ID must be a UUID')
        stored=Path(output)/'proof.json';_safe_ancestors(stored)
        if not stored.is_file() or stored.stat().st_size>1_000_000 or canonical_digest(json.loads(stored.read_text(encoding='utf-8')))!=canonical_digest(proof):raise ValueError('Returned proof differs from the saved attestation')
        study=getattr(self,'_attestation_study',None)
        if not study:raise ValueError('Verified Study runtime required to independently attest inference')
        self._verify_component(study)
        verifier=Path(study['code'])/'deploy/ls5/comfy_smoke.py'
        self.runner.run([study['python'],'-I','-B',verifier,'--verify-only','--checkpoint',checkpoint,'--output',Path(output)],cwd=Path(study['code']),timeout=60,log_path=Path(output)/'proof-verification.log')
        # The owned child checks the expected workflow and fully decodes PNG bytes.
        if canonical_digest(json.loads(stored.read_text(encoding='utf-8')))!=canonical_digest(proof) or ops.digest(path)!=proof['sha256']:raise ValueError('Attestation changed during independent verification')

    def execute(self):
        self._authorize('install')
        assert_components_offline(self.config,self.plan['components'])
        # Every path check and approval above precedes the first directory write.
        self.root.mkdir(parents=True,exist_ok=True)
        with transaction_lock(self.config):
            run=self.root/'run';transactions=run/'transactions';_safe_ancestors(transactions);transactions.mkdir(exist_ok=True)
            matching=[]
            for file in transactions.glob('*.json'):
                if '.previous' in file.stem:continue
                _safe_ancestors(file)
                value=json.loads(file.read_text(encoding='utf-8'))
                if value.get('plan_sha256')==canonical_digest(self.plan):matching.append((file,value))
            if matching:
                self.journal_file,self.journal=max(matching,key=lambda pair:pair[1]['created_at'])
                if self.journal['state']=='committed':return self.journal
                transaction=self.journal['transaction_id']
            else:
                transaction=uuid.uuid4().hex;self.journal_file=transactions/(transaction+'.json')
                self.journal={'schema_version':1,'transaction_id':transaction,'created_at':time.time(),'plan_sha256':canonical_digest(self.plan),'manifest_sha256':canonical_digest(self.manifest),'components':{},'state':'approved'}
            stage=self.root/'staging'/transaction;_safe_ancestors(stage);stage.mkdir(parents=True,exist_ok=True)
            cache=self.root/'cache';cache.mkdir(exist_ok=True)
            active_file=run/'active.json'
            _safe_ancestors(active_file)
            previous=json.loads(active_file.read_text()) if active_file.exists() else None
            previous_file=transactions/(transaction+'.previous.json')
            if previous is not None and previous.get('transaction_id')==transaction:
                for item in previous.get('components',{}).values():
                    if item.get('mode')=='managed':self._verify_component(item)
                self._save('committed',active=previous,recovered_after_activation=True)
                return copy.deepcopy(self.journal)
            _safe_ancestors(previous_file)
            if previous is not None:
                if previous_file.exists() and canonical_digest(json.loads(previous_file.read_text()))!=canonical_digest(previous):
                    os.replace(previous_file,previous_file.with_name(transaction+'.previous-attempt-'+uuid.uuid4().hex+'.json'))
                if not previous_file.exists():atomic_json(previous_file,previous)
                self.journal['previous_active_sha256']=canonical_digest(previous)
            try:
                self._save('downloading')
                self._files={key:self._artifact(artifact,cache) for key,artifact in self.artifacts.items()}
                self._preflight_space(self._files)
                self._save('preparing')
                components=copy.deepcopy(previous.get('components',{})) if previous else {}
                for name in self.plan['components']:
                    descriptor=self.journal['components'].get(name)
                    if descriptor is None:
                        descriptor=self._component(name,self._files,transaction)
                        self.journal['components'][name]=descriptor;self._save('preparing')
                    self._verify_component(descriptor)
                    components[name]=descriptor
                if self.plan['mode']=='managed' and 'comfy' in self.plan['components']:
                    if 'study' not in components:raise ValueError('Install Study before managed Comfy smoke verification')
                    self._verify_component(components['study'])
                    self._save('smoke_testing');self._proof(components['comfy'],components['study'],stage)
                elif self.plan['mode']=='external':
                    if previous and previous.get('components',{}).get('comfy',{}).get('mode')=='managed':
                        assert_components_offline(self.config,['comfy'])
                    external=self.config['comfy'];checkpoint=external.get('checkpoint','')
                    components['comfy']={'owner':'external','mode':'external','url':'http://127.0.0.1:8188','checkpoint_name':checkpoint,'enabled':False,'requires_external_acceptance':True,'health':external_health()}
                    if self.plan.get('external_smoke_approved') is True:
                        if not checkpoint or 'study' not in components:raise ValueError('External smoke needs a reviewed checkpoint and installed Study runtime')
                        proof=self.smoke(checkpoint,stage/'external-smoke',components['study'],self.runner)
                        self._attestation_study=components['study']
                        self._validate_proof(proof,checkpoint,stage/'external-smoke')
                        components['comfy'].update(enabled=True,requires_external_acceptance=False,smoke=proof)
                elif self.plan['mode']=='disabled':
                    if 'comfy' in components:
                        components['comfy']['enabled']=False
                        components['comfy']['disabled_by_plan']=True
                    else:components['comfy']={'owner':'external','mode':'disabled','enabled':False}
                effective_mode=self.plan['mode']
                if effective_mode=='managed' and 'comfy' not in self.plan['components']:
                    effective_mode=previous.get('comfy_mode','disabled') if previous else 'disabled'
                    if 'comfy' not in components:components['comfy']={'owner':'external','mode':'disabled','enabled':False,'pending_requested_mode':'managed'}
                self._save('backing_up')
                assert_components_offline(self.config,self.plan['components'])
                assert_data_writers_offline(self.config,previous)
                backup=None
                if self.data.exists():
                    backups=self.root/'backups';backups.mkdir(exist_ok=True);destination=backups/(transaction+'-'+uuid.uuid4().hex)
                    ops.backup_data(self.data,destination)
                    backup=str(destination)
                self.data.mkdir(parents=True,exist_ok=True)
                active={'schema_version':1,'target_host':'LS5','transaction_id':transaction,'activated_at':time.time(),'manifest_sha256':canonical_digest(self.manifest),'plan_sha256':canonical_digest(self.plan),'components':components,'comfy_mode':effective_mode,'requested_comfy_mode':self.plan['mode'],'previous_active':str(previous_file) if previous is not None else None,'backup':backup,'data_dir':str(self.data)}
                self._save('activating',active=active)
                assert_data_writers_offline(self.config,previous)
                atomic_json(active_file,active)
                self._save('committed',active=active)
                return copy.deepcopy(self.journal)
            except BaseException as exc:
                # If activation already happened, the atomic pointer is authoritative.
                current=json.loads(active_file.read_text()) if active_file.exists() else None
                state='committed' if current and current.get('transaction_id')==transaction else 'failed'
                self._save(state,error=type(exc).__name__+': '+str(exc)[:500])
                raise

    def recover(self):
        """Read-only recovery inspection; never activate incomplete components."""
        config=self.plan.get('config',{});root=Path(config['app_root'])
        active=root/'run/active.json';directory=root/'run/transactions'
        return {'active':json.loads(active.read_text()) if active.exists() else None,'transactions':[json.loads(p.read_text()) for p in directory.glob('*.json') if '.previous' not in p.stem] if directory.exists() else []}

    def rollback(self):
        self._authorize('rollback')
        transaction=self.plan.get('rollback_transaction_id','')
        if not re.fullmatch('[a-f0-9]{32}',transaction):raise ValueError('Select an installed transaction to roll back')
        # Authoritative reads, ownership checks and merge occur under the same lock
        # as update/activation, preserving unrelated concurrent component updates.
        with transaction_lock(self.config):
            journal_path=self.root/'run/transactions'/(transaction+'.json')
            previous_file=self.root/'run/transactions'/(transaction+'.previous.json')
            active_file=self.root/'run/active.json'
            for path in (journal_path,previous_file,active_file):_safe_ancestors(path)
            journal=json.loads(journal_path.read_text())
            if journal.get('state')!='committed' or not previous_file.is_file():raise ValueError('No verified previous active release exists')
            previous=json.loads(previous_file.read_text())
            if canonical_digest(previous)!=journal.get('previous_active_sha256'):raise ValueError('Rollback pointer history changed')
            current=json.loads(active_file.read_text())
            assert_components_offline(self.config,self.plan['components'])
            assert_data_writers_offline(self.config,current)
            merged=copy.deepcopy(current)
            for name in self.plan['components']:
                item=previous.get('components',{}).get(name)
                if item is None:raise ValueError('No previous release exists for selected component')
                if item.get('mode')=='managed':self._verify_component(item)
                merged['components'][name]=item
            if 'comfy' in self.plan['components']:merged['comfy_mode']=previous['comfy_mode']
            merged.update(rollback_of=transaction,rollback_plan_sha256=canonical_digest(self.plan),rolled_back_at=time.time())
            backup=self.root/'backups'/('rollback-'+uuid.uuid4().hex)
            if self.data.exists():backup.parent.mkdir(exist_ok=True);ops.backup_data(self.data,backup)
            assert_data_writers_offline(self.config,current)
            atomic_json(active_file,merged)
        return {'state':'rolled_back','active':merged,'data_preserved':True,'backup':str(backup) if backup.exists() else None}

    def restore_backup(self,source,destination):
        self._authorize('restore')
        # Never overwrite live data; verified restore always goes to a new directory.
        if self.plan.get('restore_source')!=str(source) or self.plan.get('restore_destination')!=str(destination):raise ValueError('Restore paths differ from the approved plan')
        target=_local(destination)
        if target==self.data or ops.inside(target,self.root/'releases'):raise ValueError('Restore requires a separate new destination')
        return ops.restore_data(source,target)

def relative_member(value):
    path=PurePosixPath(value)
    if not value or path.is_absolute() or '..' in path.parts or ':' in value or '\\' in value:raise ValueError('Unsafe component member')
    return Path(*path.parts)

def urllib_name(artifact):
    import urllib.parse
    value=artifact.get('filename') or urllib.parse.unquote(urllib.parse.urlsplit(artifact.get('url',artifact.get('local_path',''))).path).split('/')[-1]
    if not value or Path(value).name!=value or value in ('.','..') or any(c in value for c in (':','\\','/')):raise ValueError('Unsafe artifact filename')
    return value
