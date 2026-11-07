"""Remove one owned component, retaining data/models and refusing External installs."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import time
from uuid import uuid4
import portable_ops as ops
from resumable_download import atomic_json
from installer_engine import transaction_lock


def canonical_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _safe(path):
    path = Path(path)
    for parent in (path, *path.parents):
        if os.path.lexists(parent) and ops.linked(parent): raise ValueError('Linked uninstall path refused')
    return path.resolve()


def _digest(path):
    return ops.digest(path)


def _owned(config, component):
    if component not in ('study', 'comfy'): raise ValueError('Choose exactly one component')
    root = _safe(config['app_root'])
    if root == Path(root.anchor): raise ValueError('Dedicated application root required')
    pointer = root/'run/active.json'
    if not pointer.is_file(): raise ValueError('No managed active ownership pointer')
    active = json.loads(pointer.read_text(encoding='utf-8'))
    if active.get('schema_version') != 1 or active.get('target_host') != 'LS5': raise ValueError('Invalid active ownership pointer')
    descriptor = active.get('components', {}).get(component)
    if not isinstance(descriptor, dict) or descriptor.get('mode') != 'managed' or descriptor.get('owner') != 'study-installer':
        raise ValueError('External, disabled or unowned component must never be removed')
    candidate = _safe(descriptor['root'])
    relative = candidate.relative_to(root/'releases')
    if len(relative.parts) != 2 or relative.parts[-1] != component: raise ValueError('Unexpected immutable component root')
    marker_path = candidate/'.study-managed-component.json'
    if not marker_path.is_file(): raise ValueError('Managed component ownership marker is missing')
    marker = json.loads(marker_path.read_text(encoding='utf-8'))
    if (marker.get('schema_version') != 1 or marker.get('owner') != 'study-installer'
            or marker.get('component') != component or _safe(marker.get('component_root', '')) != candidate
            or marker.get('transaction_id') != descriptor.get('transaction_id')
            or not isinstance(marker.get('manifest_sha256'), str) or len(marker['manifest_sha256']) != 64):
        raise ValueError('Managed component ownership marker mismatch')
    protected = [root/'models', root/'retained', root/'backups', root/'venvs']
    for source in (config.get('study', {}).get('data_dir'), active.get('data_dir')):
        if source: protected.append(_safe(source))
    for name, other in active.get('components', {}).items():
        if name != component and isinstance(other, dict) and other.get('root'): protected.append(_safe(other['root']))
    if any(ops.inside(candidate, path) or ops.inside(path, candidate) for path in protected):
        raise ValueError('Component overlaps data, models or another environment')
    ops.safe_files(candidate)
    return root, pointer, active, descriptor, candidate, marker_path


def _retention(candidate, component):
    """Legacy state found inside owned code is copied out, never discarded."""
    directories = []
    files = []
    if component == 'study':
        prototype = candidate/'code/prototype'
        for name in ('board_assets', 'generated_media', 'speech_audio', 'document_uploads'):
            path = prototype/name
            if path.is_dir(): directories.append(path)
        for prefix in ('study_local.sqlite3', 'study_lexicon.sqlite3', 'comfy_jobs.sqlite', 'compositions.sqlite'):
            if prototype.exists(): files.extend(p for p in prototype.glob(prefix+'*') if p.is_file())
    else:
        for name in ('input', 'output', 'user', 'models'):
            path = candidate/'code'/name
            if path.is_dir(): directories.append(path)
    for directory in directories: files.extend(ops.safe_files(directory))
    return [{'path': path.relative_to(candidate).as_posix(), 'size': path.stat().st_size, 'sha256': _digest(path)}
            for path in sorted(set(files))]


def _inventory(candidate):
    return [{'path': path.relative_to(candidate).as_posix(), 'size': path.stat().st_size, 'sha256': _digest(path)}
            for path in ops.safe_files(candidate)]


def build_uninstall_plan(config, component):
    root, pointer, active, descriptor, candidate, marker = _owned(config, component)
    retained = _retention(candidate, component)
    transaction = str(uuid4())
    return {'schema_version': 1, 'operation': 'uninstall', 'target_host': 'LS5', 'component': component,
            'app_root': str(root), 'data_dir': active.get('data_dir', config['study']['data_dir']),
            'component_root': str(candidate), 'active_sha256': _digest(pointer), 'marker_sha256': _digest(marker),
            'component_inventory': _inventory(candidate),
            'transaction_id': transaction, 'retained_root': str(root/'retained'/transaction/component),
            'retained_files': retained, 'retained_bytes': sum(row['size'] for row in retained),
            'models_preserved': True, 'data_preserved': True}


def assert_component_offline(root, component):
    if (root/'run'/(component+'.json')).exists(): raise ValueError('Stop the selected owned component before removal')
    with socket.socket() as connection:
        connection.settimeout(.5)
        if connection.connect_ex(('127.0.0.1', 8766 if component == 'study' else 8188)) == 0:
            raise ValueError('Selected component port is occupied; nothing was stopped')


def _verify_retained(plan, root):
    owner = json.loads((root/'.retention-owner.json').read_text(encoding='utf-8'))
    if owner != {'owner': 'study-installer', 'operation': 'uninstall-retention', 'plan_sha256': canonical_digest(plan)}:
        raise ValueError('Retained data directory ownership mismatch')
    manifest = json.loads((root/'retention-manifest.json').read_text(encoding='utf-8'))
    if manifest != {'plan_sha256': canonical_digest(plan), 'files': plan['retained_files']}:
        raise ValueError('Retention manifest does not match approved removal')
    for entry in plan['retained_files']:
        path = _safe(root/entry['path'])
        if not ops.inside(path, root) or path.stat().st_size != entry['size'] or _digest(path) != entry['sha256']:
            raise ValueError('Retained user data is not verified; removal cannot continue')


def _finish_removal(plan, state, pointer, journal, candidate, retained_root):
    _verify_retained(plan, retained_root)
    if candidate.exists():
        marker = candidate/'.study-managed-component.json'
        if not marker.exists():
            if any(candidate.iterdir()): raise ValueError('Residual component lost its ownership marker; refusing recursive removal')
            candidate.rmdir()
            state['state'] = 'removed'; atomic_json(journal, state)
            return {key: state[key] for key in ('state', 'component', 'component_root', 'retained_root')}
        if _digest(marker) != plan['marker_sha256']: raise ValueError('Residual component ownership was replaced')
        approved = {entry['path']: entry for entry in plan['component_inventory']}
        for entry in _inventory(candidate):
            if approved.get(entry['path']) != entry: raise ValueError('Residual component has unapproved or changed files')
        expected = {row['path']: row for row in plan['retained_files']}
        for row in _retention(candidate, plan['component']):
            if expected.get(row['path']) != row: raise ValueError('New legacy data appeared; review a fresh preservation plan')
        _remove_owned_tree(candidate, plan['component_inventory'], plan['marker_sha256'])
    state['state'] = 'removed'; atomic_json(journal, state)
    return {key: state[key] for key in ('state', 'component', 'component_root', 'retained_root')}


def _remove_owned_tree(candidate, inventory, marker_sha256):
    """Delete recorded files only; retain ownership marker through partial removal."""
    approved = {entry['path']: entry for entry in inventory}
    marker = candidate/'.study-managed-component.json'
    for path in ops.safe_files(candidate):
        if path == marker: continue
        entry = approved.get(path.relative_to(candidate).as_posix())
        if not entry or _safe(path) != path or path.stat().st_size != entry['size'] or _digest(path) != entry['sha256']:
            raise ValueError('Unlisted/changed file refused during owned removal')
        path.unlink()
    directories = sorted((path for path in candidate.rglob('*') if path.is_dir()), key=lambda path: len(path.parts), reverse=True)
    for directory in directories:
        if _safe(directory) != directory: raise ValueError('Linked residual directory refused')
        directory.rmdir()  # Nonrecursive: any new/unrecorded file prevents removal.
    if _digest(marker) != marker_sha256: raise ValueError('Ownership marker changed before final removal')
    if set(candidate.iterdir()) != {marker}: raise ValueError('Unlisted residual root entries refused')
    marker.unlink()
    candidate.rmdir()


def execute_uninstall(plan, approval):
    if socket.gethostname().upper() != 'LS5': raise ValueError('Uninstall is restricted to LS5')
    if (plan.get('schema_version') != 1 or plan.get('operation') != 'uninstall' or plan.get('target_host') != 'LS5'
            or approval.get('approved') is not True or approval.get('plan_sha256') != canonical_digest(plan)
            or not isinstance(approval.get('expires_at'), (int, float)) or approval['expires_at'] < time.time()):
        raise ValueError('Explicit exact-plan uninstall approval required')
    root = _safe(plan['app_root']); candidate = _safe(plan['component_root']); retained_root = _safe(plan['retained_root'])
    if not ops.inside(retained_root, root/'retained') or retained_root == root/'retained': raise ValueError('Unsafe retained-data destination')
    config = {'target_host': 'LS5', 'app_root': str(root), 'study': {'data_dir': plan['data_dir']}}
    with transaction_lock(config):
        journal = root/'run'/('uninstall-'+plan['transaction_id']+'.json')
        if journal.exists():
            recovery = json.loads(journal.read_text(encoding='utf-8'))
            if recovery.get('plan_sha256') != canonical_digest(plan): raise ValueError('Recovery journal belongs to a different plan')
            if recovery.get('state') in ('retention_verified', 'deactivated', 'removed'):
                pointer = root/'run/active.json'; active = json.loads(pointer.read_text(encoding='utf-8'))
                deactivated = (active.get('last_uninstall', {}).get('transaction_id') == plan['transaction_id']
                               and plan['component'] not in active.get('components', {}))
                if deactivated:
                    if candidate != root/'releases'/candidate.parent.name/plan['component']:
                        raise ValueError('Unsafe recovery component root')
                    assert_component_offline(root, plan['component'])
                    return _finish_removal(plan, recovery, pointer, journal, candidate, retained_root)
                if recovery.get('state') in ('deactivated', 'removed'):
                    raise ValueError('Active installation changed; removal recovery refused')
        _, pointer, active, descriptor, verified, marker = _owned(config, plan['component'])
        if (verified != candidate or _digest(pointer) != plan['active_sha256'] or _digest(marker) != plan['marker_sha256']
                or _retention(candidate, plan['component']) != plan['retained_files']
                or _inventory(candidate) != plan['component_inventory']):
            raise ValueError('Uninstall plan is stale; review a fresh plan')
        assert_component_offline(root, plan['component'])
        if shutil.disk_usage(root).free < plan['retained_bytes'] + 1_000_000: raise ValueError('Not enough space to preserve legacy data')
        state = {'state': 'preserving', 'plan_sha256': canonical_digest(plan), 'component': plan['component'],
                 'component_root': str(candidate), 'retained_root': str(retained_root), 'previous_active': active}
        atomic_json(journal, state)
        owner = {'owner': 'study-installer', 'operation': 'uninstall-retention', 'plan_sha256': canonical_digest(plan)}
        owner_path = retained_root/'.retention-owner.json'
        if retained_root.exists():
            if not owner_path.is_file() or json.loads(owner_path.read_text(encoding='utf-8')) != owner:
                raise ValueError('Partial retention directory is not owned by this plan')
        else:
            retained_root.mkdir(parents=True)
            atomic_json(owner_path, owner)
        allowed = {'.retention-owner.json', 'retention-manifest.json'}
        for entry in plan['retained_files']: allowed.update((entry['path'], entry['path']+'.retaining'))
        if any(path.relative_to(retained_root).as_posix() not in allowed for path in ops.safe_files(retained_root)):
            raise ValueError('Unlisted data in retention directory')
        for entry in plan['retained_files']:
            source = candidate/entry['path']; target = retained_root/entry['path']
            if not ops.inside(target, retained_root): raise ValueError('Escaping retained-data path')
            if target.exists():
                if target.stat().st_size != entry['size'] or _digest(target) != entry['sha256']:
                    raise ValueError('Already retained file changed; original installation preserved')
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            partial = target.with_name(target.name+'.retaining')
            shutil.copy2(source, partial)
            if partial.stat().st_size != entry['size'] or _digest(partial) != entry['sha256']:
                raise ValueError('Retention verification failed; original component was not removed')
            os.replace(partial, target)
        if _retention(candidate, plan['component']) != plan['retained_files']:
            raise ValueError('Legacy data changed during preservation; original component retained')
        atomic_json(retained_root/'retention-manifest.json', {'plan_sha256': canonical_digest(plan), 'files': plan['retained_files']})
        state['state'] = 'retention_verified'; atomic_json(journal, state)
        updated = json.loads(json.dumps(active))
        updated['components'].pop(plan['component'])
        if plan['component'] == 'comfy': updated['comfy_mode'] = 'disabled'
        updated['last_uninstall'] = {'transaction_id': plan['transaction_id'], 'component': plan['component'], 'retained_root': str(retained_root)}
        atomic_json(pointer, updated)
        state['state'] = 'deactivated'; atomic_json(journal, state)
        # Resolve and inspect again while the shared lifecycle lock is still held.
        if _safe(candidate) != candidate: raise ValueError('Component root changed before removal')
        return _finish_removal(plan, state, pointer, journal, candidate, retained_root)
