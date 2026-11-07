"""Build a hash-bound installer ZIP from clean git HEAD; no install/download."""
import argparse
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import subprocess
import types
import zipfile


def _json(value): return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False)+'\n').encode()


def build_bundle(repository, destination):
    repository = Path(repository).resolve(); destination = Path(destination).resolve()
    def git(*args, binary=False):
        return subprocess.check_output(['git', *args], cwd=repository, text=not binary)
    if git('status', '--porcelain').strip(): raise ValueError('Bundle requires a clean committed HEAD')
    if destination.exists(): raise ValueError('Refusing to overwrite an existing installer bundle')
    sha = git('rev-parse', 'HEAD').strip()
    names = git('ls-files', '-z').split('\0')
    for name in filter(None, names):
        path = PurePosixPath(name)
        if (path.name in ('.env', 'config.local.json', 'id_rsa', 'id_ed25519')
                or path.suffix.lower() in ('.sqlite', '.sqlite3', '.safetensors', '.ckpt', '.wav')
                or (len(path.parts) > 2 and path.parts[0] == 'prototype'
                    and path.parts[1] in ('document_uploads', 'speech_audio', 'board_assets', 'generated_media')
                    and path.name not in ('.gitkeep', '.gitignore', 'README.md'))):
            raise ValueError('Tracked learner/private/runtime payload refused: '+name)
    sizes = git('ls-tree', '-rl', 'HEAD').splitlines()
    if sum(int(line.split(None, 4)[3]) for line in sizes if line.split(None, 4)[3].isdigit()) > 100_000_000:
        raise ValueError('Source archive exceeds the code-only bundle budget')
    payload = git('archive', '--format=zip', 'HEAD', binary=True)
    source_hash = hashlib.sha256(payload).hexdigest()
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        catalog = json.loads(archive.read('deploy/ls5/release_catalog.json'))
        validation = types.ModuleType('bundled_manifest_validation')
        exec(compile(archive.read('deploy/ls5/manifest_validation.py'), 'bundled_manifest_validation.py', 'exec'), validation.__dict__)
        source = {'id': 'study-source-'+sha, 'component': 'study', 'kind': 'zip',
                  'local_path': 'payload/study.zip', 'sha256': source_hash, 'size': len(payload),
                  'source_revision': sha, 'license_id': 'repository-license-review-required'}
        manifest = validation.materialize_manifest(catalog, mode='disabled', study_source_artifact=source)
        selected = manifest['components']['study']
        selected_ids = set(selected['artifact_ids'] + selected['wheel_ids'] + [selected['python_artifact_id'], selected['pip_artifact_id']])
        validation.validate_manifest(manifest, plan={'mode': 'disabled', 'components': ['study'],
            'approved_download_bytes': sum(a['size'] for a in manifest['artifacts'] if a['id'] in selected_ids),
            'accepted_licenses': sorted({a['license_id'] for a in manifest['artifacts'] if a['id'] in selected_ids})})
        metadata = {'format': 'study-ls5-installer-bundle-v1', 'source_sha': sha,
                    'study_zip_sha256': source_hash, 'study_zip_bytes': len(payload),
                    'release_manifest_sha256': hashlib.sha256(_json(manifest)).hexdigest(),
                    'managed_comfy_ready': False, 'target_host': 'LS5',
                    'physical_acceptance': 'NOT_PERFORMED', 'installation_performed': False}
        entries = {'payload/study.zip': payload, 'release_manifest.json': _json(manifest), 'release.json': _json(metadata)}
        candidate_path = 'deploy/ls5/comfy_cpu_lock_candidate.json'
        candidate_manifests = []
        if candidate_path in archive.namelist():
            candidate = json.loads(archive.read(candidate_path))
            licensed = {row['id'] for row in catalog.get('licenses', [])
                        if isinstance(row.get('sha256'), str) and len(row['sha256']) == 64 and row.get('size', 0) > 0}
            for model in catalog['artifacts']:
                if model.get('kind') != 'model' or model.get('license_id') not in licensed: continue
                name = 'managed-cpu-'+model['id']+'.candidate.json'
                candidate_manifest = validation.materialize_managed_cpu_candidate(
                    catalog, candidate, source, model['id'], profile='cpu-metadata-verified')
                entries[name] = _json(candidate_manifest); candidate_manifests.append(name)
        metadata['optional_managed_cpu_candidate_manifests'] = candidate_manifests
        metadata['candidate_selection'] = 'NONE; fresh LS5 hardware/model review and explicit approvals required'
        entries['release.json'] = _json(metadata)
        for name in archive.namelist():
            if name.startswith('deploy/ls5/') and not name.endswith('/') and '/__pycache__/' not in name:
                entries[name] = archive.read(name)
            elif name in ('docs/INSTALLER_DESIGN.md', 'docs/LS5_AUDIT_AND_MODEL_GATE.md', 'docs/INTEGRATION_WINDOWS_ACCEPTANCE.md'):
                entries[name] = archive.read(name)
    moment = datetime.fromtimestamp(int(git('show', '-s', '--format=%ct', 'HEAD').strip()), timezone.utc)
    stamp = (moment.year, moment.month, moment.day, moment.hour, moment.minute, moment.second)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open('xb') as stream, zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
            for name, data in sorted(entries.items()):
                info = zipfile.ZipInfo(name, date_time=stamp); info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16; bundle.writestr(info, data, compresslevel=9)
    except Exception:
        # A partial deliverable is retained for inspection, never reported ready.
        raise
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    return {**metadata, 'bundle_path': str(destination), 'bundle_sha256': digest, 'bundle_bytes': destination.stat().st_size}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(build_bundle(args.repository, args.output), indent=2))


if __name__ == '__main__': main()
