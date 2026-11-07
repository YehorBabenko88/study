"""Offline lifecycle primitives. No installer, dependency or model downloads."""
from pathlib import Path, PurePosixPath
from contextlib import closing, contextmanager
import argparse
import hashlib
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys

FORMAT='study-offline-backup-v1'

def canonical(host): return str(host).upper()
def target_guard(config):
    if canonical(config.get('target_host'))!='LS5' or canonical(socket.gethostname())!='LS5':
        raise ValueError('Operation is restricted to configured LS5; PC1 is development only')
def inside(path, parent):
    try: path.resolve().relative_to(parent.resolve()); return True
    except ValueError: return False

def load_config(path):
    # Embedded Python isolates its search path; use only this reviewed sibling.
    sys.dont_write_bytecode=True
    if str(Path(__file__).resolve().parent) not in sys.path:sys.path.insert(0,str(Path(__file__).resolve().parent))
    from study_service import load_config as validated_config
    result=validated_config(path);result['_config_file']=str(Path(path).resolve());return result

def launch_plan(config,service):
    if service not in ('study','comfy'): raise ValueError('Select exactly one service')
    item=config[service];exe=Path(item['python'])
    entry=Path(item['release_dir'])/'deploy/ls5/study_service.py' if service=='study' else Path(item['directory'])/'main.py'
    if not exe.is_file() or not entry.is_file(): raise ValueError('Configured existing environment or service entry point is missing')
    args=['-B',str(entry),'--config',config['_config_file']] if service=='study' else ['-B',str(entry),'--listen','127.0.0.1','--port','8188']
    create_dirs=[]
    if service=='comfy':
        if not item.get('enabled',False):raise ValueError('Comfy is disabled in configuration')
        checkpoint=item.get('checkpoint','')
        checkpoint_file=Path(item.get('checkpoint_path') or Path(item['directory'])/'models/checkpoints'/checkpoint)
        if not checkpoint or Path(checkpoint).name!=checkpoint or not checkpoint_file.is_file():raise ValueError('A reviewed existing checkpoint is required; no model will be downloaded')
        if item.get('checkpoint_path') and not inside(checkpoint_file,Path(config['app_root'])/'models'):raise ValueError('Managed shared checkpoint escapes the owned model library')
        flags=['--disable-auto-launch','--disable-api-nodes','--disable-all-custom-nodes','--output-directory','--user-directory']
        cli=Path(item['directory'])/'comfy/cli_args.py'
        if not cli.is_file() or any(flag not in cli.read_text(encoding='utf-8') for flag in flags):raise ValueError('Installed Comfy flags require audit; unsupported releases are not launched')
        output=Path(config['study']['data_dir'])/'comfy/output';user=Path(config['study']['data_dir'])/'comfy/user'
        args+=flags[:3]+['--output-directory',str(output),'--user-directory',str(user)]
        if item.get('extra_model_paths'):
            mapping=Path(item['extra_model_paths'])
            if not mapping.is_file() or not inside(mapping,Path(item['directory']).parent) or '--extra-model-paths-config' not in cli.read_text(encoding='utf-8'):raise ValueError('Managed model-path mapping is missing or unsupported')
            args+=['--extra-model-paths-config',str(mapping)]
        create_dirs=[str(output),str(user)]
    return {'create_dirs':create_dirs,'service':service,'executable':str(exe),'args':args,'argument_line':subprocess.list2cmdline(args),'working_directory':str(entry.parent if service=='comfy' else Path(item['release_dir'])),'pid_file':str(Path(config['app_root'])/'run'/(service+'.json')),'health_url':'http://127.0.0.1:'+str(item['port'])+('/' if service=='study' else '/system_stats')}

