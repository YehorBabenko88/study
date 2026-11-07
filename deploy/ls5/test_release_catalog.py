import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import unittest

from manifest_validation import ManifestError, audit_sha256, validate_manifest, materialize_manifest


class ManifestTests(unittest.TestCase):
    def fixture(self):
        def artifact(identifier, kind, **extra):
            return dict(id=identifier,kind=kind,component='fixture',url='https://example.org/'+identifier,
                        sha256=hashlib.sha256(identifier.encode()).hexdigest(),size=100,**extra)
        artifacts=[artifact('python.zip','python',runtime_kind='embedded',python_executable='python.exe',python_tag='cp313',platform='win_amd64'),
                   artifact('pip.whl','wheel',distribution='pip',version='25.3',python_tag='py3',platform='any'),
                   artifact('study.zip','zip'),artifact('comfy.zip','zip'),
                   artifact('pillow.whl','wheel',distribution='pillow',version='12.1.0',python_tag='cp313',platform='win_amd64'),
                   artifact('model.safetensors','model',license_id='fixture-license',hardware_requirements_reviewed=True,min_vram_bytes=1024,min_ram_bytes=1024,workflow_family='sd1')]
        component=dict(runtime_kind='embedded',entrypoint='main.py',python_artifact_id='python.zip',pip_artifact_id='pip.whl',wheel_ids=['pillow.whl'],requirements_lock=[dict(distribution='pillow',version='12.1.0',artifact_id='pillow.whl',requires=[])],dependency_lock_complete=True,dependency_lock_audited=True)
        manifest=dict(schema_version=1,release_ready=True,allowed_hosts=['example.org'],artifacts=artifacts,
                      components={'study':dict(component,artifact_ids=['study.zip']), 'comfy':dict(component,artifact_ids=['comfy.zip','model.safetensors'])},
                      licenses=[dict(id='fixture-license',url='https://example.org/license',sha256='a'*64,size=12,acceptance_required=True)])
        audit=dict(schema_version=1,status='COLLECTED_READ_ONLY',hostname='LS5',collected_at_utc=datetime.now(timezone.utc).isoformat(),os=[{'OSArchitecture':'64-bit'}],ram=[{'TotalPhysicalMemory':32768}],disks=[{'FreeSpace':100000}],gpu={'nvidia_smi':[{'dedicated_vram_total_mib':'8192','driver_version':'999.1','source':'nvidia-smi'}]})
        plan=dict(mode='managed',components=['study','comfy'],device='cuda',accepted_licenses=['fixture-license'],approved_download_bytes=100000,hardware_review={'audit_sha256':audit_sha256(audit),'component_compatibility':'approved','gpu_verified':True,'vram_bytes':8192*1024**2})
        return manifest,plan,audit

    def test_complete_fixture_passes_detached(self):
        manifest,plan,audit=self.fixture(); result=validate_manifest(manifest,plan,audit)
        self.assertEqual(result,manifest); self.assertIsNot(result,manifest)

    def test_missing_and_placeholder_pins_refused(self):
        for value in (None,'','TODO','0'*64):
            manifest,plan,audit=self.fixture();manifest['artifacts'][0]['sha256']=value
            with self.assertRaises(ManifestError):validate_manifest(manifest,plan,audit)

    def test_mutable_or_unapproved_url_refused(self):
        for url in ('http://example.org/a','https://evil.org/a','https://example.org/latest/a','https://example.org/resolve/main/a'):
            manifest,plan,audit=self.fixture();manifest['artifacts'][0]['url']=url
            with self.assertRaises(ManifestError):validate_manifest(manifest,plan,audit)

    def test_dependency_closure_and_platform_refused(self):
        for case in ('missing','open','wrong_version','incompatible'):
            manifest,plan,audit=self.fixture()
            if case=='missing':manifest['components']['study']['dependency_lock_audited']=False
            if case=='open':manifest['components']['study']['requirements_lock'][0]['requires']=['missing-dependency']
            if case=='wrong_version':manifest['components']['study']['requirements_lock'][0]['version']='0.0'
            if case=='incompatible':manifest['artifacts'][4]['python_tag']='cp312'
            with self.assertRaises(ManifestError):validate_manifest(manifest,plan,audit)

    def test_unknown_or_no_gpu_never_auto_selects_cuda(self):
        manifest,plan,audit=self.fixture()
        for hardware in (None,{'status':'BLOCKED'},dict(audit,gpu={'wmi':[{'AdapterRAM':4294967295}]})):
            with self.assertRaises(ManifestError):validate_manifest(manifest,plan,hardware)

    def test_cpu_requires_explicit_opt_in_and_audit_review(self):
        manifest,plan,audit=self.fixture();plan['device']='cpu';audit['gpu']={};plan['hardware_review']['audit_sha256']=audit_sha256(audit)
        with self.assertRaises(ManifestError):validate_manifest(manifest,plan,audit)
        plan['cpu_opt_in']=True
        self.assertEqual(validate_manifest(manifest,plan,audit),manifest)

    def test_model_license_and_download_plan_required(self):
        for key,value in (('accepted_licenses',[]),('approved_download_bytes',0)):
            manifest,plan,audit=self.fixture();plan[key]=value
            with self.assertRaises(ManifestError):validate_manifest(manifest,plan,audit)

    def test_external_and_disabled_have_no_implicit_comfy_install(self):
        manifest,plan,audit=self.fixture()
        for mode in ('external','disabled'):
            plan.update(mode=mode,components=['study'])
            self.assertEqual(validate_manifest(manifest,plan,None),manifest)
            with self.assertRaises(ManifestError):validate_manifest(manifest,dict(plan,components=['study','comfy']),None)

    def test_real_catalog_is_metadata_only_and_blocks_managed(self):
        catalog=json.loads(Path(__file__).with_name('release_catalog.json').read_text())
        self.assertFalse(catalog['release_ready'])
        self.assertEqual(catalog['bootstrap_python']['size'],catalog['bootstrap_python']['size_bytes'])
        self.assertEqual(catalog['bootstrap_python']['sha256'],'76f238f606250c87c6beac75dccd35ee99070a13490555936abb6cb64ecce3d0')
        with self.assertRaises(ManifestError):validate_manifest(catalog,{'mode':'managed','components':['study','comfy']},None)

    def test_real_study_lock_materializes_disabled_external_without_comfy(self):
        catalog=json.loads(Path(__file__).with_name('release_catalog.json').read_text())
        source=dict(id='built-study-source',kind='zip',local_path='payload/study.zip',sha256=hashlib.sha256(b'fixture only').hexdigest(),size=12)
        for mode in ('disabled','external'):
            manifest=materialize_manifest(catalog,mode=mode,study_source_artifact=source)
            plan={'mode':mode,'components':['study'],'approved_download_bytes':100000000}
            self.assertEqual(validate_manifest(manifest,plan,None),manifest)
            self.assertFalse(manifest['components']['comfy']['dependency_lock_complete'])
        with self.assertRaises(ManifestError):materialize_manifest(catalog,mode='managed',study_source_artifact=source)

    def test_malformed_nested_inputs_and_unsafe_local_paths_refused(self):
        manifest,plan,audit=self.fixture()
        for bad in (dict(plan,components=[{}]),dict(plan,accepted_licenses=None)):
            with self.assertRaises(ManifestError):validate_manifest(manifest,bad,audit)
        for path in ('../escape.zip','C:/outside.zip','payload/../../escape.zip','payload\\escape.zip'):
            invalid=copy.deepcopy(manifest);invalid['artifacts'][0].pop('url');invalid['artifacts'][0]['local_path']=path
            with self.assertRaises(ManifestError):validate_manifest(invalid,plan,audit)

    def test_arm_stale_audit_and_oversize_model_are_rejected(self):
        manifest,plan,audit=self.fixture()
        for bad in (dict(audit,os=[{'OSArchitecture':'ARM64'}]),dict(audit,collected_at_utc='2000-01-01T00:00:00+00:00')):
            plan['hardware_review']['audit_sha256']=audit_sha256(bad)
            with self.assertRaises(ManifestError):validate_manifest(manifest,plan,bad)
        manifest,plan,audit=self.fixture();manifest['artifacts'][-1]['min_vram_bytes']=100000000000000
        with self.assertRaises(ManifestError):validate_manifest(manifest,plan,audit)

    def test_lock_text_injection_and_unsafe_archive_root_are_rejected(self):
        manifest,plan,audit=self.fixture()
        manifest['artifacts'][4]['version']='12.1.0\n--index-url evil'
        manifest['components']['study']['requirements_lock'][0]['version']=manifest['artifacts'][4]['version']
        with self.assertRaises(ManifestError):validate_manifest(manifest,plan,audit)
        manifest,plan,audit=self.fixture();manifest['artifacts'][2]['archive_root']='../escape'
        with self.assertRaises(ManifestError):validate_manifest(manifest,plan,audit)

    def test_all_real_catalog_artifacts_have_positive_exact_pins(self):
        catalog=json.loads(Path(__file__).with_name('release_catalog.json').read_text())
        for row in catalog['artifacts']:
            with self.subTest(artifact=row['id']):
                self.assertRegex(row['sha256'], r'^[0-9a-f]{64}$')
                self.assertGreater(row['size'],0)
                self.assertTrue(row['url'].startswith('https://'))

    def test_independent_managed_component_updates_keep_selection_boundary(self):
        manifest,plan,audit=self.fixture()
        self.assertEqual(validate_manifest(manifest,dict(plan,components=['comfy']),audit),manifest)
        # Study-only update preserves existing generation policy; it does not
        # download/enable/review a new Comfy runtime or require its missing lock.
        manifest['release_ready']=False
        manifest['components']['comfy']['dependency_lock_complete']=False
        self.assertEqual(validate_manifest(manifest,dict(plan,components=['study']),None),manifest)
        with self.assertRaises(ManifestError):validate_manifest(manifest,dict(plan,components=['comfy']),audit)

    def test_external_selection_cannot_hide_checkpoint_under_study(self):
        manifest,plan,audit=self.fixture()
        manifest['components']['study']['artifact_ids'].append('model.safetensors')
        with self.assertRaises(ManifestError):validate_manifest(manifest,dict(plan,mode='external',components=['study']),None)

    def test_redirect_hosts_must_be_exact_reviewed_subset(self):
        manifest,plan,audit=self.fixture()
        manifest['allowed_hosts'].append('cdn.example.org')
        manifest['artifacts'][-1]['redirect_hosts']=['cdn.example.org']
        self.assertEqual(validate_manifest(manifest,plan,audit),manifest)
        for invalid in (['evil.example.org'],['*.example.org'],['https://cdn.example.org'],['cdn.example.org:443'],['127.0.0.1'],['cdn.example.org','cdn.example.org']):
            manifest['artifacts'][-1]['redirect_hosts']=invalid
            with self.assertRaises(ManifestError):validate_manifest(manifest,plan,audit)

if __name__=='__main__':unittest.main()
