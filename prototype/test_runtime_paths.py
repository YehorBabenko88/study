"""Portable data-root regressions without touching existing learner data."""
import json,os,subprocess,sys,tempfile,unittest
from pathlib import Path

class RuntimePathsTests(unittest.TestCase):
    def test_external_data_survives_release_path_change_and_import_is_read_only(self):
        source=Path(__file__).parent
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);data=root/'durable'
            scripts=[]
            for name in ('release-a','release-b'):
                release=root/name;release.mkdir()
                for filename in ('runtime_paths.py','visual_memory.py'):
                    candidate=source/filename
                    if candidate.exists():(release/filename).write_bytes(candidate.read_bytes())
                scripts.append(release)
            env=dict(os.environ,STUDY_DATA_DIR=str(data))
            imported=subprocess.run([sys.executable,'-c','import visual_memory; print(visual_memory.DB)'],cwd=scripts[0],env=env,capture_output=True,text=True,check=True)
            self.assertFalse(data.exists(),'Import must not create directories')
            self.assertEqual(Path(imported.stdout.strip()),data/'study_local.sqlite3')
            data.mkdir()
            subprocess.run([sys.executable,'-c',"import visual_memory as v; c=v.connection(); d=c.__enter__(); d.execute('CREATE TABLE portable_probe(value TEXT)'); d.execute(\"INSERT INTO portable_probe VALUES ('preserved')\"); d.commit(); c.__exit__(None,None,None)"],cwd=scripts[0],env=env,check=True)
            recovered=subprocess.check_output([sys.executable,'-c',"import visual_memory as v; c=v.connection(); d=c.__enter__(); print(d.execute('SELECT value FROM portable_probe').fetchone()[0]); c.__exit__(None,None,None)"],cwd=scripts[1],env=env,text=True)
            self.assertEqual(recovered.strip(),'preserved')
            self.assertFalse((scripts[0]/'study_local.sqlite3').exists())
            self.assertFalse((scripts[1]/'study_local.sqlite3').exists())

    def test_defaults_and_configured_paths(self):
        import runtime_paths as paths
        source=Path(__file__).parent
        from unittest.mock import patch
        with patch.dict(os.environ,{},clear=True):
            self.assertEqual(paths.data_path(source/'visual_memory.py','study_local.sqlite3'),source/'study_local.sqlite3')
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'STUDY_DATA_DIR':folder}):
            for name in ('study_local.sqlite3','study_lexicon.sqlite3','generated_media','speech_audio','document_uploads','board_assets','comfy_jobs.sqlite','compositions.sqlite'):
                self.assertEqual(paths.data_path(source/'module.py',name),Path(folder)/name)
            for name in ('../escape','/absolute','x/y','x\\y','..','x:y'):
                with self.assertRaises(ValueError):paths.data_path(source/'module.py',name)

    def test_relative_and_traversal_roots_are_rejected(self):
        import runtime_paths as paths
        from unittest.mock import patch
        for value in ('relative-data','../data',str(Path.cwd()/'..'/'escape'),'\\\\server\\share','\\\\.\\PhysicalDrive0'):
            with self.subTest(value=value),patch.dict(os.environ,{'STUDY_DATA_DIR':value}),self.assertRaises(ValueError):paths.data_root()

    def test_all_storage_modules_share_root_and_main_database_without_import_writes(self):
        source=Path(__file__).parent.resolve()
        script="""
import json,visual_memory as v,lexicon_store as l,board_assets as b,ai_images as a,speech_projects as s,document_import as d,comfy_adapter as c,composition_service as p
print(json.dumps([str(v.DB),str(l.DB),str(b.ROOT),str(a.MEDIA),str(s.AUDIO_DIR),str(d.ROOT),str(s.DB),str(d.DB)]))
"""
        with tempfile.TemporaryDirectory() as folder:
            data=Path(folder)/'not-created'
            env=dict(os.environ,STUDY_DATA_DIR=str(data),PYTHONPATH=str(source))
            values=json.loads(subprocess.check_output([sys.executable,'-c',script],env=env,text=True))
            self.assertEqual(values,[str(data/name) for name in ('study_local.sqlite3','study_lexicon.sqlite3','board_assets','generated_media','speech_audio','document_uploads','study_local.sqlite3','study_local.sqlite3')])
            self.assertFalse(data.exists())
            data.mkdir()
            initialize="import comfy_adapter as c,composition_service as p; r=c.registry(); print(r.db.execute('PRAGMA database_list').fetchone()[2]); r.close(); p.service()"
            # These are explicit service initializers; no worker can contact Comfy.
            env['STUDY_COMFYUI_ENABLED']='0'
            env.pop('STUDY_COMFYUI_DB',None);env.pop('STUDY_COMPOSITIONS_DB',None)
            subprocess.check_call([sys.executable,'-c',initialize],env=env)
            self.assertTrue((data/'comfy_jobs.sqlite').is_file())
            self.assertTrue((data/'compositions.sqlite').is_file())

    def test_resolved_alias_to_drive_root_is_rejected(self):
        import runtime_paths as paths
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'STUDY_DATA_DIR':folder}),patch.object(Path,'resolve',return_value=Path(Path(folder).anchor)):
            with self.assertRaises(ValueError):paths.data_root()
