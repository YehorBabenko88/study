"""Offline metadata evidence tests, not an installation/hardware smoke test."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import unittest

from pip._vendor.packaging.requirements import Requirement
from pip._vendor.packaging.tags import cpython_tags, compatible_tags
from pip._vendor.packaging.utils import canonicalize_name, parse_wheel_filename
from pip._vendor.packaging.version import Version
from manifest_validation import (ManifestError, audit_sha256, validate_manifest,
                                 materialize_managed_cpu_candidate)

ROOT=Path(__file__).parent


class CpuMetadataCandidateTests(unittest.TestCase):
    def setUp(self):
        self.candidate=json.loads((ROOT/'comfy_cpu_lock_candidate.json').read_text())
        self.catalog=json.loads((ROOT/'release_catalog.json').read_text())
        self.source={'id':'fixture-built-study','kind':'zip','local_path':'payload/study.zip',
                     'sha256':hashlib.sha256(b'fixture-source-only').hexdigest(),'size':20}

    def materialize(self, model_id='sdxl-base-1.0'):
        return materialize_managed_cpu_candidate(self.catalog,self.candidate,self.source,model_id,
                                                 profile='cpu-metadata-verified')

    def test_all_86_pins_and_target_wheel_tags_are_complete(self):
        rows=self.candidate['artifacts'];self.assertEqual(len(rows),86)
        supported=set(cpython_tags((3,13),abis=['cp313'],platforms=['win_amd64']))
        supported.update(compatible_tags((3,13),interpreter='cp313',platforms=['win_amd64']))
        for row in rows:
            self.assertRegex(row['sha256'],r'^[0-9a-f]{64}$');self.assertGreater(row['size'],0)
            _,version,_,tags=parse_wheel_filename(row['filename'])
            self.assertEqual(version,Version(row['version']));self.assertTrue(tags.intersection(supported))
        self.assertEqual(sum(row['size'] for row in rows),self.candidate['total_wheel_bytes'])

    def test_target_dependency_constraints_and_root_requirements_close(self):
        rows={row['distribution']:row for row in self.candidate['artifacts']}
        lock={row['distribution']:row for row in self.candidate['requirements_lock']}
        target=self.candidate['target_marker_environment']
        for name,row in rows.items():
            expected=set()
            for text in row['requires_dist_metadata']:
                requirement=Requirement(text)
                active=not requirement.marker or any(requirement.marker.evaluate(dict(target,extra=e)) for e in ['']+row['selected_extras'])
                if active:
                    dependency=canonicalize_name(requirement.name)
                    self.assertIn(dependency,rows);self.assertIn(Version(rows[dependency]['version']),requirement.specifier)
                    expected.add(dependency)
            self.assertEqual(expected,set(lock[name]['requires']))
        for text in self.candidate['root_requirements']:
            requirement=Requirement(text)
            self.assertIn(Version(rows[canonicalize_name(requirement.name)]['version']),requirement.specifier)

    def test_candidate_is_off_by_default_and_not_runtime_acceptance(self):
        self.assertFalse(self.candidate['default_enabled'])
        self.assertEqual(self.candidate['runtime_acceptance'],'not_tested')
        self.assertEqual(self.candidate['package_payload_requests_performed'],0)
        self.assertFalse(self.catalog['release_ready'])
        with self.assertRaises(ManifestError):
            materialize_managed_cpu_candidate(self.catalog,self.candidate,self.source,'sdxl-base-1.0',profile='auto')

    def test_explicit_materialization_refuses_unpinned_model_license(self):
        with self.assertRaises(ManifestError):self.materialize('sd15-emaonly')
        with self.assertRaises(ManifestError):self.materialize('unknown')
        manifest=self.materialize()
        self.assertTrue(manifest['release_ready'])
        self.assertEqual(manifest['runtime_acceptance'],'not_tested')
        self.assertEqual(manifest['components']['comfy']['model_artifact_id'],'sdxl-base-1.0')
        self.assertEqual(len(manifest['components']['comfy']['wheel_ids']),86)

    def test_managed_trial_still_requires_audit_cpu_opt_in_fit_license_and_budget(self):
        manifest=self.materialize()
        plan={'mode':'managed','components':['study','comfy'],'device':'cpu','cpu_opt_in':True,
              'accepted_licenses':['openrail++'],'approved_download_bytes':20_000_000_000}
        with self.assertRaises(ManifestError):validate_manifest(manifest,plan,None)
        audit={'status':'COLLECTED_READ_ONLY','hostname':'LS5','collected_at_utc':datetime.now(timezone.utc).isoformat(),
               'os':[{'OSArchitecture':'64-bit'}],'ram':[{'TotalPhysicalMemory':64*1024**3}],
               'disks':[{'FreeSpace':100*1024**3}],'gpu':{}}
        plan['hardware_review']={'audit_sha256':audit_sha256(audit),'component_compatibility':'approved',
                                 'model_fit':{'model_id':'sdxl-base-1.0','requirements_reviewed':True,'min_ram_bytes':32*1024**3}}
        self.assertEqual(validate_manifest(manifest,plan,audit),manifest)
        for key,value in (('cpu_opt_in',False),('accepted_licenses',[]),('approved_download_bytes',0)):
            with self.assertRaises(ManifestError):validate_manifest(manifest,dict(plan,**{key:value}),audit)
        del plan['hardware_review']['model_fit']
        with self.assertRaises(ManifestError):validate_manifest(manifest,plan,audit)


if __name__=='__main__':unittest.main()
