"""Run unittest and optional real browser cases in an isolated source copy.

Example: python qa/verify_backend.py --evidence C:/path/to/evidence
Use a Python with Pillow, PyMuPDF and Playwright, and an already available
Chromium via PLAYWRIGHT_BROWSERS_PATH. This script installs nothing.
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--evidence',required=True,type=Path)
    parser.add_argument('--no-browser',action='store_true')
    args=parser.parse_args()
    repo=Path(__file__).resolve().parents[1]
    evidence=args.evidence.resolve();evidence.mkdir(parents=True,exist_ok=True)
    # Retain this generated snapshot for diagnosis. Never touch existing data.
    snapshot=Path(tempfile.mkdtemp(prefix='backend-verification-',dir=evidence))
    shutil.copytree(repo/'prototype',snapshot/'prototype',ignore=shutil.ignore_patterns(
        '__pycache__','*.sqlite*','*.db','board_assets','document_uploads','speech_audio'))
    sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
    metadata={'head':sha,'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'python':sys.version,'source_snapshot':str(snapshot),'browser_requested':not args.no_browser}
    (evidence/'verification.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    os.chdir(snapshot/'prototype');sys.path.insert(0,str(snapshot/'prototype'))
    import web_app
    server=ThreadingHTTPServer(('127.0.0.1',0),web_app.Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    if not args.no_browser:
        os.environ['STUDY_E2E_URL']=f'http://127.0.0.1:{server.server_port}'
    else:
        os.environ.pop('STUDY_E2E_URL',None)
    try:
        suite=unittest.defaultTestLoader.discover(str(snapshot/'prototype'))
        with (evidence/'unittest.log').open('w',encoding='utf-8') as log:
            result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
        metadata.update(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),
                        skipped=[{'test':str(t),'reason':reason} for t,reason in result.skipped])
        print(json.dumps(metadata,indent=2))
        return 0 if result.wasSuccessful() else 1
    finally:
        server.shutdown();server.server_close();thread.join()
        metadata['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
        (evidence/'verification.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')


if __name__=='__main__':
    raise SystemExit(main())
