"""Deterministic mnemonic scene compiler; no inference, network or board writes.

See docs/SEMANTIC_COMPOSER_CONTRACT.md for the adapter and persistence contract.
All public JSON values are detached. Snapshot strings are immutable JSON, not
live references to board nodes or assets. This module never reads asset paths.
"""
from collections import deque
import hashlib
import json
import unicodedata
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import UUID, uuid4


NODE_TYPES = frozenset(('letter', 'syllable', 'word', 'sentence', 'image', 'note', 'action'))
RELATIONS = {
    'association': 'is associated with', 'part_of': 'is part of',
    'sequence': 'comes before', 'meaning': 'means',
    'sound': 'sounds like', 'action': 'acts on',
}
DEFAULT_PARAMETERS = {'seed': 0, 'width': 512, 'height': 512, 'steps': 20}


def _json(value, *, max_bytes=2_000_000):
    """Strict, bounded JSON; reject lossy Python-to-JSON coercions."""
    def check(item, depth=0):
        if depth > 32:
            raise ValueError('JSON nesting exceeds 32')
        if type(item) is dict:
            if any(type(key) is not str for key in item):
                raise ValueError('JSON keys must be strings')
            for child in item.values():
                check(child, depth + 1)
        elif type(item) is list:
            for child in item:
                check(child, depth + 1)
        elif item is not None and type(item) not in (str, int, float, bool):
            raise ValueError('Expected JSON data')
    try:
        check(value)
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(',', ':'), allow_nan=False)
        if len(encoded.encode('utf-8')) > max_bytes:
            raise ValueError('JSON exceeds byte limit')
        return encoded
    except (TypeError, OverflowError, RecursionError, UnicodeError) as exc:
        raise ValueError('Invalid JSON data') from exc


def _hash(value):
    return hashlib.sha256(_json(value).encode('utf-8')).hexdigest()


def _integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('Invalid ' + label)
    return value


def _string(value, limit, label, *, empty=False):
    if not isinstance(value, str) or len(value) > limit or (not empty and not value.strip()):
        raise ValueError('Invalid ' + label)
    return value


def _asset(value):
    _string(value, 36, 'asset ID')
    try:
        if str(UUID(value)) != value:
            raise ValueError('Asset ID must be canonical UUID')
    except (ValueError, AttributeError) as exc:
        raise ValueError('Invalid asset ID') from exc
    return value


def _clean(value):
    # Prompt sanitation is not a guarantee against natural-language injection.
    return ' '.join(''.join(' ' if unicodedata.category(c).startswith('C') else c
                            for c in value).split())


def _parameters(parameters):
    if parameters is None:
        parameters = {}
    if type(parameters) is not dict or set(parameters) - set(DEFAULT_PARAMETERS):
        raise ValueError('Unknown generation parameters')
    result = {**DEFAULT_PARAMETERS, **parameters}
    _integer(result['seed'], 0, 2**53 - 1, 'seed')
    _integer(result['steps'], 5, 35, 'steps')
    for key in ('width', 'height'):
        if type(result[key]) is not int or result[key] not in (512, 768):
            raise ValueError('Unsupported ' + key)
    return result


class UnsupportedMode(ValueError):
    """No installed adapter can truthfully execute the requested mode."""


def generation_request(revision):
    """Build v1 adapter input. Asset manifests are never sent as fake references.

    This function deliberately cannot produce image-conditioned requests. Agent A
    must implement actual byte upload/workflow wiring before extending it.
    """
    if type(revision) is not dict or revision.get('schema_version') != 1:
        raise ValueError('Expected composer schema version 1')
    mode = revision.get('mode')
    if mode == 'image_conditioned':
        raise UnsupportedMode('image_conditioned unavailable: no pixel-upload workflow adapter')
    if mode != 'text_to_image':
        raise ValueError('Invalid mode')
    prompt = _clean(_string(revision.get('effective_prompt'), 1200, 'effective prompt'))
    _string(prompt, 1200, 'effective prompt')
    return {'contract_version': 1, 'mode': mode, 'prompt': prompt,
            'parameters': _parameters(revision.get('parameters')), 'references': []}


_UNSET = object()