def assert_offline(config):
    run=Path(config['app_root'])/'run';active_file=run/'active.json'
    owned_comfy=(run/'comfy.json').exists()
    if active_file.exists():
        if linked(active_file) or linked(run):raise ValueError('Linked active ownership metadata refused')
        active=json.loads(active_file.read_text(encoding='utf-8'))
        if active.get('schema_version')!=1 or active.get('target_host')!='LS5' or not isinstance(active.get('components'),dict):raise ValueError('Invalid active ownership metadata')
        descriptor=active['components'].get('comfy')
        if descriptor is not None:
            if not isinstance(descriptor,dict):raise ValueError('Invalid Comfy ownership descriptor')
            if descriptor.get('owner')=='study-installer' and descriptor.get('mode')=='managed':owned_comfy=True
            elif descriptor.get('owner')=='external' and descriptor.get('mode')=='external':pass
            elif descriptor.get('mode')=='disabled':pass
            else:raise ValueError('Unrecognized Comfy ownership metadata')
    elif config.get('comfy_mode')!='external' and config.get('comfy',{}).get('enabled') is True:
        owned_comfy=True  # Explicit legacy standalone management configuration.
    services=[('study',8766)]+([('comfy',8188)] if owned_comfy else [])
    for service,port in services:
        if (Path(config['app_root'])/'run'/(service+'.json')).exists():raise ValueError('Stop the managed '+service+' process before offline data/code operations')
        with socket.socket() as connection:
            connection.settimeout(.5)
            if connection.connect_ex(('127.0.0.1',port))==0:raise ValueError(service+' port is in use; consistent offline operation refused')

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def linked(path):
    return path.is_symlink() or bool(getattr(path.lstat(),'st_file_attributes',0)&0x400)

def safe_files(root):
    if linked(root): raise ValueError('Linked data roots are refused')
    result=[]
    for path in root.rglob('*'):
        if linked(path) or not inside(path,root): raise ValueError('Linked or escaping data path refused')
        if path.is_file():result.append(path)
    return sorted(result)

def backup_data(source,destination):
    if linked(Path(source)) or (os.path.lexists(destination) and linked(Path(destination))):raise ValueError('Linked root refused')
    source=Path(source).resolve();destination=Path(destination).resolve()
    if not source.is_dir() or inside(destination,source) or inside(source,destination):raise ValueError('Backup must be separate from existing data')
    files=safe_files(source)
    if any(p.relative_to(source).as_posix()=='backup-manifest.json' for p in files):raise ValueError('Reserved manifest filename in source')
    databases=set()
    for path in files:
        with path.open('rb') as stream:
            if stream.read(16)==b'SQLite format 3\x00':databases.add(path)
    before={str(p): (p.stat().st_size,p.stat().st_mtime_ns) for p in files}
    destination.mkdir(parents=True,exist_ok=False)
    entries=[]
    for path in files:
        if any(str(path)==str(db)+suffix for db in databases for suffix in ('-wal','-shm','-journal')):continue
        target=destination/path.relative_to(source);target.parent.mkdir(parents=True,exist_ok=True)
        if path in databases:
            with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as original,closing(sqlite3.connect(target)) as copied:
                original.backup(copied)
                if copied.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('SQLite backup integrity failure')
        else:shutil.copy2(path,target)
        entries.append({'path':path.relative_to(source).as_posix(),'sha256':digest(target),'size':target.stat().st_size,'kind':'sqlite' if path in databases else 'file'})
    after_files=safe_files(source)
    if set(map(str,after_files))!=set(before) or any((p.stat().st_size,p.stat().st_mtime_ns)!=before[str(p)] for p in after_files):raise ValueError('Source changed during backup; partial destination must not be restored')
    manifest={'format':FORMAT,'files':entries}
    (destination/'backup-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    return manifest

def verify_backup(source):
    if linked(Path(source)):raise ValueError('Linked backup root refused')
    source=Path(source).resolve();safe_files(source)
    manifest=json.loads((source/'backup-manifest.json').read_text(encoding='utf-8'))
    if manifest.get('format')!=FORMAT or not isinstance(manifest.get('files'),list):raise ValueError('Unsupported backup manifest')
    seen=set()
    for entry in manifest['files']:
        name=entry['path'];parts=PurePosixPath(name)
        if parts.is_absolute() or '..' in parts.parts or ':' in name or '\\' in name or name in seen or not name or name=='backup-manifest.json':raise ValueError('Unsafe manifest path')
        seen.add(name);path=source/name
        if not path.is_file() or digest(path)!=entry['sha256'] or path.stat().st_size!=entry['size']:raise ValueError('Backup hash verification failed: '+name)
        if entry['kind']=='sqlite':
            with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as db:
                if db.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('Database integrity failure')
    if {p.relative_to(source).as_posix() for p in safe_files(source)}!=seen|{'backup-manifest.json'}:raise ValueError('Unlisted files in backup')
    return manifest

def restore_data(source,destination):
    if (os.path.lexists(source) and linked(Path(source))) or (os.path.lexists(destination) and linked(Path(destination))):raise ValueError('Linked root refused')
    source=Path(source).resolve();destination=Path(destination).resolve();manifest=verify_backup(source)
    if inside(destination,source) or inside(source,destination):raise ValueError('Restore destination must be separate')
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):raise ValueError('Restore requires a new empty destination')
    if linked(destination) if destination.exists() else False:raise ValueError('Linked destination refused')
    destination.mkdir(parents=True,exist_ok=True)
    for entry in manifest['files']:
        target=destination/entry['path'];target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source/entry['path'],target)
        if digest(target)!=entry['sha256']:raise ValueError('Restored file hash mismatch')
    return {'destination':str(destination),'files':len(manifest['files'])}

