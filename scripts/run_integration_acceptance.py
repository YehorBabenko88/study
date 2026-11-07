"""Run tests against this exact checkout with disposable local storage only.

No model download, cloud service, migration of learner data, or user-path cleanup.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'prototype'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=('unit', 'browser'), required=True)
    parser.add_argument('--require-clean', action='store_true')
    args = parser.parse_args()
    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip()
    dirty = subprocess.check_output(['git', 'status', '--porcelain'], cwd=REPO, text=True).strip()
    if args.require_clean and dirty:
        raise SystemExit('Acceptance requires a clean committed HEAD: ' + dirty)
    print(json.dumps({'head': sha, 'dirty': bool(dirty), 'mode': args.mode}), flush=True)
    with tempfile.TemporaryDirectory(prefix='study-integration-') as fixture:
        data = Path(fixture)
        os.environ['STUDY_COMFYUI_DB'] = str(data / 'comfy.sqlite3')
        os.environ['STUDY_COMPOSITIONS_DB'] = str(data / 'compositions.sqlite3')
        os.environ['STUDY_COMFYUI_ENABLED'] = '0'
        import web_app
        for module in tuple(sys.modules.values()):
            source = getattr(module, '__file__', None)
            if not source or not Path(source).resolve().is_relative_to(REPO / 'prototype'):
                continue
            if hasattr(module, 'DB'):
                module.DB = data / ('lexicon.sqlite3' if module.__name__ == 'lexicon_store' else 'study.sqlite3')
            for attribute in ('ROOT', 'MEDIA', 'AUDIO_DIR'):
                if hasattr(module, attribute):
                    target = data / (module.__name__ + '-' + attribute)
                    target.mkdir(exist_ok=True)
                    setattr(module, attribute, target)
        server = thread = None
        try:
            if args.mode == 'browser':
                from http.server import ThreadingHTTPServer
                server = ThreadingHTTPServer(('127.0.0.1', 0), web_app.Handler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                os.environ['STUDY_E2E_URL'] = 'http://127.0.0.1:' + str(server.server_port)
                suite = unittest.TestSuite()
                for file in sorted((REPO / 'prototype').glob('test_*browser*.py')):
                    suite.addTests(unittest.defaultTestLoader.discover(str(REPO / 'prototype'), pattern=file.name))
            else:
                os.environ['STUDY_E2E_URL'] = ''
                suite = unittest.defaultTestLoader.discover(str(REPO / 'prototype'), pattern='test_*.py')
            result = unittest.TextTestRunner(verbosity=2).run(suite)
            failures = len(result.failures) + len(result.errors)
            summary = {'head': sha, 'mode': args.mode, 'total': result.testsRun,
                       'PASS': result.testsRun - failures - len(result.skipped),
                       'SKIP': len(result.skipped), 'FAIL_OR_ERROR': failures}
            print(json.dumps(summary), flush=True)
            passed = result.wasSuccessful() and (args.mode != 'browser' or (result.testsRun and not result.skipped))
        finally:
            if server:
                server.shutdown(); server.server_close(); thread.join()
            import comfy_adapter
            if comfy_adapter._registry is not None:
                comfy_adapter._registry.close(); comfy_adapter._registry = None
        return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
