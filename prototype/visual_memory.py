"""Offline visual mnemonic renderer and SQLite persistence, no third-party dependencies."""
import html
from contextlib import contextmanager
import json
import sqlite3
from pathlib import Path
from threading import Lock
from uuid import uuid4
from datetime import datetime, timezone

DB = Path(__file__).with_name("study_local.sqlite3")
LOCK = Lock()

@contextmanager
def connection():
    """Close SQLite handles deterministically, including on Windows and errors."""
    db = sqlite3.connect(DB, timeout=10)
    try:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("""CREATE TABLE IF NOT EXISTS scenes(
            id TEXT PRIMARY KEY, word TEXT NOT NULL, payload TEXT NOT NULL,
            created_at TEXT NOT NULL)""")
        yield db
    finally:
        db.close()

def save(scene):
    sid = str(uuid4())
    scene = dict(scene)
    scene["scene_id"] = sid
    with LOCK, connection() as db:
        db.execute("INSERT INTO scenes VALUES (?,?,?,?)",
                   (sid, scene["target"]["lemma"], json.dumps(scene, ensure_ascii=False),
                    datetime.now(timezone.utc).isoformat()))
        db.commit()
    return scene

def list_scenes(limit=30):
    with LOCK, connection() as db:
        rows = db.execute("SELECT id, word, created_at FROM scenes ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [{"id": a, "word": b, "created_at": c} for a,b,c in rows]

def get_scene(sid):
    with LOCK, connection() as db:
        row = db.execute("SELECT payload FROM scenes WHERE id=?", (sid,)).fetchone()
    return json.loads(row[0]) if row else None

def delete_scene(sid):
    with LOCK, connection() as db:
        cur = db.execute("DELETE FROM scenes WHERE id=?", (sid,))
        db.commit()
        return cur.rowcount > 0

def svg(scene):
    """Render a genuine SVG image (diagram/storyboard, NOT a diffusion AI picture)."""
    anchors = scene["anchors"]
    height = 180 + 130 * len(anchors)
    if len(anchors) > 20:
        raise ValueError("too many anchors")
    target = scene["target"]
    esc = lambda x: html.escape(str(x), quote=True)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="760" height="{height}" viewBox="0 0 760 {height}" role="img">',
           '<rect width="100%" height="100%" fill="#f5f3ff"/>',
           f'<text x="35" y="54" font-family="Arial,sans-serif" font-size="29" font-weight="bold" fill="#312e81">{esc(target["article"])} {esc(target["lemma"])}</text>',
           f'<text x="35" y="88" font-family="Arial,sans-serif" font-size="20" fill="#475569">{esc(target["translation"])}</text>']
    for i,a in enumerate(anchors):
        y=115+i*130
        color=("#dbeafe","#fce7f3","#dcfce7","#fef3c7")[i%4]
        out.extend([
            f'<rect x="25" y="{y}" width="710" height="112" rx="17" fill="{color}"/>',
            f'<circle cx="80" cy="{y+56}" r="32" fill="#4338ca"/>',
            f'<text x="80" y="{y+63}" text-anchor="middle" font-family="Arial,sans-serif" font-size="17" fill="white">{i+1}</text>',
            f'<text x="135" y="{y+35}" font-family="Arial,sans-serif" font-size="19" font-weight="bold" fill="#1e293b">{esc(a["sound_fragment"][:30])} → {esc(a["object_name"][:45])}</text>',
            f'<text x="135" y="{y+75}" font-family="Arial,sans-serif" font-size="16" fill="#334155">{esc(a["meaning_link"][:65])}</text>',
        ])
    out.append('</svg>')
    return "".join(out).encode("utf-8")
