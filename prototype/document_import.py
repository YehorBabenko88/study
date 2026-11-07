"""Resumable PDF page extraction with bounded work per HTTP request.

PDF bytes are stored locally; extraction and OCR are processed page by page.
"""
import io
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4,UUID
from datetime import datetime,timezone
from visual_memory import DB,LOCK

ROOT=Path(__file__).with_name("document_uploads")
MAX_UPLOAD=100_000_000
@contextmanager
def _db():
    db=sqlite3.connect(DB,timeout=30)
    db.execute("""CREATE TABLE IF NOT EXISTS documents(
      id TEXT PRIMARY KEY,name TEXT NOT NULL,page_count INTEGER NOT NULL,
      next_page INTEGER NOT NULL DEFAULT 0,status TEXT NOT NULL,
      created_at TEXT NOT NULL,error TEXT NOT NULL DEFAULT '')""")
    db.execute("""CREATE TABLE IF NOT EXISTS document_pages(
      document_id TEXT NOT NULL,page_number INTEGER NOT NULL,
      text TEXT NOT NULL,method TEXT NOT NULL,
      PRIMARY KEY(document_id,page_number))""")
    try:
        yield db
    finally:
        db.close()
def create(data,name):
    if not isinstance(data,bytes) or not 1<=len(data)<=MAX_UPLOAD or not data.startswith(b"%PDF-"):
        raise ValueError("PDF required, up to 100 MB per upload")
    if not isinstance(name,str) or len(name)>200:raise ValueError("Invalid filename")
    try:import pymupdf as fitz
    except ImportError:return {"status":"unavailable","reason":"pymupdf_missing"}
    try:
        with fitz.open(stream=data,filetype="pdf") as doc:
            pages=len(doc)
            if doc.needs_pass or not 1<=pages<=5000:raise ValueError("Encrypted or unsupported PDF")
    except Exception as exc:raise ValueError("Invalid or encrypted PDF") from exc
    pid=str(uuid4());ROOT.mkdir(exist_ok=True)
    path=ROOT/(pid+".pdf");path.write_bytes(data)
    with LOCK,_db() as db:
        db.execute("INSERT INTO documents VALUES(?,?,?,?,?,?,?)",
                   (pid,name,pages,0,"queued",datetime.now(timezone.utc).isoformat(),""))
        db.commit()
    return status(pid)
def status(pid):
    pid=str(UUID(pid))
    with LOCK,_db() as db:
        row=db.execute("SELECT id,name,page_count,next_page,status,error FROM documents WHERE id=?",(pid,)).fetchone()
    return dict(zip(("id","name","page_count","next_page","status","error"),row)) if row else None
def list_documents():
    with LOCK,_db() as db:
        rows=db.execute("SELECT id,name,page_count,next_page,status,error FROM documents ORDER BY created_at DESC LIMIT 100").fetchall()
    return [dict(zip(("id","name","page_count","next_page","status","error"),r)) for r in rows]
def process(pid,batch=2,ocr=False,retry=False):
    pid=str(UUID(pid));job=status(pid)
    if job is None:raise KeyError("document_not_found")
    if type(batch) is not int or not 1<=batch<=5:raise ValueError("Batch 1–5")
    if type(ocr) is not bool or type(retry) is not bool:raise ValueError("OCR and retry must be booleans")
    if retry and not ocr:raise ValueError("Retry requires OCR")
    if job['status']=='ocr_error' and not retry:return job
    try:import pymupdf as fitz
    except ImportError:return {"status":"unavailable","reason":"pymupdf_missing"}
    from PIL import Image
    try:
        if retry:
            with LOCK,_db() as db:
                numbers=[r[0] for r in db.execute("SELECT page_number FROM document_pages WHERE document_id=? AND method IN ('ocr_error','ocr_unavailable','no_text') ORDER BY page_number LIMIT ?",(pid,batch))]
        else:
            numbers=range(job['next_page'],min(job['next_page']+batch,job['page_count']))
        with fitz.open(ROOT/(pid+".pdf")) as pdf:
            for i in numbers:
                page=pdf[i];text=page.get_text("text",sort=True);method="pdf_text" if text.strip() else "no_text"
                error=''
                if ocr and not text.strip():
                    try:
                        import pytesseract
                        pix=page.get_pixmap(matrix=fitz.Matrix(1.5,1.5),alpha=False)
                        image=Image.frombytes("RGB",(pix.width,pix.height),pix.samples)
                        text=pytesseract.image_to_string(image,lang="deu",config="--psm 3",timeout=30)
                        method="tesseract_unverified" if text.strip() else "ocr_no_text"
                    except Exception as exc:
                        method="ocr_error"
                        error='OCR unavailable or failed; check Tesseract and deu language data, then Retry. '+type(exc).__name__
                with LOCK,_db() as db:
                    db.execute("INSERT OR REPLACE INTO document_pages VALUES(?,?,?,?)",(pid,i,text[:100000],method))
                    rows=dict(db.execute('SELECT page_number,method FROM document_pages WHERE document_id=?',(pid,)))
                    next_page=0
                    while next_page<job['page_count'] and next_page in rows and rows[next_page] not in ('ocr_error','ocr_unavailable'):
                        next_page+=1
                    has_error=any(value in ('ocr_error','ocr_unavailable') for value in rows.values())
                    state='ocr_error' if has_error else ('complete' if next_page==job['page_count'] else 'processing')
                    db.execute("UPDATE documents SET next_page=?,status=?,error=? WHERE id=?",
                               (next_page,state,error if error else (job['error'] if has_error else ''),pid))
                    db.commit()
                if method=='ocr_error':break
    except Exception as exc:
        with LOCK,_db() as db:
            db.execute("UPDATE documents SET status='failed',error=? WHERE id=?",(str(exc)[:300],pid));db.commit()
    return status(pid)
def page(pid,number):
    pid=str(UUID(pid))
    if not isinstance(number,int) or number<0:raise ValueError("Invalid page")
    with LOCK,_db() as db:
        row=db.execute("SELECT text,method FROM document_pages WHERE document_id=? AND page_number=?",(pid,number)).fetchone()
    return {"document_id":pid,"page_number":number,"text":row[0],"method":row[1]} if row else None
