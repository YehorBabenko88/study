"""Behavioral contract for the standalone semantic composer."""
import copy
import json
import unittest
import tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing

import semantic_composer as sc

ASSET = '11111111-1111-4111-8111-111111111111'


def graph():
    return {'nodes': [
        {'id': 'a', 'type': 'syllable', 'text': 'Tas'},
        {'id': 'b', 'type': 'word', 'text': 'Tasse'},
        {'id': 'c', 'type': 'image', 'text': 'cup', 'asset_id': ASSET},
    ], 'edges': [
        {'from': 'a', 'to': 'b', 'relation': 'sound'},
        {'from': 'b', 'to': 'c', 'relation': 'meaning'},
        {'from': 'c', 'to': 'a', 'relation': 'association'},
    ], 'title': 'Original board'}


class CompilerTests(unittest.TestCase):
    def test_cycle_and_directed_semantics(self):
        scene = sc.compose(graph(), ['a'])
        self.assertEqual(scene['selected_node_ids'], ['a', 'b', 'c'])
        self.assertEqual(len(scene['selected_edges']), 3)
        self.assertIn('"a" sounds like "b"', scene['suggested_prompt'])
        self.assertIn('"b" means "c"', scene['suggested_prompt'])
        self.assertIn('one unified mnemonic scene', scene['suggested_prompt'])
        self.assertEqual(scene['references'], [{'node_id': 'c', 'asset_id': ASSET}])

    def test_order_independent_prompt_and_fingerprint(self):
        a = graph()
        b = copy.deepcopy(a)
        b['nodes'].reverse()
        b['edges'].reverse()
        first = sc.compose(a, ['c', 'a'])
        second = sc.compose(b, ['a', 'c'])
        self.assertEqual(first['suggested_prompt'], second['suggested_prompt'])
        self.assertEqual(first['scene_fingerprint'], second['scene_fingerprint'])

    def test_direction_and_depth_boundary(self):
        g = graph()
        g['edges'].pop()
        outgoing = sc.compose(g, ['b'], max_depth=1)
        incoming = sc.compose(g, ['b'], direction='incoming', max_depth=1)
        both = sc.compose(g, ['b'], direction='both', max_depth=0)
        self.assertEqual(outgoing['selected_node_ids'], ['b', 'c'])
        self.assertEqual(incoming['selected_node_ids'], ['a', 'b'])
        self.assertIn('"a" sounds like "b"', incoming['suggested_prompt'])
        self.assertEqual(both['selected_node_ids'], ['b'])
        self.assertTrue(both['depth_limited'])
        self.assertFalse(outgoing['depth_limited'])

    def test_all_relations_and_legacy_defaults(self):
        phrases = {'association': 'is associated with', 'part_of': 'is part of',
                   'sequence': 'comes before', 'meaning': 'means',
                   'sound': 'sounds like', 'action': 'acts on'}
        for relation, phrase in phrases.items():
            with self.subTest(relation=relation):
                g = graph()
                g['edges'] = [{'from': 'a', 'to': 'b', 'relation': relation}]
                self.assertIn('"a" ' + phrase + ' "b"', sc.compose(g, ['a'])['suggested_prompt'])
        g['edges'][0].pop('relation')
        self.assertIn('is associated with', sc.compose(g, ['a'])['suggested_prompt'])

    def test_snapshot_preserves_original_and_manual_edit_is_separate(self):
        g = graph()
        g['nodes'][0]['text'] = 'Tas\x00\n  se'
        original = copy.deepcopy(g)
        result = sc.compose(g, ['a'], user_prompt='A cup balancing on a tower.')
        self.assertEqual(g, original)
        self.assertEqual(json.loads(result['source_graph_json']), original)
        self.assertIn('Tas se', result['suggested_prompt'])
        self.assertNotIn('\x00', result['suggested_prompt'])
        self.assertEqual(result['effective_prompt'], 'A cup balancing on a tower.')
        self.assertNotEqual(result['source_description'], result['user_prompt'])
        g['nodes'][0]['text'] = 'changed'
        self.assertEqual(json.loads(result['source_graph_json']), original)

    def test_rejects_invalid_graphs(self):
        invalid = [None, [], {'nodes': [], 'edges': []}]
        for mutation in (
            lambda g: g['nodes'].append(copy.deepcopy(g['nodes'][0])),
            lambda g: g['nodes'][0].update(type='unknown'),
            lambda g: g['nodes'][0].update(id=''),
            lambda g: g['nodes'][0].update(text=123),
            lambda g: g['nodes'][0].update(x=float('nan')),
            lambda g: g['nodes'][0].update(asset_id='../secret'),
            lambda g: g['edges'][0].update(to='missing'),
            lambda g: g['edges'][0].update(relation='unknown'),
            lambda g: g.update(metadata={1: 'not a JSON key'}),
        ):
            g = graph()
            mutation(g)
            invalid.append(g)
        for g in invalid:
            with self.subTest(graph=g), self.assertRaises(ValueError):
                sc.compose(g, ['a'])

    def test_rejects_bad_options(self):
        for options in ({'direction': 'sideways'}, {'max_depth': True},
                        {'max_depth': -1}, {'max_depth': 33}, {'max_nodes': 0},
                        {'max_edges': 257}, {'mode': 'gallery'},
                        {'parameters': {'seed': True}}, {'parameters': {'seed': -1}},
                        {'parameters': {'width': 1024}}, {'parameters': {'steps': 36}},
                        {'parameters': {'unknown': 1}}, {'user_prompt': ''},
                        {'user_prompt': 'x' * 1201}, {'user_prompt': '\x00'}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                sc.compose(graph(), ['a'], **options)
        for roots in ([], ['missing'], 'a', ['a', 'a'], [None]):
            with self.subTest(roots=roots), self.assertRaises(ValueError):
                sc.compose(graph(), roots)

    def test_limits_reject_instead_of_silent_truncation(self):
        for opts in ({'max_nodes': 2}, {'max_edges': 2}):
            with self.assertRaises(ValueError):
                sc.compose(graph(), ['a'], **opts)
        g = graph()
        g['nodes'][0]['text'] = 'a' * 1200
        with self.assertRaises(ValueError):
            sc.compose(g, ['a'])
        g = {'nodes': [{'id': str(i), 'type': 'letter'} for i in range(1001)], 'edges': []}
        with self.assertRaises(ValueError):
            sc.compose(g, ['0'])

    def test_references_deduplicate_and_require_real_assets(self):
        g = graph()
        g['nodes'][2]['image_assets'] = [ASSET]
        result = sc.compose(g, ['a'], mode='image_conditioned')
        self.assertEqual(len(result['references']), 1)
        self.assertFalse(result['reference_images_transmitted'])
        g['nodes'][2].pop('asset_id')
        g['nodes'][2].pop('image_assets')
        with self.assertRaises(ValueError):
            sc.compose(g, ['a'], mode='image_conditioned')


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'composer.sqlite3'
        self.store = sc.CompositionStore(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_versions_are_durable_and_detached(self):
        g = graph()
        first = self.store.create(g, ['a'])
        original = copy.deepcopy(first)
        second = self.store.revise(first['revision_id'], parameters={'seed': 42}, user_prompt='A giant cup.')
        self.assertEqual(second['version'], 2)
        self.assertEqual(second['parent_revision_id'], first['revision_id'])
        self.assertEqual(second['composition_id'], first['composition_id'])
        self.assertEqual(second['parameters']['seed'], 42)
        self.assertEqual(second['parameters']['steps'], 20)
        self.assertEqual(second['source_graph_json'], first['source_graph_json'])
        self.assertEqual(second['suggested_prompt'], first['suggested_prompt'])
        third = self.store.revise(second['revision_id'], user_prompt=None)
        self.assertEqual(third['effective_prompt'], third['suggested_prompt'])
        first['parameters']['seed'] = 99
        g['nodes'].clear()
        reopened = sc.CompositionStore(self.path)
        self.assertEqual(reopened.get(original['revision_id']), original)
        self.assertEqual([r['version'] for r in reopened.history(first['composition_id'])], [1, 2, 3])

    def test_branching_and_parallel_revisions_do_not_overwrite(self):
        first = self.store.create(graph(), ['a'])
        def revise(seed):
            return sc.CompositionStore(self.path).revise(first['revision_id'], parameters={'seed': seed})
        with ThreadPoolExecutor(max_workers=4) as pool:
            revisions = list(pool.map(revise, range(8)))
        self.assertEqual(sorted(r['version'] for r in revisions), list(range(2, 10)))
        self.assertEqual(len(self.store.history(first['composition_id'])), 9)
        self.assertTrue(all(r['parent_revision_id'] == first['revision_id'] for r in revisions))

    def test_job_provenance_and_retry_are_append_only(self):
        revision = self.store.create(graph(), ['a'], parameters={'seed': 7})
        job = self.store.record_job(revision['revision_id'], 'comfy-task-1')
        event = self.store.record_result(job['job_id'], status='failed', error='GPU unavailable')
        retry = self.store.record_job(revision['revision_id'], 'comfy-task-2')
        output = {'asset_id': ASSET, 'sha256': 'a' * 64}
        self.store.record_result(retry['job_id'], status='complete', outputs=[output])
        history = self.store.job_history(revision['revision_id'])
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]['result'], event)
        self.assertEqual(history[1]['result']['outputs'], [output])
        self.assertEqual(history[1]['revision_id'], revision['revision_id'])
        self.assertEqual(history[1]['request']['parameters']['seed'], 7)
        self.assertEqual(history[1]['request']['mode'], 'text_to_image')
        self.assertEqual(history[1]['request']['references'], [])
        self.assertEqual(self.store.get(revision['revision_id'])['references'][0]['asset_id'], ASSET)
        with self.assertRaises(ValueError):
            self.store.record_result(retry['job_id'], status='failed', error='overwrite')

    def test_invalid_writes_leave_history_unchanged(self):
        first = self.store.create(graph(), ['a'])
        for options in ({'parameters': {'seed': -1}}, {'user_prompt': ''}, {'mode': 'bad'}):
            with self.assertRaises(ValueError):
                self.store.revise(first['revision_id'], **options)
        with self.assertRaises(KeyError):
            self.store.revise('missing')
        with self.assertRaises(KeyError):
            self.store.record_job('missing', 'job')
        for prompt_id in ('', 'a' * 201, None):
            with self.assertRaises(ValueError):
                self.store.record_job(first['revision_id'], prompt_id)
        job = self.store.record_job(first['revision_id'], 'job-1')
        for options in ({'status': 'complete', 'outputs': []},
                        {'status': 'complete', 'outputs': [{'asset_id': ASSET, 'sha256': 'bad'}]},
                        {'status': 'failed'}, {'status': 'queued'},
                        {'status': 'failed', 'error': 'failed', 'outputs': [{'asset_id': ASSET}]}):
            with self.assertRaises(ValueError):
                self.store.record_result(job['job_id'], **options)
        self.assertEqual(len(self.store.history(first['composition_id'])), 1)
        self.assertIsNone(self.store.job_history(first['revision_id'])[0]['result'])

    def test_text_request_and_disabled_image_mode(self):
        first = self.store.create(graph(), ['a'], parameters={'seed': 13, 'steps': 25})
        request = sc.generation_request(first)
        self.assertEqual(request, {'contract_version': 1, 'mode': 'text_to_image',
                                  'prompt': first['effective_prompt'],
                                  'parameters': {'seed': 13, 'width': 512, 'height': 512, 'steps': 25},
                                  'references': []})
        image = self.store.revise(first['revision_id'], mode='image_conditioned')
        with self.assertRaises(sc.UnsupportedMode):
            sc.generation_request(image)
        with self.assertRaises(sc.UnsupportedMode):
            self.store.record_job(image['revision_id'], 'not-really-uploaded')
        self.assertEqual(self.store.job_history(image['revision_id']), [])

    def test_database_rejects_updates_and_deletes(self):
        import sqlite3
        first = self.store.create(graph(), ['a'])
        with closing(sqlite3.connect(self.path)) as db:
            for sql in ('DELETE FROM semantic_revisions',
                        "UPDATE semantic_revisions SET payload='{}'"):
                with self.assertRaises(sqlite3.IntegrityError):
                    db.execute(sql)
        self.assertEqual(self.store.get(first['revision_id']), first)

    def test_large_valid_source_roundtrips_inside_history_envelope(self):
        g = graph()
        g['metadata'] = '"' * 600_000
        revision = self.store.create(g, ['a'])
        self.assertEqual(json.loads(self.store.get(revision['revision_id'])['source_graph_json']), g)

    def test_all_history_tables_are_append_only_and_duplicate_job_rejects(self):
        import sqlite3
        revision = self.store.create(graph(), ['a'])
        job = self.store.record_job(revision['revision_id'], 'unique-comfy-id')
        self.store.record_result(job['job_id'], status='failed', error='out of memory')
        with self.assertRaises(ValueError):
            self.store.record_job(revision['revision_id'], 'unique-comfy-id')
        with self.assertRaises(KeyError):
            self.store.record_result('missing', status='failed', error='error')
        with closing(sqlite3.connect(self.path)) as db:
            for table in ('semantic_jobs', 'semantic_results'):
                for operation in ('DELETE FROM', "UPDATE"):
                    sql = f'{operation} {table}'
                    if operation == 'UPDATE':
                        sql += " SET payload='{}'"
                    with self.assertRaises(sqlite3.IntegrityError):
                        db.execute(sql)
        self.assertEqual(len(self.store.job_history(revision['revision_id'])), 1)


