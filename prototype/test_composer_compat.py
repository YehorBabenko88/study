"""Compatibility fixes from PR #16 without replacing the unified service journal."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from uuid import UUID

from semantic_composer import compose, generation_request, CompositionStore


class ComposerCompatibilityTests(unittest.TestCase):
    def graph(self, asset='AABBCCDD-1234-5678-ABCD-1234567890AB'):
        return {'nodes': [{'id': 'image', 'type': 'image', 'text': 'old board image',
                           'asset_id': asset, 'image_assets': [asset]}], 'edges': []}

    def test_legacy_uuid_spellings_normalize_manifest_only(self):
        canonical = 'aabbccdd-1234-5678-abcd-1234567890ab'
        spellings = [canonical.upper(), canonical.replace('-', ''), '{'+canonical+'}', 'urn:uuid:'+canonical]
        for spelling in spellings:
            with self.subTest(spelling=spelling):
                graph = self.graph(spelling); before = copy.deepcopy(graph)
                revision = compose(graph, ['image'])
                self.assertEqual(revision['references'], [{'node_id': 'image', 'asset_id': canonical}])
                self.assertEqual(json.loads(revision['source_graph_json']), before)
                self.assertEqual(graph, before)

    def test_aliases_in_gallery_deduplicate_normalized_manifest(self):
        graph = self.graph()
        graph['nodes'][0]['image_assets'].append(str(UUID(graph['nodes'][0]['asset_id'])))
        self.assertEqual(len(compose(graph, ['image'])['references']), 1)

    def test_roundtrip_preserves_raw_source_and_output_ids_remain_strict(self):
        graph = self.graph('{AABBCCDD-1234-5678-ABCD-1234567890AB}')
        with tempfile.TemporaryDirectory() as folder:
            store = CompositionStore(Path(folder)/'compositions.sqlite')
            revision = store.create(graph, ['image'])
            revised = store.revise(revision['revision_id'], user_prompt='Reviewed legacy image')
            self.assertEqual(json.loads(revised['source_graph_json']), graph)
            self.assertEqual(revised['references'], revision['references'])
            job = store.record_job(revision['revision_id'], 'upstream-real-job')
            with self.assertRaises(ValueError):
                store.record_result(job['job_id'], status='complete', outputs=[{
                    'asset_id': graph['nodes'][0]['asset_id'], 'sha256': 'a'*64}])

    def test_schema_version_must_be_integer_one(self):
        revision = compose(self.graph('aabbccdd-1234-5678-abcd-1234567890ab'), ['image'])
        for value in (True, False, 1.0, '1', None, 2):
            with self.subTest(value=value):
                invalid = {**revision, 'schema_version': value}
                with self.assertRaises(ValueError): generation_request(invalid)
        self.assertEqual(generation_request(revision)['contract_version'], 1)

    def test_saved_parameters_require_exact_keys(self):
        revision = compose(self.graph('aabbccdd-1234-5678-abcd-1234567890ab'), ['image'],
                           parameters={'seed': 47, 'width': 768, 'height': 512, 'steps': 13})
        self.assertEqual(generation_request(revision)['parameters'], revision['parameters'])
        invalid_parameters = [None, {}, {'seed': 47}, {**revision['parameters'], 'extra': 1}]
        invalid_parameters += [{k: v for k, v in revision['parameters'].items() if k != omitted}
                               for omitted in revision['parameters']]
        for parameters in invalid_parameters:
            with self.subTest(parameters=parameters):
                with self.assertRaises(ValueError): generation_request({**revision, 'parameters': parameters})
        # Creation accepts a partial user parameter override and persists all defaults.
        self.assertEqual(compose(self.graph('aabbccdd-1234-5678-abcd-1234567890ab'), ['image'], parameters={'seed': 7})['parameters'],
                         {'seed': 7, 'width': 512, 'height': 512, 'steps': 20})

if __name__ == '__main__': unittest.main()
