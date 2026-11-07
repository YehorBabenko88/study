"""Shared, local speech projects for all Study views.

Metadata in SQLite, optional PCM WAV in separate directory. No automatic cloud upload.
"""
import io
import json
import sqlite3
from contextlib import contextmanager
import wave
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4, UUID
from visual_memory import DB, LOCK

@contextmanager
def connection():
    db=sqlite3.connect(DB,timeout=30)
    try:
        yield db
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()

AUDIO_DIR=Path(__file__).with_name("speech_audio")
MAX_AUDIO=2_000_000
def init(db):
    db.execute("""CREATE TABLE IF NOT EXISTS speech_projects(
        id TEXT PRIMARY KEY, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        title TEXT NOT NULL, lang TEXT NOT NULL, transcript TEXT NOT NULL,
        segments_json TEXT NOT NULL, has_audio INTEGER NOT NULL DEFAULT 0)""")
def validate(data):
    if not isinstance(data,dict):raise ValueError("Expected object")
    title=data.get("title","Запись речи")
    lang=data.get("lang","de")
    text=data.get("transcript","")
    segs=data.get("segments",[])
    if not isinstance(title,str) or len(title)>120 or not isinstance(text,str) or len(text)>10000 or lang not in ("de","ru","en"):
        raise ValueError("Invalid speech metadata")
    if not isinstance(segs,list) or len(segs)>1000:raise ValueError("Too many segments")
    cleaned=[]
    for s in segs:
        if not isinstance(s,dict) or not isinstance(s.get("label"),str) or len(s["label"])>100:
            raise ValueError("Invalid segment")
        t=s.get("t")
        if isinstance(t,bool) or not isinstance(t,(int,float)) or not 0<=t<=1:
            raise ValueError("Invalid segment position")
        cleaned.append({"label":s["label"],"t":t})
    return title,lang,text,cleaned

def save(data):
    title,lang,text,segs=validate(data)
    project_id=data.get("id")
    pid=str(UUID(project_id)) if project_id else str(uuid4())
    now=datetime.now(timezone.utc).isoformat()
    with LOCK,connection() as db:
        init(db)
        db.execute("""INSERT INTO speech_projects(id,created_at,updated_at,title,lang,transcript,segments_json,has_audio)
            VALUES(?,?,?,?,?,?,?,0) ON CONFLICT(id) DO UPDATE SET
            updated_at=excluded.updated_at,title=excluded.title,lang=excluded.lang,
            transcript=excluded.transcript,segments_json=excluded.segments_json""",
            (pid,now,now,title,lang,text,json.dumps(segs,ensure_ascii=False)))
        db.commit()
    return get(pid)

def get(pid):
    pid=str(UUID(pid))
    with LOCK,connection() as db:
        init(db)
        row=db.execute("SELECT id,title,lang,transcript,segments_json,has_audio,updated_at FROM speech_projects WHERE id=?",(pid,)).fetchone()
    if row is None:return None
    return {"id":row[0],"title":row[1],"lang":row[2],"transcript":row[3],
            "segments":json.loads(row[4]),"has_audio":bool(row[5]),
            "audio_url":"/v1/speech-projects/"+pid+"/audio" if row[5] else None,"updated_at":row[6]}

def list_projects():
    with LOCK,connection() as db:
        init(db)
        rows=db.execute("SELECT id,title,lang,transcript,has_audio,updated_at FROM speech_projects ORDER BY updated_at DESC LIMIT 100").fetchall()
    return [{"id":a,"title":b,"lang":c,"transcript":d[:160],"has_audio":bool(e),"updated_at":f} for a,b,c,d,e,f in rows]

def save_audio(pid,data):
    pid=str(UUID(pid))
    if not isinstance(data,bytes) or not 1<=len(data)<=MAX_AUDIO:raise ValueError("WAV max 2 MB")
    try:
        with wave.open(io.BytesIO(data),"rb") as w:
            if w.getcomptype()!="NONE" or w.getsampwidth()!=2 or w.getnchannels() not in (1,2) or not 8000<=w.getframerate()<=48000 or w.getnframes()/w.getframerate()>8:
                raise ValueError("Expected 16-bit PCM WAV <=8 seconds")
    except (wave.Error,EOFError) as exc:raise ValueError("Invalid WAV") from exc
    if get(pid) is None:raise KeyError("Project not found")
    AUDIO_DIR.mkdir(exist_ok=True)
    dest=AUDIO_DIR/(pid+".wav")
    temp=AUDIO_DIR/(pid+".tmp")
    temp.write_bytes(data)
    temp.replace(dest)
    with LOCK,connection() as db:
        init(db)
        db.execute("UPDATE speech_projects SET has_audio=1,updated_at=? WHERE id=?",(datetime.now(timezone.utc).isoformat(),pid))
        db.commit()
    return get(pid)

def read_audio(pid):
    pid=str(UUID(pid))
    if get(pid) is None:return None
    path=AUDIO_DIR/(pid+".wav")
    return path.read_bytes() if path.is_file() else None
