"""Durable local composition HTTP service; no arbitrary workflow or file access."""
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
from uuid import UUID, uuid4

import board_assets
import comfy_adapter
from semantic_composer import CompositionStore, generation_request


class RequestConflict(ValueError):
    pass


class CompositionService:
    def __init__(self, path, adapter=comfy_adapter):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.store = CompositionStore(path)
        self.adapter = adapter
        self.lock = threading.RLock()
        with self.store._connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS composition_requests (
                  request_id TEXT PRIMARY KEY, revision_id TEXT NOT NULL,
                  job_id TEXT NOT NULL UNIQUE, adapter_request_id TEXT NOT NULL UNIQUE);
                CREATE TABLE IF NOT EXISTS composition_cancelled (job_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS composition_assets (
                  source_sha256 TEXT PRIMARY KEY, asset_id TEXT NOT NULL, sha256 TEXT NOT NULL);
            ''')
            for table in ('composition_requests', 'composition_assets', 'composition_cancelled'):
                for operation in ('UPDATE', 'DELETE'):
                    db.execute(f"CREATE TRIGGER IF NOT EXISTS {table}_no_{operation.lower()} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT, 'composition service history is append-only'); END")

    def _reservation(self, job_id):
        with self.store._connection() as db:
            row = db.execute('SELECT request_id,revision_id,job_id,adapter_request_id FROM composition_requests WHERE job_id=?', (job_id,)).fetchone()
        if row is None: raise KeyError('Unknown composition job')
        return row

    def _job(self, job_id):
        with self.store._connection() as db:
            row = db.execute('SELECT payload FROM semantic_jobs WHERE job_id=?', (job_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def generate(self, revision_id, request_id):
        if not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,120}', request_id):
            raise ValueError('A stable request_id is required')
        # Validate exact saved revision before allocating any request or contacting adapter.
        generation_request(self.store.get(revision_id))
        with self.lock, self.store._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT revision_id,job_id FROM composition_requests WHERE request_id=?', (request_id,)).fetchone()
            if row:
                if row[0] != revision_id: raise RequestConflict('request_id belongs to another revision')
                job_id = row[1]
            else:
                job_id = str(uuid4())
                adapter_id = 'composition:' + hashlib.sha256((revision_id+'\0'+request_id).encode()).hexdigest()
                db.execute('INSERT INTO composition_requests VALUES (?,?,?,?)', (request_id, revision_id, job_id, adapter_id))
        return self.status(job_id)

    def _accepted(self, reservation):
        request_id, revision_id, job_id, adapter_request_id = reservation
        job = self._job(job_id)
        if job is not None: return job
        request = generation_request(self.store.get(revision_id))
        accepted = self.adapter.submit(request['prompt'], request_id=adapter_request_id, **request['parameters'])
        if accepted.get('status') == 'unavailable':
            # Reservation remains durable; enabling local adapter and repeating GET resumes it.
            return {'job_id': job_id, 'revision_id': revision_id, 'prompt_id': None,
                    'prompt_id_kind': 'local', 'upstream_prompt_id': None, 'status': 'unavailable',
                    'result': None, 'error': accepted.get('reason'), 'request_id': request_id}
        prompt_id = accepted['prompt_id']
        # Crash after adapter submit is safe: repeating its durable request key returns same job.
        try:
            return self.store.record_job(revision_id, prompt_id, job_id=job_id,
                prompt_id_kind='local', upstream_prompt_id=accepted.get('upstream_prompt_id'))
        except ValueError:
            job = self._job(job_id)
            if job is None: raise
            return job

    def _save_image(self, data):
        source_digest = hashlib.sha256(data).hexdigest()
        with self.store._connection() as db:
            row = db.execute('SELECT asset_id,sha256 FROM composition_assets WHERE source_sha256=?', (source_digest,)).fetchone()
            if row: return {'asset_id': row[0], 'sha256': row[1]}
            # Deterministic immutable ID makes retries safe across a crash after file creation.
            asset_id = str(UUID(source_digest[:32]))
            saved = board_assets.store(data, asset_id=asset_id)
            digest = hashlib.sha256(board_assets.read(saved['asset_id'])).hexdigest()
            db.execute('INSERT OR IGNORE INTO composition_assets VALUES (?,?,?)', (source_digest, asset_id, digest))
            return {'asset_id': asset_id, 'sha256': digest}

    def status(self, job_id, *, cancel=False):
        with self.lock:
            reservation = self._reservation(job_id)
            with self.store._connection() as db:
                row = db.execute('SELECT payload FROM composition_cancelled WHERE job_id=?', (job_id,)).fetchone()
                if row: return json.loads(row[0])
                if cancel and self._job(job_id) is None:
                    cancelled = {'job_id': job_id, 'revision_id': reservation[1], 'request_id': reservation[0],
                                 'prompt_id': None, 'prompt_id_kind': 'local', 'upstream_prompt_id': None,
                                 'status': 'cancelled', 'result': {'status': 'cancelled', 'outputs': [], 'error': 'Cancelled before adapter submission'}}
                    db.execute('INSERT INTO composition_cancelled VALUES (?,?)', (job_id, json.dumps(cancelled)))
                    return cancelled
            job = self._accepted(reservation)
            if job.get('status') == 'unavailable': return job
            history = self.store.job_history(job['revision_id'])
            existing = next(j for j in history if j['job_id'] == job_id)
            if existing['result'] is not None:
                return {**existing, 'status': existing['result']['status'], 'request_id': reservation[0],
                        'upstream_prompt_id': existing['result'].get('upstream_prompt_id')}
            info = self.adapter.cancel(job['prompt_id']) if cancel else self.adapter.result(job['prompt_id'])
            state = info['status']
            result = None
            if state in self.adapter.TERMINAL:
                if state == 'complete':
                    outputs = [self._save_image(self.adapter.image_bytes(job['prompt_id'], image['filename'], image.get('subfolder', '')))
                               for image in info.get('images', [])]
                    result = self.store.record_result(job_id, status='complete', outputs=outputs, upstream_prompt_id=info.get('upstream_prompt_id'))
                else:
                    error = info.get('error') or {'message': state}
                    result = self.store.record_result(job_id, status=state, error=json.dumps(error)[:2000], upstream_prompt_id=info.get('upstream_prompt_id'))
            return {**job, 'request_id': reservation[0], 'status': state, 'result': result,
                    'upstream_prompt_id': info.get('upstream_prompt_id'), 'prompt_id_kind': 'local'}

    def revision_jobs(self, revision):
        with self.store._connection() as db:
            ids = [r[0] for r in db.execute('SELECT job_id FROM composition_requests WHERE revision_id=? ORDER BY rowid', (revision['revision_id'],))]
        return {**revision, 'jobs': [self.status(jid) for jid in ids]}

    def dispatch(self, method, path, data=None):
        if path != '/v1/compositions' and not path.startswith('/v1/compositions/'): return None
        data = {} if data is None else data
        if type(data) is not dict: return 400, {'error': 'Expected object'}
        try:
            parts = path.rstrip('/').split('/')[3:]
            if not parts:
                if method == 'POST':
                    options = {k: v for k, v in data.items() if k not in ('graph', 'roots')}
                    options.setdefault('direction', 'both')
                    return 201, self.store.create(data.get('graph'), data.get('roots'), **options)
                if method == 'GET':
                    with self.store._connection() as db:
                        rows = db.execute('SELECT payload FROM semantic_revisions s WHERE version=(SELECT MAX(version) FROM semantic_revisions WHERE composition_id=s.composition_id) ORDER BY rowid DESC').fetchall()
                    return 200, {'items': [self.revision_jobs(json.loads(r[0])) for r in rows]}
            elif parts[0] == 'revisions' and len(parts) in (2, 3):
                rid = parts[1]
                if method == 'POST' and len(parts) == 2:
                    return 201, self.store.revise(rid, **data)
                if method == 'POST' and parts[2:] == ['generate']:
                    if set(data) != {'request_id'}: raise ValueError('Expected request_id only; revise prompt first')
                    job = self.generate(rid, data['request_id'])
                    return (503 if job['status'] == 'unavailable' else 202), job
            elif parts[0] == 'jobs' and len(parts) in (2, 3):
                if (method == 'GET' and len(parts) == 2) or (method == 'POST' and parts[2:] == ['cancel']):
                    job = self.status(parts[1], cancel=method == 'POST')
                    return (503 if job['status'] == 'unavailable' else 200), job
            elif len(parts) == 1 and method == 'GET':
                items = self.store.history(parts[0])
                if not items: raise KeyError('Unknown composition')
                return 200, {'items': [self.revision_jobs(item) for item in items]}
            return 404, {'error': 'Unknown composition route'}
        except KeyError:
            return 404, {'error': 'Composition, revision or job not found'}
        except RequestConflict as exc:
            return 409, {'error': str(exc)}
        except (ValueError, TypeError) as exc:
            return 400, {'error': str(exc)}
        except comfy_adapter.QueueFull:
            return 429, {'error': 'Local generation queue is full'}
        except (OSError, RuntimeError, sqlite3.Error):
            return 503, {'error': 'Local generation service temporarily unavailable'}


_service = None
_service_lock = threading.Lock()


def service():
    global _service
    with _service_lock:
        if _service is None:
            path = os.getenv('STUDY_COMPOSITIONS_DB', str(Path(__file__).with_name('compositions.sqlite')))
            _service = CompositionService(path)
        return _service


def dispatch(method, path, data=None):
    if path != '/v1/compositions' and not path.startswith('/v1/compositions/'): return None
    return service().dispatch(method, path, data)
