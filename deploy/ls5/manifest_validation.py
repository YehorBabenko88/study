"""Pure fail-closed release validation. No downloads, hardware queries or installs."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import PurePosixPath
import re
from urllib.parse import unquote, urlsplit


class ManifestError(ValueError):
    pass


def _require(condition, message):
    if not condition:
        raise ManifestError(message)


def audit_sha256(audit):
    try:
        data = json.dumps(audit, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise ManifestError('Audit must be strict JSON') from exc
    return hashlib.sha256(data.encode()).hexdigest()


def _name(value):
    _require(isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', value), 'Invalid distribution name')
    return re.sub(r'[-_.]+', '-', value).lower()


def _path(value):
    _require(isinstance(value, str) and value and '\\' not in value and ':' not in value,
             'Expected safe relative POSIX path')
    parsed = PurePosixPath(value)
    _require(not parsed.is_absolute() and all(p not in ('', '.', '..') for p in value.split('/')),
             'Unsafe relative artifact/entrypoint path')
    return value


def _host(value):
    return isinstance(value, str) and bool(re.fullmatch(r'(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]*', value))


def _wheel_tag(value):
    # CPython's stable ABI permits older cp3x-abi3 wheels on standard cp313;
    # free-threaded cp313t, future ABI3 floors and other architectures do not fit.
    return value in ('py3', 'py2.py3', 'cp313') or (
        isinstance(value, str) and bool(re.fullmatch(r'cp3(?:[2-9]|1[0-3])-abi3', value)))


def _pin(artifact, hosts):
    _require(type(artifact) is dict and isinstance(artifact.get('id'), str)
             and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,159}', artifact['id']), 'Safe artifact ID required')
    digest = artifact.get('sha256')
    _require(isinstance(digest, str) and re.fullmatch('[0-9a-f]{64}', digest) and digest != '0'*64,
             'Every selected artifact requires a real SHA-256 pin')
    _require(type(artifact.get('size')) is int and artifact['size'] > 0, 'Exact positive artifact byte size required')
    _require(('url' in artifact) != ('local_path' in artifact), 'Specify exactly one HTTPS URL or bundled local_path')
    redirects = artifact.get('redirect_hosts', [])
    _require(type(redirects) is list and len(redirects) <= 5 and len(set(redirects)) == len(redirects)
             and all(_host(host) and host in hosts for host in redirects),
             'Redirect hosts must be exact reviewed DNS names within allowed_hosts')
    if 'url' in artifact:
        _require(isinstance(artifact['url'], str), 'Invalid artifact URL')
        url = urlsplit(artifact['url'])
        _require(url.scheme == 'https' and url.hostname in hosts and not url.username and not url.password
                 and url.port in (None, 443) and not url.fragment, 'Artifact URL must use an approved HTTPS host')
        _require(not any(p.lower() in ('latest', 'main', 'master') for p in unquote(url.path).split('/')),
                 'Mutable latest/main/master artifact paths are forbidden')
    else:
        _path(artifact['local_path'])
    _require(artifact.get('kind') in ('python', 'wheel', 'zip', 'model'), 'Unsupported release artifact format')
    if artifact.get('archive_root') is not None:
        _path(artifact['archive_root'])
    return artifact


def _audit(hardware, plan):
    _require(type(hardware) is dict and hardware.get('status') == 'COLLECTED_READ_ONLY'
             and str(hardware.get('hostname', '')).upper() == 'LS5', 'Fresh authenticated LS5 inventory required; offer Disabled/External')
    try:
        timestamp = datetime.fromisoformat(hardware['collected_at_utc'].replace('Z', '+00:00'))
        _require(timestamp.tzinfo is not None, 'Audit timestamp needs timezone')
        age = (datetime.now(timezone.utc)-timestamp).total_seconds()
    except (KeyError, TypeError, ValueError) as exc:
        raise ManifestError('Valid audit timestamp required') from exc
    _require(-60 <= age <= 1800, 'Audit must be no older than 30 minutes')
    _require(any('64' in str(row.get('OSArchitecture', '')) and 'ARM' not in str(row.get('OSArchitecture', '')).upper()
                 for row in hardware.get('os', [])),
             'Windows x86-64 inventory required')
    review = plan.get('hardware_review')
    _require(type(review) is dict and review.get('audit_sha256') == audit_sha256(hardware)
             and review.get('component_compatibility') == 'approved', 'Hardware fit review must bind the exact audit')
    _require(plan.get('device') in ('cuda', 'cpu'), 'Select a reviewed device explicitly; no automatic GPU choice')
    if plan['device'] == 'cpu':
        _require(plan.get('cpu_opt_in') is True, 'CPU generation requires explicit opt-in; Disabled remains available')
    else:
        _require(review.get('gpu_verified') is True and type(review.get('vram_bytes')) is int and review['vram_bytes'] > 0,
                 'Verified dedicated VRAM required, never WMI AdapterRAM')
        readings = hardware.get('gpu', {}).get('nvidia_smi', [])
        totals = []
        for row in readings:
            if row.get('source') == 'nvidia-smi' and str(row.get('dedicated_vram_total_mib', '')).isdigit() and row.get('driver_version'):
                totals.append(int(row['dedicated_vram_total_mib'])*1024**2)
        _require(totals and review['vram_bytes'] in totals, 'NVIDIA driver-reported VRAM and explicit compatibility review required; unknown/AMD/WMI cannot auto-select CUDA')
    return review


def _validate_manifest(manifest, plan=None, hardware=None):
    """Validate selected install payloads; metadata candidates cannot become releases.

    A release author must audit dependency constraints/markers for this target,
    record the resulting closed distribution graph, and pin every wheel. This
    validator checks closure and artifact agreement; it is not a PyPI resolver.
    """
    _require(type(manifest) is dict and type(manifest.get('schema_version')) is int
             and manifest['schema_version'] == 1, 'Expected release manifest schema 1')
    plan = {'mode': 'managed', 'components': ['study', 'comfy']} if plan is None else plan
    _require(type(plan) is dict and plan.get('mode') in ('managed', 'external', 'disabled'), 'Invalid generation mode')
    selected = plan.get('components', ['study', 'comfy'] if plan['mode'] == 'managed' else ['study'])
    _require(type(selected) is list and selected and all(x in ('study', 'comfy') for x in selected)
             and len(set(selected)) == len(selected), 'Invalid selected components')
    _require(plan['mode'] == 'managed' or 'comfy' not in selected, 'External/Disabled never install or manage ComfyUI')
    managed_comfy = plan['mode'] == 'managed' and 'comfy' in selected
    if managed_comfy:
        _require(manifest.get('release_ready') is True, 'Managed release gate incomplete; candidate catalogue is not installable')
        review = _audit(hardware, plan)
    else:
        review = None
    hosts = manifest.get('allowed_hosts')
    _require(type(hosts) is list and hosts and all(_host(h) for h in hosts), 'Explicit exact HTTPS host names required')
    rows = manifest.get('artifacts')
    _require(type(rows) is list and all(type(a) is dict and isinstance(a.get('id'), str) for a in rows), 'Artifacts list required')
    by_id = {a['id']: a for a in rows}
    _require(len(by_id) == len(rows), 'Duplicate artifact ID')
    components = manifest.get('components')
    _require(type(components) is dict, 'Components map required')
    needed = set()
    for name in selected:
        component = components.get(name)
        _require(type(component) is dict and component.get('runtime_kind') == 'embedded', 'Component needs its own app-owned embedded runtime')
        _require(component.get('dependency_lock_complete') is True and component.get('dependency_lock_audited') is True,
                 'An audited closed wheel lock is required before installation')
        ids = component.get('artifact_ids')
        wheels = component.get('wheel_ids')
        lock = component.get('requirements_lock')
        _require(type(ids) is list and ids and type(wheels) is list and type(lock) is list and lock,
                 'Pinned source and dependency lock required')
        _require(len(set(ids)) == len(ids) and len(set(wheels)) == len(wheels), 'Duplicate component artifact ID')
        python_id, pip_id = component.get('python_artifact_id'), component.get('pip_artifact_id')
        _require(isinstance(python_id, str) and isinstance(pip_id, str), 'Pinned Python and pip required')
        component_ids = set(ids + wheels + [python_id, pip_id])
        _require(all(i in by_id for i in component_ids), 'Selected artifact ID missing from release')
        for identifier in component_ids: _pin(by_id[identifier], hosts)
        _require(sum(by_id[i]['kind'] == 'zip' for i in ids) == 1, 'Exactly one pinned source ZIP required per component')
        needed.update(component_ids)
        runtime = by_id[python_id]
        _require(runtime.get('kind') == 'python' and runtime.get('runtime_kind') == 'embedded'
                 and runtime.get('python_tag') == 'cp313' and runtime.get('platform') == 'win_amd64', 'Incompatible embedded Python runtime')
        _path(runtime.get('python_executable'))
        pip = by_id[pip_id]
        _require(pip.get('kind') == 'wheel' and _name(pip.get('distribution')) == 'pip'
                 and isinstance(pip.get('version'), str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.!+_-]*', pip['version']), 'Pinned pip wheel required')
        _path(component.get('entrypoint'))
        locked_names = set()
        locked_artifacts = set()
        for item in lock:
            _require(type(item) is dict, 'Invalid wheel lock entry')
            distribution = _name(item.get('distribution'))
            _require(distribution not in locked_names and item.get('artifact_id') in wheels, 'Duplicate/unlisted locked wheel')
            locked_names.add(distribution); locked_artifacts.add(item['artifact_id'])
            artifact = by_id[item['artifact_id']]
            _require(artifact.get('kind') == 'wheel' and _name(artifact.get('distribution')) == distribution
                     and isinstance(item.get('version'), str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.!+_-]*', item['version'])
                     and artifact.get('version') == item['version'], 'Wheel/version does not match lock')
            _require(artifact.get('platform') in ('any', 'win_amd64') and _wheel_tag(artifact.get('python_tag')), 'Wheel incompatible with Python 3.13 Windows x86-64')
            _require(type(item.get('requires')) is list, 'Each locked wheel needs audited resolved dependencies')
        _require(locked_artifacts == set(wheels), 'Every dependency wheel must appear exactly once in lock')
        for item in lock:
            _require(all(_name(dep) in locked_names for dep in item['requires']), 'Dependency wheel set is not closed')
    total = sum(by_id[i]['size'] for i in needed)
    _require(type(plan.get('approved_download_bytes')) is int and plan['approved_download_bytes'] >= total,
             'Explicit download-size approval must cover all selected unique artifacts')
    models = [by_id[i] for i in needed if by_id[i]['kind'] == 'model']
    torch_variants = {by_id[i].get('variant') for i in needed if by_id[i]['kind'] == 'wheel'
                      and _name(by_id[i].get('distribution')) == 'torch'}
    if torch_variants and managed_comfy:
        _require(torch_variants <= ({'cpu'} if plan['device'] == 'cpu' else {'cu128', 'cu130'}),
                 'Torch wheel variant does not match explicitly selected CPU/CUDA device')
    if managed_comfy: _require(models, 'Managed generation requires a reviewed checkpoint')
    else: _require(not models, 'Study-only and External/Disabled selections cannot install checkpoints')
    licenses = {row['id']: row for row in manifest.get('licenses', []) if type(row) is dict and 'id' in row}
    accepted = plan.get('accepted_licenses', [])
    _require(type(accepted) is list and all(isinstance(value, str) for value in accepted), 'Accepted licenses must be an explicit list')
    for model in models:
        fit = review.get('model_fit') if review is not None else None
        explicit_cpu_fit = (managed_comfy and plan.get('device') == 'cpu'
                            and components['comfy'].get('profile') == 'cpu-metadata-verified'
                            and model.get('metadata_candidate_requires_model_fit_review') is True
                            and type(fit) is dict and fit.get('model_id') == model['id']
                            and fit.get('requirements_reviewed') is True)
        _require(model.get('workflow_family') in ('sd1', 'sdxl')
                 and (model.get('hardware_requirements_reviewed') is True or explicit_cpu_fit),
                 'Model/workflow hardware requirements have not been reviewed')
        license_id = model.get('license_id')
        _require(license_id in accepted and license_id in licenses
                 and re.fullmatch('[0-9a-f]{64}', str(licenses[license_id].get('sha256', '')))
                 and licenses[license_id].get('sha256') != '0'*64, 'Explicit reviewed model-license acceptance required')
        if review is not None:
            minimum_ram = fit.get('min_ram_bytes') if explicit_cpu_fit else model.get('min_ram_bytes')
            _require(type(minimum_ram) is int and minimum_ram > 0
                     and any(type(row.get('TotalPhysicalMemory')) is int and row['TotalPhysicalMemory'] >= minimum_ram for row in hardware.get('ram', [])), 'Model RAM requirements unresolved or unsupported')
            if plan['device'] == 'cuda':
                minimum_vram = model.get('min_vram_bytes')
                _require(type(minimum_vram) is int and 0 < minimum_vram <= review['vram_bytes'], 'Model VRAM requirements unresolved or unsupported')
    if review is not None:
        _require(any(type(row.get('FreeSpace')) is int and row['FreeSpace'] >= total*3 for row in hardware.get('disks', [])), 'Insufficient audited free disk for downloads, extraction and rollback headroom')
    try:
        return json.loads(json.dumps(manifest, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise ManifestError('Manifest must contain strict JSON') from exc


def materialize_manifest(catalog, *, mode, study_source_artifact):
    """Bind the built Study ZIP to the audited Study lock, never unlock Comfy.

    source is supplied by the release bundler with exact bytes/hash and either an
    immutable HTTPS URL or safe bundled local_path. This function does not build,
    download or inspect payloads; the engine verifies actual bytes before use.
    """
    _require(mode in ('external', 'disabled'), 'Managed materialization blocked until complete Comfy lock and LS5 fit review')
    result = json.loads(json.dumps(catalog))
    _require(type(study_source_artifact) is dict and study_source_artifact.get('kind') == 'zip', 'Built Study source ZIP pin required')
    _pin(study_source_artifact, result['allowed_hosts'])
    source_id = study_source_artifact['id']
    _require(source_id not in {a['id'] for a in result['artifacts']}, 'Study source artifact ID conflicts with catalogue')
    result['artifacts'].append(study_source_artifact)
    component = result['components']['study']
    _require(component.get('dependency_lock_complete') is True and component.get('dependency_lock_audited') is True, 'Study lock has not been audited')
    component['artifact_ids'] = [source_id]
    component['release_gates'] = []
    result['catalog_type'] = 'release_manifest'
    result['materialized_mode'] = mode
    # Global Managed readiness remains false. Study-only modes validate selected
    # component locks independently and never download unrelated Comfy candidates.
    return result


def validate_manifest(manifest, plan=None, hardware=None):
    """Public normalization boundary: malformed input always fails ManifestError."""
    try:
        return _validate_manifest(manifest, plan, hardware)
    except ManifestError:
        raise
    except (TypeError, ValueError, KeyError, AttributeError, OverflowError) as exc:
        raise ManifestError('Malformed or incompatible release manifest/plan/audit') from exc


def materialize_managed_cpu_candidate(catalog, graph_candidate, study_source_artifact,
                                       model_id, *, profile):
    """Explicit opt-in metadata release, never proof of LS5 runtime acceptance.

    The engine still requires audit/plan/license/budget approvals, isolated pip
    checks, component verification and actual Comfy HTTP generation before enable.
    No model/profile default and no invented RAM/VRAM requirements are supplied.
    """
    _require(profile == 'cpu-metadata-verified', 'Explicit CPU metadata profile required; no automatic device choice')
    candidate = json.loads(json.dumps(graph_candidate))
    _require(type(candidate.get('schema_version')) is int and candidate['schema_version'] == 1 and candidate.get('profile') == profile
             and candidate.get('dependency_lock_complete') is True and candidate.get('dependency_lock_audited') is True
             and candidate.get('constraints_verified') is True and candidate.get('wheel_tags_and_requires_python_verified') is True
             and candidate.get('official_metadata_hash_size_verified') is True
             and candidate.get('package_payload_requests_performed') == 0,
             'A complete verified metadata-only candidate graph is required')
    result = materialize_manifest(catalog, mode='disabled', study_source_artifact=study_source_artifact)
    models = [row for row in result['artifacts'] if row['id'] == model_id and row.get('kind') == 'model']
    _require(len(models) == 1, 'Explicit pinned model candidate required')
    model = models[0]
    terms = [row for row in result.get('licenses', []) if row.get('id') == model.get('license_id')]
    _require(len(terms) == 1 and re.fullmatch(r'[0-9a-f]{64}', str(terms[0].get('sha256', '')))
             and terms[0].get('sha256') != '0'*64
             and type(terms[0].get('size')) is int and terms[0]['size'] > 0,
             'Model exact license document is not pinned; this candidate cannot be selected')
    rows = candidate.get('artifacts')
    lock = candidate.get('requirements_lock')
    _require(type(rows) is list and rows and type(lock) is list and len(rows) == len(lock), 'Incomplete candidate wheel graph')
    source = next((row for row in result['artifacts'] if row['id'] == 'comfy-v0.43.0-source'), None)
    _require(source is not None and source.get('source_revision') == candidate.get('source_commit'), 'Candidate source commit mismatch')
    _require(candidate.get('python_version') == result['bootstrap_python']['version']
             and candidate.get('platform') == 'win_amd64', 'Candidate Python/platform mismatch')
    existing = {row['id'] for row in result['artifacts']}
    names = {_name(row.get('distribution')) for row in rows}
    ids = {row.get('id') for row in rows}
    _require(len(ids) == len(rows) and not ids.intersection(existing)
             and set(candidate.get('wheel_ids', [])) == ids, 'Duplicate, conflicting or missing candidate wheel IDs')
    by_id = {row['id']: row for row in rows}
    for row in rows:
        _pin(row, result['allowed_hosts'])
        _require(row.get('kind') == 'wheel' and row.get('platform') in ('any', 'win_amd64')
                 and _wheel_tag(row.get('python_tag')), 'Incompatible CPU candidate wheel')
    locked_names = set()
    for item in lock:
        row = by_id.get(item.get('artifact_id'))
        name = _name(item.get('distribution'))
        _require(row is not None and name not in locked_names and _name(row.get('distribution')) == name
                 and item.get('version') == row.get('version') and type(item.get('requires')) is list
                 and all(_name(dep) in names for dep in item['requires']), 'Candidate wheel lock is not complete/closed')
        locked_names.add(name)
    _require(locked_names == names, 'Candidate lock does not cover every wheel')
    variants = {row.get('variant') for row in rows if _name(row.get('distribution')) in ('torch', 'torchvision', 'torchaudio')}
    _require(variants == {'cpu'}, 'Only the explicitly verified CPU wheel profile is eligible')
    model['metadata_candidate_requires_model_fit_review'] = True
    result['artifacts'].extend(rows)
    component = result['components']['comfy']
    component.update(profile=profile, wheel_ids=candidate['wheel_ids'], requirements_lock=lock,
                     artifact_ids=[source['id'], model_id], model_artifact_id=model_id,
                     dependency_lock_complete=True, dependency_lock_audited=True,
                     dependency_lock_audit_scope='verified metadata-only CPython3.13 Windows graph; no runtime execution',
                     runtime_acceptance='not_tested', release_gates=['fresh_LS5_hardware_and_model_fit_review',
                         'explicit_CPU_opt_in_license_and_download_approval', 'real_isolated_runtime_smoke_before_enable'])
    result.update(materialized_mode='managed', selected_profile=profile, release_ready=True,
                  release_ready_scope='metadata_artifact_and_closed_lock_eligibility_only',
                  runtime_acceptance='not_tested', requires_real_generation_smoke=True,
                  candidate_graph_sha256=audit_sha256(candidate))
    return result
