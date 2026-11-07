"""Executable backend-A handoff: durable submit, restart recovery and image history.

This example never replaces the adapter or changes shared application files.
Only an explicitly enabled real adapter may generate images through the CLI.
Tests exercise the same functions with A's real registry and a protocol fixture.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import time
from uuid import UUID, uuid4

from semantic_composer import CompositionStore


def submit_revision(store, backend, revision_id):
    """Create a durable intent, submit exact parameters, then atomically bind ID."""
    return resume_submission(store, backend, store.prepare_submission(revision_id))


def resume_submission(store, backend, intent):
    """Repeat an intent after restart, using A's idempotent request_id unchanged."""
    canonical = store.prepare_submission(intent['revision_id'], request_id=intent['request_id'])
    if canonical != intent:
        raise ValueError('Do not mutate persisted submission intents')
    request = canonical['request']
    # Works with JobRegistry.submit and the public module submit. Deliberately
    # fails on an old adapter rather than silently dropping size/step settings.
    accepted = backend.submit(request['prompt'], **request['parameters'],
                              request_id=canonical['request_id'])
    if (not isinstance(accepted, dict)
            or accepted.get('status') not in ('queued', 'running', 'complete', 'failed',
                                              'cancelled', 'timed_out', 'interrupted')):
        raise RuntimeError('Backend did not accept a persistent generation job')
    local_id = accepted.get('job_id', accepted.get('prompt_id'))
    if not isinstance(local_id, str) or str(UUID(local_id)) != local_id:
        raise ValueError('Backend must return a canonical local job UUID')
    if accepted.get('prompt_id', local_id) != local_id:
        raise ValueError('Ambiguous backend job ID aliases')
    if accepted.get('request_id') != canonical['request_id']:
        raise ValueError('Backend response must retain the submitted request_id')
    return store.record_job(canonical['revision_id'], local_id, backend='study_local',
                            request_id=canonical['request_id'])


def collect_result(store, adapter, job, save_asset):
    """Poll once; save new images after backend validation; append one final event.

    save_asset(png_bytes) must return a new asset_id and SHA-256 of stored bytes.
    Never reuse an original asset ID. Existing terminal records return unchanged.
    """
    canonical = store.find_job(job['prompt_id'], backend='study_local')
    if canonical is None or canonical != job:
        raise ValueError('Expected an unmodified stored study_local job')
    history = store.job_history(job['revision_id'])
    previous = next(item['result'] for item in history if item['job_id'] == job['job_id'])
    if previous is not None:
        return previous
    state = adapter.result(job['prompt_id'])
    status = state.get('status')
    if status in ('queued', 'running', 'pending'):
        return None
    if status in ('failed', 'cancelled', 'timed_out', 'interrupted'):
        return store.record_result(job['job_id'], status='failed', error=json.dumps(
            {'backend_status': status, 'error': state.get('error')}, ensure_ascii=False, sort_keys=True))
    if status != 'complete' or not isinstance(state.get('images'), list) or not 1 <= len(state['images']) <= 8:
        raise ValueError('Expected complete backend result with 1..8 image descriptors')
    outputs = []
    for image in state['images']:
        data = adapter.image_bytes(job['prompt_id'], image['filename'], image.get('subfolder', ''))
        outputs.append(save_asset(data))
    return store.record_result(job['job_id'], status='complete', outputs=outputs)


class DirectoryAssets:
    """Minimal non-destructive example store; production uses board_assets + hash."""
    def __init__(self, directory):
        self.directory = Path(directory)

    def save(self, data):
        if not isinstance(data, bytes) or not 1 <= len(data) <= 8_000_000:
            raise ValueError('Expected validated PNG bytes, at most 8 MB')
        self.directory.mkdir(parents=True, exist_ok=True)
        asset_id = str(uuid4())
        path = self.directory / (asset_id + '.png')
        with path.open('xb') as output:
            output.write(data)
        return {'asset_id': asset_id, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--adapter-file', type=Path, default=Path(__file__).with_name('comfy_adapter.py'))
    parser.add_argument('--timeout', type=float, default=120)
    parser.add_argument('--recover', action='store_true', help='resume existing intents/jobs instead of creating another scene')
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('semantic_example_adapter', args.adapter_file)
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    if not adapter.configured():
        parser.error('Explicit STUDY_COMFYUI_ENABLED=1 and a reviewed checkpoint are required')
    args.data_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault('STUDY_COMFYUI_DB', str(args.data_dir / 'comfy_jobs.sqlite'))
    store = CompositionStore(args.data_dir / 'semantic_compositions.sqlite')
    assets = DirectoryAssets(args.data_dir / 'generated_assets')
    try:
        if args.recover:
            for intent in store.recovery_state()['unlinked_submissions']:
                resume_submission(store, adapter, intent)
        else:
            case = json.loads(Path(__file__).with_name('semantic_composer_cards.json').read_text(encoding='utf-8'))[1]
            revision = store.create(case['graph'], case['roots'])
            edited = store.revise(revision['revision_id'], user_prompt='A giant cup rides a tiny train.',
                                  parameters={'seed': 12345, 'width': 768, 'height': 512, 'steps': 29})
            submit_revision(store, adapter, edited['revision_id'])
        deadline = time.monotonic() + args.timeout
        legacy = [job['job_id'] for job in store.recovery_state()['unfinished_jobs']
                  if job.get('backend', 'comfyui') != 'study_local']
        if legacy:
            print(json.dumps({'manual_reconciliation': legacy,
                              'reason': 'Legacy upstream IDs cannot be polled as Study local queue IDs'}))
        while time.monotonic() < deadline:
            jobs = [job for job in store.recovery_state()['unfinished_jobs']
                    if job.get('backend', 'comfyui') == 'study_local']
            if not jobs:
                break
            for job in jobs:
                outcome = collect_result(store, adapter, job, assets.save)
                if outcome:
                    print(json.dumps(outcome, ensure_ascii=False))
            time.sleep(.1)
        remaining = store.recovery_state()
        print(json.dumps(remaining, ensure_ascii=False))
        return 1 if remaining['unfinished_jobs'] or remaining['unlinked_submissions'] else 0
    finally:
        if getattr(adapter, '_registry', None) is not None:
            adapter._registry.close()


if __name__ == '__main__':
    raise SystemExit(main())
