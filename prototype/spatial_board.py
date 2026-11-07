"""Local spatial board persistence, separate from mnemonic scenes."""
import json
import math
import sqlite3
from uuid import uuid4,UUID
from visual_memory import connection,LOCK

def init(db):
    db.execute("""CREATE TABLE IF NOT EXISTS spatial_boards(
      id TEXT PRIMARY KEY,title TEXT NOT NULL,document TEXT NOT NULL)""")

def validate(doc):
    if not isinstance(doc,dict):raise ValueError("document must be object")
    nodes=doc.get("nodes",[]);edges=doc.get("edges",[])
    if not isinstance(nodes,list) or len(nodes)>10000 or not isinstance(edges,list) or len(edges)>30000:
        raise ValueError("board too large")
    ids=set()
    for n in nodes:
        if not isinstance(n,dict) or not isinstance(n.get("id"),str) or len(n["id"])>80 or n["id"] in ids:
            raise ValueError("invalid node id")
        ids.add(n["id"])
        if n.get("type") not in ("letter","word","syllable","image","sentence","note","action"):
            raise ValueError("invalid node type")
        if not isinstance(n.get("text",""),str) or len(n.get("text",""))>5000:
            raise ValueError("invalid text")
        for key in ("x","y"):
            val=n.get(key,0)
            if isinstance(val,bool) or not isinstance(val,(int,float)) or not math.isfinite(val) or not -100000<=val<=100000:
                raise ValueError("invalid coordinate")
        if "scene_id" in n:
            if n["type"]!="image" or not isinstance(n["scene_id"],str):
                raise ValueError("scene reference only allowed on image nodes")
            try:
                UUID(n["scene_id"])
            except ValueError as exc:
                raise ValueError("invalid scene reference") from exc
        if "asset_id" in n:
            if n["type"]!="image" or not isinstance(n["asset_id"],str):
                raise ValueError("asset reference only allowed on image nodes")
            try:
                UUID(n["asset_id"])
            except ValueError as exc:
                raise ValueError("invalid asset reference") from exc
    for e in edges:
        if not isinstance(e,dict) or e.get("from") not in ids or e.get("to") not in ids:
            raise ValueError("dangling edge")
        if e.get("relation","association") not in ("association","part_of","sequence","meaning","sound","action"):
            raise ValueError("invalid relation")
    return {"nodes":nodes,"edges":edges}

def save(doc,board_id=None,title="Моя доска"):
    doc=validate(doc)
    bid=str(UUID(board_id)) if board_id else str(uuid4())
    if not isinstance(title,str) or len(title)>100:raise ValueError("invalid title")
    with LOCK,connection() as db:
        init(db)
        db.execute("""INSERT INTO spatial_boards VALUES(?,?,?)
            ON CONFLICT(id) DO UPDATE SET title=excluded.title,document=excluded.document""",
            (bid,title,json.dumps(doc,ensure_ascii=False)))
        db.commit()
    return {"id":bid,"title":title}

def load(board_id):
    bid=str(UUID(board_id))
    with LOCK,connection() as db:
        init(db)
        row=db.execute("SELECT title,document FROM spatial_boards WHERE id=?",(bid,)).fetchone()
    return {"id":bid,"title":row[0],**json.loads(row[1])} if row else None

def list_boards():
    with LOCK,connection() as db:
        init(db)
        rows=db.execute("SELECT id,title FROM spatial_boards ORDER BY rowid DESC LIMIT 100").fetchall()
    return [{"id":bid,"title":title} for bid,title in rows]
