"""Durable contract and recovery tests; external adapter lifecycle lives separately."""
import copy
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import semantic_composer as sc
from test_semantic_composer import graph, ASSET


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'compositions.sqlite3'
        self.store = sc.CompositionStore(self.path)
        self.revision = self.store.create(graph(), ['a'], parameters={
            'seed': 9007199254740991, 'width': 768, 'height': 768, 'steps': 35})

    def tearDown(self):
        self.tmp.cleanup()

    def test_request_contract_is_strict_and_lossless(self):
        expected = {'contract_version': 1, 'mode': 'text_to_image',
                    'prompt': self.revision['effective_prompt'], 'references': [],
                    'parameters': {'seed': 9007199254740991, 'width': 768, 'height': 768, 'steps': 35}}
        self.assertEqual(json.loads(json.dumps(sc.generation_request(self.revision))), expected)
        for mutation in (lambda r: r.update(schema_version=True),
                         lambda r: r.pop('parameters'),
                         lambda r: r['parameters'].pop('width'),
                         lambda r: r.update(parameters=None)):
            r = copy.deepcopy(self.revision)
            mutation(r)
            with self.subTest(revision=r), self.assertRaises(ValueError):
                sc.generation_request(r)

    def test_submission_intent_survives_crash_before_job_link(self):
        intent = self.store.prepare_submission(self.revision['revision_id'])
        recovered = sc.CompositionStore(self.path)
        state = recovered.recovery_state()
        self.assertEqual(state['unlinked_submissions'], [intent])
        self.assertEqual(state['unfinished_jobs'], [])
        self.assertEqual(intent['request'], sc.generation_request(self.revision))
        self.assertEqual(recovered.prepare_submission(self.revision['revision_id'],
                                                     request_id=intent['request_id']), intent)
        linked = recovered.record_job(self.revision['revision_id'], 'backend-local-id',
                                      backend='study_local', request_id=intent['request_id'])
        reopened = sc.CompositionStore(self.path)
        self.assertEqual(reopened.recovery_state()['unlinked_submissions'], [])
        self.assertEqual(reopened.recovery_state()['unfinished_jobs'][0]['job_id'], linked['job_id'])
        self.assertEqual(reopened.find_job('backend-local-id', backend='study_local'), linked)
        self.assertIsNone(reopened.find_job('backend-local-id', backend='comfyui'))
        # A retry of the bind is idempotent, not a duplicate job/history item.
        self.assertEqual(reopened.record_job(self.revision['revision_id'], 'backend-local-id',
                                            backend='study_local', request_id=intent['request_id']), linked)
        reopened.record_result(linked['job_id'], status='failed', error='restart_interrupted')
        self.assertEqual(reopened.recovery_state()['unfinished_jobs'], [])
        self.assertEqual(len(reopened.job_history(self.revision['revision_id'])), 1)

    def test_intent_mismatch_cannot_rebind_or_overwrite_history(self):
        first = self.store.prepare_submission(self.revision['revision_id'], request_id='stable-id')
        other = self.store.revise(self.revision['revision_id'], parameters={'seed': 1})
        with self.assertRaises(ValueError):
            self.store.prepare_submission(other['revision_id'], request_id='stable-id')
        with self.assertRaises(ValueError):
            self.store.record_job(other['revision_id'], 'job', backend='study_local', request_id='stable-id')
        with self.assertRaises(KeyError):
            self.store.record_job(self.revision['revision_id'], 'job', backend='study_local', request_id='missing')
        linked = self.store.record_job(self.revision['revision_id'], 'job', backend='study_local', request_id='stable-id')
        with self.assertRaises(ValueError):
            self.store.record_job(self.revision['revision_id'], 'different-job', backend='study_local', request_id='stable-id')
        with closing(sqlite3.connect(self.path)) as db:
            for table in ('semantic_submissions', 'semantic_submission_links'):
                with self.assertRaises(sqlite3.IntegrityError):
                    db.execute(f'DELETE FROM {table}')
        self.assertEqual(self.store.find_job('job', backend='study_local'), linked)
        self.assertEqual(first['request']['parameters']['seed'], 9007199254740991)

    def test_old_and_new_board_fixtures_remain_unchanged(self):
        import spatial_board
        fixtures = json.loads(Path(__file__).with_name('semantic_composer_cards.json').read_text(encoding='utf-8'))
        for case in fixtures:
            source = copy.deepcopy(case['graph'])
            spatial_board.validate(source)
            revision = self.store.create(source, case['roots'])
            self.assertEqual(json.loads(revision['source_graph_json']), source)
            self.assertEqual(source, case['graph'])
            self.assertEqual(revision['references'], case['expected_references'])
            self.assertEqual(sc.generation_request(revision)['references'], [])

    def test_legacy_uuid_spelling_is_normalized_only_in_manifest(self):
        g = graph()
        legacy = ASSET.replace('-', '').upper()
        g['nodes'][2]['asset_id'] = legacy
        g['nodes'][2]['image_assets'] = ['{' + ASSET + '}']
        result = sc.compose(g, ['a'])
        self.assertEqual(result['references'], [{'node_id': 'c', 'asset_id': ASSET}])
        self.assertEqual(json.loads(result['source_graph_json'])['nodes'][2]['asset_id'], legacy)

    def test_image_mode_never_creates_intent(self):
        image = self.store.revise(self.revision['revision_id'], mode='image_conditioned')
        with self.assertRaises(sc.UnsupportedMode):
            self.store.prepare_submission(image['revision_id'])
        self.assertEqual(self.store.recovery_state(), {'unlinked_submissions': [], 'unfinished_jobs': []})

    def test_concurrent_recovery_binds_one_history_entry(self):
        intent = self.store.prepare_submission(self.revision['revision_id'])
        def bind(_):
            return sc.CompositionStore(self.path).record_job(
                self.revision['revision_id'], 'one-persistent-local-id',
                backend='study_local', request_id=intent['request_id'])
        with ThreadPoolExecutor(max_workers=4) as pool:
            jobs = list(pool.map(bind, range(8)))
        self.assertTrue(all(job == jobs[0] for job in jobs))
        self.assertEqual(len(self.store.job_history(self.revision['revision_id'])), 1)
        self.assertEqual(len(self.store.recovery_state()['unfinished_jobs']), 1)

    def test_old_job_records_without_namespace_remain_readable(self):
        old = {'job_id': str(uuid4()), 'revision_id': self.revision['revision_id'],
               'prompt_id': str(uuid4()), 'request': sc.generation_request(self.revision),
               'created_at': '2026-11-07T00:00:00+00:00', 'reference_images_transmitted': False}
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('INSERT INTO semantic_jobs VALUES (?,?,?,?)',
                       (old['job_id'], old['revision_id'], old['prompt_id'], json.dumps(old)))
            db.commit()
        reopened = sc.CompositionStore(self.path)
        self.assertEqual(reopened.find_job(old['prompt_id']), old)
        self.assertIsNone(reopened.find_job(old['prompt_id'], backend='study_local'))
        self.assertEqual(reopened.recovery_state()['unfinished_jobs'], [old])

    def test_prepare_bad_ids_creates_no_side_effects(self):
        for request_id in ('', 'spaces not allowed', '../path', 0):
            with self.subTest(request_id=request_id), self.assertRaises(ValueError):
                self.store.prepare_submission(self.revision['revision_id'], request_id=request_id)
        with self.assertRaises(ValueError):
            self.store.record_job(self.revision['revision_id'], 'job', backend='unknown')
        self.assertEqual(self.store.recovery_state(), {'unlinked_submissions': [], 'unfinished_jobs': []})

    def test_cli_recovers_local_jobs_while_reporting_legacy_namespace(self):
        import io
        from contextlib import redirect_stdout
        from unittest.mock import patch
        import semantic_composer_example as example
        run_dir = Path(self.tmp.name) / 'cli'
        run_dir.mkdir()
        store = sc.CompositionStore(run_dir / 'semantic_compositions.sqlite')
        revision = store.create(graph(), ['a'])
        legacy = store.record_job(revision['revision_id'], str(uuid4()))
        local = store.record_job(revision['revision_id'], str(uuid4()), backend='study_local')
        adapter_file = run_dir / 'stub_adapter.py'
        adapter_file.write_text(
            'def configured(): return True\n'
            'def result(job_id):\n'
            f'    assert job_id == {local["prompt_id"]!r}, "Legacy IDs must never reach local lookup"\n'
            '    return {"status":"failed", "error":"fixture failure"}\n', encoding='utf-8')
        stdout = io.StringIO()
        with patch('sys.argv', ['example', '--recover', '--data-dir', str(run_dir),
                                '--adapter-file', str(adapter_file)]), redirect_stdout(stdout):
            exit_code = example.main()
        self.assertEqual(exit_code, 1)  # Explicit manual reconciliation remains.
        state = store.recovery_state()
        self.assertEqual(state['unfinished_jobs'], [legacy])
        self.assertEqual(store.job_history(revision['revision_id'])[1]['result']['status'], 'failed')
        self.assertIn('manual_reconciliation', stdout.getvalue())


if __name__ == '__main__':
    unittest.main()