class CompositionStore:
    """Separate SQLite file; append-only revisions, submitted jobs and results.

    Returned dictionaries are copies. SQL triggers prohibit UPDATE/DELETE as an
    additional guard (not a security boundary against the database file owner).
    Each operation closes its connection; concurrent writers serialize revision
    allocation with BEGIN IMMEDIATE. No existing Study database is touched unless
    the caller explicitly selects it.
    """

    def __init__(self, path):
        self.path = str(path)
        if self.path == ':memory:':
            raise ValueError('A durable SQLite file path is required')
        with self._connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS semantic_revisions (
                    revision_id TEXT PRIMARY KEY,
                    composition_id TEXT NOT NULL,
                    version INTEGER NOT NULL CHECK(version > 0),
                    parent_revision_id TEXT REFERENCES semantic_revisions(revision_id),
                    payload TEXT NOT NULL,
                    UNIQUE(composition_id, version)
                );
                CREATE TABLE IF NOT EXISTS semantic_jobs (
                    job_id TEXT PRIMARY KEY,
                    revision_id TEXT NOT NULL REFERENCES semantic_revisions(revision_id),
                    prompt_id TEXT NOT NULL UNIQUE,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS semantic_results (
                    job_id TEXT PRIMARY KEY REFERENCES semantic_jobs(job_id),
                    payload TEXT NOT NULL
                );
            ''')
            for table in ('semantic_revisions', 'semantic_jobs', 'semantic_results'):
                for operation in ('UPDATE', 'DELETE'):
                    db.execute(f'''CREATE TRIGGER IF NOT EXISTS {table}_no_{operation.lower()}
                        BEFORE {operation} ON {table}
                        BEGIN SELECT RAISE(ABORT, 'semantic history is append-only'); END''')

    @contextmanager
    def _connection(self):
        db = sqlite3.connect(self.path, timeout=15)
        try:
            db.execute('PRAGMA foreign_keys=ON')
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _load(db, revision_id):
        _string(revision_id, 80, 'revision ID')
        row = db.execute('SELECT payload FROM semantic_revisions WHERE revision_id=?', (revision_id,)).fetchone()
        if row is None:
            raise KeyError(revision_id)
        return json.loads(row[0])

    @staticmethod
    def _append(db, scene, composition_id, version, parent):
        record = {**scene, 'revision_id': str(uuid4()), 'composition_id': composition_id,
                  'version': version, 'parent_revision_id': parent,
                  'created_at': datetime.now(timezone.utc).isoformat()}
        # Snapshot text is JSON-escaped again inside the history envelope; selected
        # edge metadata is also retained. Keep the source cap independent of this.
        payload = _json(record, max_bytes=8_000_000)
        db.execute('INSERT INTO semantic_revisions VALUES (?,?,?,?,?)',
                   (record['revision_id'], composition_id, version, parent, payload))
        return json.loads(payload)

    def create(self, graph, roots, **options):
        """Persist first revision; validate before opening the write transaction."""
        scene = compose(graph, roots, **options)
        with self._connection() as db:
            return self._append(db, scene, str(uuid4()), 1, None)

    def get(self, revision_id):
        with self._connection() as db:
            return self._load(db, revision_id)

    def history(self, composition_id):
        _string(composition_id, 80, 'composition ID')
        with self._connection() as db:
            rows = db.execute('SELECT payload FROM semantic_revisions WHERE composition_id=? ORDER BY version',
                              (composition_id,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def revise(self, revision_id, *, parameters=None, user_prompt=_UNSET, mode=None):
        """Branch from any revision; omitted user_prompt inherits, None clears it.

        Source graph and selection remain fixed. A changed graph needs create().
        Parameters are merged with the parent; results never get overwritten.
        """
        with self._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            parent = self._load(db, revision_id)
            if parameters is not None and type(parameters) is not dict:
                raise ValueError('Expected parameter object')
            scene = compose(json.loads(parent['source_graph_json']), parent['roots'],
                            **parent['selection'],
                            parameters={**parent['parameters'], **(parameters or {})},
                            user_prompt=parent['user_prompt'] if user_prompt is _UNSET else user_prompt,
                            mode=parent['mode'] if mode is None else mode)
            version = db.execute('SELECT MAX(version)+1 FROM semantic_revisions WHERE composition_id=?',
                                 (parent['composition_id'],)).fetchone()[0]
            return self._append(db, scene, parent['composition_id'], version, revision_id)

    def record_job(self, revision_id, prompt_id, *, job_id=None, prompt_id_kind="upstream", upstream_prompt_id=None):
        """Record an accepted local queue or upstream job, not a submission attempt.

        prompt_id_kind distinguishes local adapter IDs from upstream ComfyUI IDs.
        Local acceptance is not evidence of upstream execution. No network here.
        Duplicate IDs are rejected to prevent ambiguous provenance.
        """
        _string(prompt_id, 200, 'generation prompt ID')
        if job_id is not None: _string(job_id, 80, 'job ID')
        if prompt_id_kind not in ('local', 'upstream'): raise ValueError('Invalid prompt ID kind')
        if upstream_prompt_id is not None: _string(upstream_prompt_id, 200, 'upstream prompt ID')
        with self._connection() as db:
            revision = self._load(db, revision_id)
            request = generation_request(revision)
            job = {'job_id': job_id or str(uuid4()), 'revision_id': revision_id,
                   'prompt_id': prompt_id, 'prompt_id_kind': prompt_id_kind,
                   'upstream_prompt_id': upstream_prompt_id, 'request': request,
                   'created_at': datetime.now(timezone.utc).isoformat(),
                   'reference_images_transmitted': False}
            try:
                db.execute('INSERT INTO semantic_jobs VALUES (?,?,?,?)',
                           (job['job_id'], revision_id, prompt_id, _json(job)))
            except sqlite3.IntegrityError as exc:
                raise ValueError('Generation job or prompt ID already recorded') from exc
        return job

    def record_result(self, job_id, *, status, outputs=None, error=None, upstream_prompt_id=None):
        """Append one terminal result. Each image is attributed to this job/revision.

        Agent A saves image bytes non-destructively, computes SHA-256, then supplies
        asset_id/hash pairs. Metadata is a caller assertion, not a pixel verifier.
        """
        _string(job_id, 80, 'job ID')
        if upstream_prompt_id is not None: _string(upstream_prompt_id, 200, 'upstream prompt ID')
        if outputs is None:
            outputs = []
        if type(outputs) is not list or len(outputs) > 8:
            raise ValueError('Expected at most 8 outputs')
        for output in outputs:
            if type(output) is not dict or set(output) != {'asset_id', 'sha256'}:
                raise ValueError('Expected output asset ID and SHA-256')
            _asset(output['asset_id'])
            digest = _string(output['sha256'], 64, 'output SHA-256')
            if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
                raise ValueError('Invalid output SHA-256')
        if status == 'complete':
            if not outputs or error is not None:
                raise ValueError('Complete requires images and no error')
        elif status in ('failed', 'cancelled', 'timed_out', 'interrupted'):
            _string(error, 2000, 'job error')
            if outputs:
                raise ValueError('Failed result cannot contain images')
        else:
            raise ValueError('Expected terminal generation status')
        with self._connection() as db:
            row = db.execute('SELECT revision_id FROM semantic_jobs WHERE job_id=?', (job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            event = {'job_id': job_id, 'revision_id': row[0], 'status': status,
                     'outputs': outputs, 'error': error, 'upstream_prompt_id': upstream_prompt_id,
                     'created_at': datetime.now(timezone.utc).isoformat()}
            payload = _json(event)
            try:
                db.execute('INSERT INTO semantic_results VALUES (?,?)', (job_id, payload))
            except sqlite3.IntegrityError as exc:
                raise ValueError('Job already has a terminal result; create a new job to retry') from exc
        return json.loads(payload)

    def job_history(self, revision_id):
        with self._connection() as db:
            self._load(db, revision_id)
            rows = db.execute('''SELECT j.payload,r.payload FROM semantic_jobs j
                LEFT JOIN semantic_results r ON r.job_id=j.job_id
                WHERE j.revision_id=? ORDER BY j.rowid''', (revision_id,)).fetchall()
        return [{**json.loads(job), 'result': json.loads(result) if result else None}
                for job, result in rows]


def compose(graph, roots, *, direction='outgoing', max_depth=4, max_nodes=24,
            max_edges=64, parameters=None, user_prompt=None, mode='text_to_image'):
    """Compile a board into one scene; reject capacity overflow, report depth cuts.

    Limits: input 1000 nodes/3000 edges/2 MB; selection <=64 nodes/256 edges;
    depth <=32; <=8 unique assets; suggested/effective prompt <=1200 characters.
    Unknown metadata is preserved in the exact source snapshot, not interpreted.
    """
    snapshot = _json(graph)
    graph = json.loads(snapshot)
    if type(graph) is not dict:
        raise ValueError('Graph must be an object')
    nodes, edges = graph.get('nodes'), graph.get('edges', [])
    if type(nodes) is not list or not 1 <= len(nodes) <= 1000:
        raise ValueError('Expected 1..1000 nodes')
    if type(edges) is not list or len(edges) > 3000:
        raise ValueError('Expected at most 3000 edges')
    by_id = {}
    for node in nodes:
        if type(node) is not dict:
            raise ValueError('Node must be an object')
        nid = _string(node.get('id'), 80, 'node ID')
        if nid in by_id or type(node.get('type')) is not str or node['type'] not in NODE_TYPES:
            raise ValueError('Duplicate node ID or unsupported node type')
        _string(node.get('text', ''), 5000, 'node text', empty=True)
        assets = node.get('image_assets', [])
        if type(assets) is not list or len(assets) > 12:
            raise ValueError('Invalid image gallery')
        for asset in assets:
            _asset(asset)
        if len(set(assets)) != len(assets):
            raise ValueError('Duplicate gallery asset')
        if 'asset_id' in node:
            _asset(node['asset_id'])
        by_id[nid] = node
    for edge in edges:
        if (type(edge) is not dict or type(edge.get('from')) is not str
                or type(edge.get('to')) is not str
                or edge['from'] not in by_id or edge['to'] not in by_id
                or type(edge.get('relation', 'association')) is not str
                or edge.get('relation', 'association') not in RELATIONS):
            raise ValueError('Invalid edge')
    if (type(roots) is not list or not roots
            or any(type(root) is not str or root not in by_id for root in roots)
            or len(set(roots)) != len(roots)):
        raise ValueError('Expected distinct existing root IDs')
    if direction not in ('outgoing', 'incoming', 'both'):
        raise ValueError('Invalid traversal direction')
    _integer(max_depth, 0, 32, 'max_depth')
    _integer(max_nodes, 1, 64, 'max_nodes')
    _integer(max_edges, 0, 256, 'max_edges')
    params = _parameters(parameters)
    if mode not in ('text_to_image', 'image_conditioned'):
        raise ValueError('Invalid generation mode')
    adjacency = {nid: set() for nid in by_id}
    for edge in edges:
        a, b = edge['from'], edge['to']
        if direction in ('outgoing', 'both'):
            adjacency[a].add(b)
        if direction in ('incoming', 'both'):
            adjacency[b].add(a)
    distances = {root: 0 for root in sorted(roots)}
    queue = deque(sorted(roots))
    while queue:
        nid = queue.popleft()
        if len(distances) > max_nodes:
            raise ValueError('Selection exceeds node limit')
        if distances[nid] == max_depth:
            continue
        for neighbor in sorted(adjacency[nid]):
            if neighbor not in distances:
                distances[neighbor] = distances[nid] + 1
                queue.append(neighbor)
    selected = sorted(distances)
    selected_edges = sorted((edge for edge in edges
                             if edge['from'] in distances and edge['to'] in distances), key=_json)
    if len(selected_edges) > max_edges:
        raise ValueError('Selection exceeds edge limit')
    references = []
    for nid in selected:
        node = by_id[nid]
        assets = set(node.get('image_assets', []))
        if 'asset_id' in node:
            assets.add(node['asset_id'])
        references.extend({'node_id': nid, 'asset_id': asset} for asset in sorted(assets))
    if len({ref['asset_id'] for ref in references}) > 8:
        raise ValueError('Selection exceeds 8 reference images')
    if mode == 'image_conditioned' and not references:
        raise ValueError('Image-conditioned drafts require reference assets')
    quote = lambda text: json.dumps(text, ensure_ascii=False)
    elements = [f'{quote(nid)} ({by_id[nid]["type"]}): {quote(_clean(by_id[nid].get("text", "")))}'
                for nid in selected]
    relations = [f'{quote(e["from"])} {RELATIONS[e.get("relation", "association")]} {quote(e["to"])}'
                 for e in selected_edges]
    description = 'Elements: ' + '; '.join(elements) + '. Relations: ' + ('; '.join(relations) or 'none') + '.'
    suggested = 'Create one unified mnemonic scene with interacting elements in a shared setting. ' + description
    _string(suggested, 1200, 'suggested prompt')
    if user_prompt is not None:
        _string(user_prompt, 1200, 'user prompt')
        if not _clean(user_prompt):
            raise ValueError('Empty user prompt after normalization')
    result = {
        'schema_version': 1, 'source_graph_json': snapshot,
        'source_graph_sha256': hashlib.sha256(snapshot.encode('utf-8')).hexdigest(),
        'roots': sorted(roots), 'selection': {'direction': direction, 'max_depth': max_depth,
                                            'max_nodes': max_nodes, 'max_edges': max_edges},
        'selected_node_ids': selected, 'selected_edges': selected_edges,
        'depth_limited': any(neighbor not in distances for nid in selected for neighbor in adjacency[nid]),
        'source_description': description, 'suggested_prompt': suggested,
        'user_prompt': user_prompt, 'effective_prompt': _clean(user_prompt) if user_prompt is not None else suggested,
        'parameters': params, 'mode': mode, 'references': references,
        'reference_images_transmitted': False,
    }
    result['scene_fingerprint'] = _hash({key: result[key] for key in (
        'schema_version', 'roots', 'selection', 'selected_node_ids', 'selected_edges',
        'source_description', 'suggested_prompt', 'user_prompt', 'effective_prompt', 'parameters', 'mode', 'references')})
    return result