class BoundaryTests(unittest.TestCase):
    def test_empty_labels_and_self_loop(self):
        g = {'nodes': [{'id': 'n', 'type': 'letter'}],
             'edges': [{'from': 'n', 'to': 'n', 'relation': 'part_of'}]}
        scene = sc.compose(g, ['n'])
        self.assertIn('"n" (letter): ""', scene['suggested_prompt'])
        self.assertIn('"n" is part of "n"', scene['suggested_prompt'])
        self.assertFalse(scene['depth_limited'])

    def test_wrong_container_values_are_validation_errors(self):
        for field, value in (('type', []), ('type', {})):
            g = graph()
            g['nodes'][0][field] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                sc.compose(g, ['a'])
        for value in ([], {}):
            g = graph()
            g['edges'][0]['relation'] = value
            with self.subTest(relation=value), self.assertRaises(ValueError):
                sc.compose(g, ['a'])

    def test_reference_limit_and_multiple_node_provenance(self):
        g = graph()
        g['nodes'][0]['image_assets'] = [ASSET]
        self.assertEqual(sc.compose(g, ['a'])['references'],
                         [{'node_id': 'a', 'asset_id': ASSET}, {'node_id': 'c', 'asset_id': ASSET}])
        g['nodes'][0]['image_assets'] = [f'{i:08x}-1111-4111-8111-111111111111' for i in range(9)]
        with self.assertRaises(ValueError):
            sc.compose(g, ['a'])

    def test_input_size_and_nested_json_limit(self):
        g = graph()
        g['metadata'] = 'x' * 2_000_000
        with self.assertRaises(ValueError):
            sc.compose(g, ['a'])
        g = graph()
        g['edges'] *= 1001
        with self.assertRaises(ValueError):
            sc.compose(g, ['a'])
        nested = []
        for _ in range(34):
            nested = [nested]
        g = graph()
        g['metadata'] = nested
        with self.assertRaises(ValueError):
            sc.compose(g, ['a'])

    def test_fingerprint_changes_with_direction_relation_seed_and_edit(self):
        first = sc.compose(graph(), ['b'])['scene_fingerprint']
        for opts in ({'direction': 'incoming'}, {'parameters': {'seed': 9}}, {'user_prompt': 'A new scene.'}):
            self.assertNotEqual(first, sc.compose(graph(), ['b'], **opts)['scene_fingerprint'])
        g = graph()
        g['edges'][0]['relation'] = 'part_of'
        self.assertNotEqual(first, sc.compose(g, ['b'])['scene_fingerprint'])

    def test_text_request_parameters_match_existing_comfy_workflow(self):
        import comfy_adapter
        from unittest.mock import patch
        request = sc.generation_request(sc.compose(graph(), ['a'], parameters={
            'seed': 1234, 'width': 768, 'height': 512, 'steps': 31}))
        with patch.dict('os.environ', {'STUDY_COMFYUI_CHECKPOINT': 'reviewed.safetensors'}):
            workflow = comfy_adapter.workflow(request['prompt'], **request['parameters'])
        self.assertEqual(workflow['2']['inputs']['text'], request['prompt'])
        self.assertEqual(workflow['4']['inputs']['width'], 768)
        self.assertEqual(workflow['4']['inputs']['height'], 512)
        self.assertEqual(workflow['5']['inputs']['seed'], 1234)
        self.assertEqual(workflow['5']['inputs']['steps'], 31)


if __name__ == '__main__':
    unittest.main()