def uninstall_candidate(config,path):
    if Path(path).exists() and linked(Path(path)):raise ValueError('Linked code release root refused')
    candidate=Path(path).resolve();root=Path(config['app_root']).resolve();release=Path(config['study']['release_dir']).resolve()
    if candidate!=release or candidate==root/'releases' or not inside(candidate,root/'releases'):raise ValueError('Only the exact configured code release may be removed')
    protected=[Path(config['study']['data_dir']),Path(config['study']['python']).parent.parent,Path(config['comfy']['python']).parent.parent,Path(config['comfy']['directory'])]
    if any(inside(p,candidate) or inside(candidate,p) for p in protected):raise ValueError('Candidate overlaps persistent data, environments or Comfy')
    if not (candidate/'prototype/web_app.py').is_file() or not (candidate/'deploy/ls5/study_service.py').is_file():raise ValueError('Code release markers are missing')
    legacy_names=('study_local.sqlite3','study_lexicon.sqlite3','comfy_jobs.sqlite','compositions.sqlite','board_assets','generated_media','speech_audio','document_uploads')
    for name in legacy_names:
        for suffix in ('','-wal','-shm','-journal'):
            if (candidate/'prototype'/(name+suffix)).exists():raise ValueError('Legacy learner storage found in release; preserve/migrate it separately before code removal')
    safe_files(candidate)
    return str(candidate)

@contextmanager
def lifecycle_lock(config):
    directory=Path(config['app_root'])/'run';directory.mkdir(parents=True,exist_ok=True)
    lock=directory/'lifecycle.lock'
    stream=lock.open('x',encoding='utf-8')
    try:
        stream.write(str(os.getpid()));stream.flush();yield
    finally:
        stream.close();lock.unlink()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('operation',choices=['launch-plan','backup','restore','uninstall-check']);parser.add_argument('--config',required=True);parser.add_argument('--service',choices=['study','comfy']);parser.add_argument('--source');parser.add_argument('--destination');parser.add_argument('--release');args=parser.parse_args()
    config=load_config(args.config);target_guard(config)
    if args.operation=='launch-plan':result=launch_plan(config,args.service)
    elif args.operation=='uninstall-check':
        assert_offline(config);result={'release':uninstall_candidate(config,args.release)}
    else:
        with lifecycle_lock(config):
            assert_offline(config)
            if args.operation=='backup':result=backup_data(config['study']['data_dir'],args.destination)
            elif args.operation=='restore':result=restore_data(args.source,args.destination)
            else:result={'release':uninstall_candidate(config,args.release)}
    print(json.dumps(result))
if __name__=='__main__':main()
