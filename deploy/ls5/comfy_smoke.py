"""Guarded LS5 inference validation; fixtures are explicitly distinguished.

Run with the staged Study Python (Pillow installed). This module installs nothing.
The engine starts/stops only its own verified managed Comfy process around it.
"""
import argparse
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import socket
import sys
import time
from urllib.parse import urlencode, urlsplit
from uuid import UUID, uuid4


class SmokeError(RuntimeError):
    pass


def _atomic_json(path, value):
    temporary = path.with_name(path.name + '.partial')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True)
        stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _png(data):
    from PIL import Image
    try:
        with Image.open(BytesIO(data)) as image:
            if image.format != 'PNG' or not 0 < image.width * image.height <= 16_000_000:
                raise SmokeError('Expected bounded PNG')
            dimensions = list(image.size); image.verify()
        with Image.open(BytesIO(data)) as image: image.load()
        return dimensions
    except (OSError, ValueError, Image.DecompressionBombError) as error:
        raise SmokeError('Generated PNG is invalid') from error


def run_probe(checkpoint, output_dir, timeout=300, base_url='http://127.0.0.1:8188', *, _fixture=False, verify_only=False):
    if not _fixture and socket.gethostname().upper() != 'LS5':
        raise SmokeError('Actual generation validation is restricted to LS5')
    url = urlsplit(base_url)
    if url.scheme != 'http' or url.hostname != '127.0.0.1' or url.username or url.password or url.path or url.query or url.fragment:
        raise SmokeError('Only a local loopback Comfy endpoint is allowed')
    if not _fixture and base_url != 'http://127.0.0.1:8188':
        raise SmokeError('LS5 Comfy endpoint must be 127.0.0.1:8188')
    if type(timeout) not in (int, float) or not 0 < timeout <= 900:
        raise SmokeError('Use a bounded inference timeout')
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'prototype'))
    import comfy_adapter as adapter
    previous = os.environ.get('STUDY_COMFYUI_CHECKPOINT')
    try:
        os.environ['STUDY_COMFYUI_CHECKPOINT'] = checkpoint
        workflow = adapter.workflow('A blue geometric cube beside a red cup, one simple scene', seed=23)
    except (ValueError, TypeError) as error:
        raise SmokeError('Checkpoint must be a reviewed supported local filename') from error
    finally:
        if previous is None: os.environ.pop('STUDY_COMFYUI_CHECKPOINT', None)
        else: os.environ['STUDY_COMFYUI_CHECKPOINT'] = previous
    workflow_hash = _digest(json.dumps(workflow, sort_keys=True).encode())
    output = Path(output_dir)
    if output.is_symlink() or output.is_junction(): raise SmokeError('Linked validation root refused')
    output = output.resolve()
    proof_path = output/'proof.json'; journal_path = output/'probe-job.json'
    proof_type = 'fixture_comfy_http' if _fixture else 'real_comfy_http'
    if proof_path.exists():
        proof = json.loads(proof_path.read_text(encoding='utf-8'))
        image = Path(proof.get('image_path', '')).resolve()
        if (proof.get('state') != 'complete' or proof.get('proof_type') != proof_type
                or proof.get('checkpoint') != checkpoint or proof.get('workflow_sha256') != workflow_hash
                or image.parent != output or image.is_symlink() or not image.is_file()):
            raise SmokeError('Existing proof does not match this reviewed request')
        raw = image.read_bytes()
        if len(raw) > 8_000_000 or _digest(raw) != proof.get('sha256'): raise SmokeError('Saved proof image changed')
        _png(raw)
        try: UUID(proof.get('prompt_id'))
        except (ValueError, TypeError, AttributeError) as error: raise SmokeError('Saved proof prompt ID is invalid') from error
        if proof.get('image_dimensions') != _png(raw): raise SmokeError('Saved image dimensions changed')
        return proof
    if verify_only: raise SmokeError('An existing completed proof is required; verification never launches inference')
    output.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    def request(path, payload=None, binary=False):
        remaining = deadline - time.monotonic()
        if remaining <= 0: raise SmokeError('Real inference validation deadline exceeded')
        from urllib.request import Request
        data = json.dumps(payload).encode() if payload is not None else None
        req = Request(base_url+path, data=data, headers={'Content-Type': 'application/json'} if data else {})
        try:
            with adapter._open(req, timeout=min(15, remaining)) as response:
                raw = adapter._read_bounded(response, 8_000_000 if binary else 4_000_000, min(15, remaining))
            if len(raw) > (8_000_000 if binary else 4_000_000): raise SmokeError('Comfy response exceeds limit')
            result = raw if binary else json.loads(raw)
            if not binary and not isinstance(result, dict): raise SmokeError('Comfy returned invalid JSON shape')
            return result
        except (OSError, ValueError) as error:
            raise SmokeError('Local Comfy validation request failed') from error
    before = request('/system_stats')
    if journal_path.exists():
        journal = json.loads(journal_path.read_text(encoding='utf-8'))
        if journal.get('workflow_sha256') != workflow_hash or journal.get('checkpoint') != checkpoint:
            raise SmokeError('Pending validation belongs to another reviewed request')
        prompt_id = journal.get('prompt_id')
    else:
        response = request('/prompt', {'prompt': workflow, 'client_id': str(uuid4())})
        prompt_id = response.get('prompt_id')
        try: UUID(prompt_id)
        except (ValueError, TypeError, AttributeError) as error: raise SmokeError('Comfy returned an invalid prompt ID') from error
        _atomic_json(journal_path, {'checkpoint': checkpoint, 'workflow_sha256': workflow_hash, 'prompt_id': prompt_id})
    try: UUID(prompt_id)
    except (ValueError, TypeError, AttributeError) as error: raise SmokeError('Invalid pending prompt ID') from error
    while time.monotonic() < deadline:
        history = request('/history/'+prompt_id).get(prompt_id)
        if history:
            if history.get('status', {}).get('status_str') == 'error':
                raise SmokeError('Comfy inference failed; integration remains inactive')
            images = [entry for node in history.get('outputs', {}).values() for entry in node.get('images', [])
                      if entry.get('type', 'output') == 'output']
            if images:
                image = images[0]
                try: adapter._image_name(image.get('filename'), image.get('subfolder', ''))
                except ValueError as error: raise SmokeError('Invalid Comfy output descriptor') from error
                raw = request('/view?'+urlencode({'filename': image['filename'], 'subfolder': image.get('subfolder', ''), 'type': 'output'}), binary=True)
                dimensions = _png(raw)
                target = output/('validated-'+str(uuid4())+'.png')
                with target.open('xb') as stream: stream.write(raw); stream.flush(); os.fsync(stream.fileno())
                proof = {'state': 'complete', 'proof_type': proof_type, 'checkpoint': checkpoint,
                         'prompt_id': prompt_id, 'workflow_sha256': workflow_hash, 'sha256': _digest(raw),
                         'image_path': str(target), 'image_dimensions': dimensions,
                         'system_stats_before': before, 'system_stats_after': request('/system_stats'),
                         'completed_at_utc': datetime.now(timezone.utc).isoformat()}
                _atomic_json(proof_path, proof)
                return proof
            if history.get('status', {}).get('completed'): raise SmokeError('Comfy completed without an image')
        time.sleep(min(.25, max(0, deadline-time.monotonic())))
    raise SmokeError('Real inference validation deadline exceeded')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--timeout', type=float, default=300)
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    print(json.dumps(run_probe(args.checkpoint, args.output, args.timeout, verify_only=args.verify_only)), flush=True)


if __name__ == '__main__': main()
