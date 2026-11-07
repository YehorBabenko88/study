"""LS5 launcher validation only; never start services on the development PC."""
import importlib.util,json,os,socket,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('study_ls5_launcher',Path(__file__).resolve().parents[1]/'deploy'/'ls5'/'study_service.py')
launcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(launcher)

class LS5LauncherTests(unittest.TestCase):
    def fixture(self,root):
        release=root/'releases'/'v1';(release/'prototype').mkdir(parents=True)
        (release/'prototype'/'web_app.py').write_text('# fixture only')
        other=root/'venvs'/'comfy'/'python.exe';other.parent.mkdir(parents=True);other.write_bytes(b'fixture')
        return {'version':1,'target_host':'LS5','app_root':str(root),'study':{'host':'127.0.0.1','port':8766,'python':sys.executable,'release_dir':str(release),'data_dir':str(root/'data')},'comfy':{'enabled':False,'host':'127.0.0.1','port':8188,'python':str(other),'directory':str(root/'ComfyUI'),'checkpoint':''}}
    def load(self,root,config):
        file=root/'config.json';file.write_text(json.dumps(config),encoding='utf-8');return launcher.load_config(file)
    def test_pc1_guard_rejects_without_creating_data_or_environment(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);config=self.load(root,self.fixture(root));before=dict(os.environ)
            with patch.object(launcher.socket,'gethostname',return_value='PC1'):
                with self.assertRaisesRegex(RuntimeError,'outside target LS5'):launcher.prepare_environment(config)
            self.assertFalse((root/'data').exists());self.assertEqual(dict(os.environ),before)
    def test_explicit_ls5_bootstrap_sets_durable_paths_without_starting_server(self):
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{},clear=False):
            root=Path(folder);config=self.load(root,self.fixture(root))
            with patch.object(launcher.socket,'gethostname',return_value='LS5'):
                prototype=launcher.prepare_environment(config)
            self.assertTrue((root/'data').is_dir())
            self.assertEqual(prototype,root/'releases'/'v1'/'prototype')
            self.assertEqual(os.environ['STUDY_DATA_DIR'],str(root/'data'))
            self.assertEqual(os.environ['STUDY_COMFYUI_DB'],str(root/'data'/'comfy_jobs.sqlite'))
            self.assertEqual(os.environ['STUDY_COMPOSITIONS_DB'],str(root/'data'/'compositions.sqlite'))
            self.assertEqual(os.environ['STUDY_COMFYUI_ENABLED'],'0')
    def test_unsafe_configurations_rejected_without_writes(self):
        changes=[('target_host','PC1'),('study.host','0.0.0.0'),('study.port',8000),('comfy.port',8189),('comfy.enabled','false'),('study.data_dir','inside'),('study.release_dir','outside'),('comfy.python','same')]
        for key,value in changes:
            with self.subTest(key=key),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);config=self.fixture(root)
                if key=='study.data_dir':value=str(root/'releases'/'v1'/'data')
                if key=='study.release_dir':value=str(root/'outside')
                if key=='comfy.python':value=config['study']['python']
                if '.' in key:section,name=key.split('.');config[section][name]=value
                else:config[key]=value
                with self.assertRaises(ValueError):self.load(root,config)
                self.assertFalse((root/'data').exists())
    def test_example_has_distinct_venvs_and_loopback_ports(self):
        config=json.loads((Path(launcher.__file__).with_name('config.example.json')).read_text())
        self.assertEqual(config['study']['port'],8766);self.assertEqual(config['comfy']['port'],8188)
        self.assertNotEqual(config['study']['python'],config['comfy']['python'])
        self.assertFalse(config['comfy']['enabled'])

    def test_ls_dash_5_is_not_the_ls5_target_host(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);config=self.load(root,self.fixture(root))
            with patch.object(launcher.socket,'gethostname',return_value='LS-5'):
                with self.assertRaises(RuntimeError):launcher.prepare_environment(config)
            self.assertFalse((root/'data').exists())
            original=json.loads((root/'config.json').read_text())
            original['target_host']='LS-5'
            with self.assertRaises(ValueError):self.load(root,original)

    def test_study_bootstrap_does_not_require_comfy_installation(self):
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{},clear=False):
            root=Path(folder);original=self.fixture(root)
            Path(original['comfy']['python']).unlink()
            original['comfy']['enabled']=True;original['comfy']['checkpoint']='reviewed.safetensors'
            config=self.load(root,original)
            self.assertFalse((config['comfy']['directory']/'main.py').exists())
            with patch.object(launcher.socket,'gethostname',return_value='ls5'):
                launcher.prepare_environment(config)
            self.assertTrue((root/'data').is_dir())
            self.assertEqual(os.environ['STUDY_COMFYUI_ENABLED'],'1')
