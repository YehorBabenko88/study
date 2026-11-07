"""Foreground Study launcher for LS5; no installation, migration or Comfy launch."""
import argparse
import json
import os
from pathlib import Path
import socket
import sys


def _canonical_host(value):
    return value.upper() if isinstance(value,str) else ''


def _inside(path,parent):
    return path==parent or parent in path.parents


def load_config(filename):
    filename=Path(filename).resolve()
    config=json.loads(filename.read_text(encoding='utf-8-sig'))
    if not isinstance(config,dict) or type(config.get('version')) is not int or config['version']!=1:
        raise ValueError('Configuration version 1 required')
    if _canonical_host(config.get('target_host'))!='LS5':raise ValueError('Target host must be LS5')
    study=config.get('study');comfy=config.get('comfy')
    if not isinstance(study,dict) or not isinstance(comfy,dict):raise ValueError('Study and Comfy configuration required')
    if study.get('host')!='127.0.0.1' or type(study.get('port')) is not int or study['port']!=8766:
        raise ValueError('Study must bind 127.0.0.1:8766')
    if comfy.get('host')!='127.0.0.1' or type(comfy.get('port')) is not int or comfy['port']!=8188:
        raise ValueError('Comfy must bind 127.0.0.1:8188')
    if type(comfy.get('enabled')) is not bool:raise ValueError('Comfy enabled must be boolean')
    checkpoint=comfy.get('checkpoint','')
    if not isinstance(checkpoint,str) or len(checkpoint)>180:raise ValueError('Invalid reviewed checkpoint name')
    def local_path(value):
        if not isinstance(value,str) or not value or '\x00' in value or value.startswith(('\\\\','//')):
            raise ValueError('A local filesystem path is required')
        path=Path(value)
        if '..' in path.parts:raise ValueError('Parent traversal in configuration paths is forbidden')
        if path.drive and not path.is_absolute():raise ValueError('Drive-relative paths are forbidden')
        return (path if path.is_absolute() else filename.parent/path).resolve()
    config['app_root']=local_path(config.get('app_root'))
    for section,keys in ((study,('python','release_dir','data_dir')),(comfy,('python','directory'))):
        for key in keys:section[key]=local_path(section.get(key))
    releases=config['app_root']/'releases'
    if study['release_dir']==releases or not _inside(study['release_dir'],releases):
        raise ValueError('Release must be a dedicated directory beneath app_root/releases')
    if _inside(study['data_dir'],releases) or _inside(study['release_dir'],study['data_dir']):
        raise ValueError('Durable data must be separate from every release directory')
    if study['data_dir']==Path(study['data_dir'].anchor):raise ValueError('Use a dedicated data directory')
    if study['python']==comfy['python']:raise ValueError('Study and Comfy require separate configured Python environments')
    return config


def assert_target(config):
    actual=_canonical_host(socket.gethostname())
    if actual!='LS5' or actual!=_canonical_host(config['target_host']):
        raise RuntimeError('Refusing to run Study services outside target LS5 (this host: '+socket.gethostname()+')')


def prepare_environment(config):
    """Explicit bootstrap; only this function creates the durable root."""
    assert_target(config)
    study=config['study'];comfy=config['comfy']
    if not study['python'].is_file():
        raise ValueError('Configure an existing Study Python executable; this launcher installs nothing')
    if Path(sys.executable).resolve()!=study['python']:
        raise ValueError('Run this launcher with the configured Study Python executable')
    prototype=study['release_dir']/'prototype'
    if not (prototype/'web_app.py').is_file():raise ValueError('Selected Study release is incomplete')
    if comfy['enabled'] and not comfy['checkpoint']:
        raise ValueError('Enabled Comfy requires a reviewed checkpoint name; installation is independent')
    study['data_dir'].mkdir(parents=True,exist_ok=True)
    os.environ.update({
        'STUDY_DATA_DIR':str(study['data_dir']),
        'STUDY_COMPOSITIONS_DB':str(study['data_dir']/'compositions.sqlite'),
        'STUDY_COMFYUI_DB':str(study['data_dir']/'comfy_jobs.sqlite'),
        'STUDY_COMFYUI_ENABLED':'1' if comfy['enabled'] else '0',
        'STUDY_COMFYUI_CHECKPOINT':comfy['checkpoint']})
    return prototype


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True,type=Path)
    args=parser.parse_args(argv)
    config=load_config(args.config)
    prototype=prepare_environment(config)
    sys.path.insert(0,str(prototype))
    from http.server import ThreadingHTTPServer
    from web_app import Handler
    with ThreadingHTTPServer(('127.0.0.1',8766),Handler) as server:
        print('Study LS5: http://127.0.0.1:8766',flush=True)
        try:server.serve_forever()
        except KeyboardInterrupt:pass


if __name__=='__main__':main()
