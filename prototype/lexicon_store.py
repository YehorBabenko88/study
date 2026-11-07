"""Streaming, provenance-aware lexicon for Study. Separate SQLite DB, no row cap."""
import gzip
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB = Path(__file__).with_name("study_lexicon.sqlite3")
@contextmanager
def connect():
    db = sqlite3.connect(DB,timeout=30)
    try:
        db.execute("PRAGMA busy_timeout=30000")
        db.execute("""CREATE TABLE IF NOT EXISTS entries(
          id INTEGER PRIMARY KEY, lang TEXT NOT NULL, lemma TEXT NOT NULL,
          pos TEXT NOT NULL, source TEXT NOT NULL, source_key TEXT NOT NULL,
          senses_json TEXT NOT NULL, forms_json TEXT NOT NULL,
          translations_json TEXT NOT NULL, raw_json TEXT NOT NULL,
          UNIQUE(source,source_key))""")
        db.execute("CREATE INDEX IF NOT EXISTS entries_lookup ON entries(lang,lemma COLLATE NOCASE)")
        db.execute("""CREATE TABLE IF NOT EXISTS imports(
          source TEXT PRIMARY KEY, license TEXT NOT NULL, attribution TEXT NOT NULL,
          snapshot TEXT NOT NULL, imported INTEGER NOT NULL)""")
        yield db
    finally:
        db.close()

def search(q, lang="de", limit=30):
    if lang not in ("de","ru") or not isinstance(q,str) or len(q)>100:
        raise ValueError("invalid search")
    q=q.strip()
    if not q:
        return []
    # Escape LIKE metacharacters so user input is literal.
    pattern=q.replace("\\","\\\\").replace("%","\\%").replace("_","\\_")+"%"
    with connect() as db:
        rows=db.execute("""SELECT id,lang,lemma,pos,source,senses_json,forms_json,translations_json
          FROM entries WHERE lang=? AND lemma LIKE ? ESCAPE '\\'
          ORDER BY length(lemma),lemma LIMIT ?""",(lang,pattern,min(max(int(limit),1),100))).fetchall()
    return [{"id":id,"lang":lc,"lemma":word,"pos":pos,"source":src,
             "senses":json.loads(s),"forms":json.loads(f),"translations":json.loads(t)}
            for id,lc,word,pos,src,s,f,t in rows]

def entry_by_id(entry_id):
    with connect() as db:
        row=db.execute("SELECT lang,lemma,pos,source,senses_json,forms_json,translations_json FROM entries WHERE id=?",(entry_id,)).fetchone()
    if not row:return None
    lang,lemma,pos,source,s,f,t=row
    return {"id":entry_id,"lang":lang,"lemma":lemma,"pos":pos,"source":source,
            "senses":json.loads(s),"forms":json.loads(f),"translations":json.loads(t)}

def count():
    with connect() as db:
        rows=db.execute("SELECT lang,COUNT(*) FROM entries GROUP BY lang").fetchall()
    return dict(rows)

def stream(path):
    opener=gzip.open if str(path).endswith(".gz") else open
    with opener(path,"rt",encoding="utf-8") as f:
        for line in f:
            if line.strip():
                obj=json.loads(line)
                if isinstance(obj,dict):
                    yield obj

def import_file(path, *, source, license_id, attribution, snapshot, batch_size=1000):
    """Import an already downloaded and license-reviewed Wiktextract JSONL/GZ dump.

    No translations are fabricated. Existing source rows are upserted, preserving
    other sources. Import must be from a complete, trusted snapshot.
    """
    if not all(isinstance(x,str) and x.strip() for x in (source,license_id,attribution,snapshot)):
        raise ValueError("Source, license, attribution and snapshot are required")
    if not 1<=batch_size<=10000:
        raise ValueError("invalid batch size")
    total=0
    with connect() as db:
        db.execute("BEGIN")
        try:
            for obj in stream(path):
                lang=obj.get("lang_code")
                lemma=obj.get("word")
                pos=obj.get("pos")
                if lang not in ("de","ru") or not isinstance(lemma,str) or not lemma.strip() or not isinstance(pos,str):
                    continue
                # Wiktextract entries can have multiple etymologies, POS and senses.
                # Stable key uses source-specific normalized record identity when present.
                key=json.dumps([lang,lemma,pos,obj.get("etymology_number",0),obj.get("etymology_text","")],ensure_ascii=False)
                senses=obj.get("senses",[])
                forms=obj.get("forms",[])
                translations=obj.get("translations",[])
                if not isinstance(senses,list):senses=[]
                if not isinstance(forms,list):forms=[]
                if not isinstance(translations,list):translations=[]
                db.execute("""INSERT INTO entries(lang,lemma,pos,source,source_key,senses_json,forms_json,translations_json,raw_json)
                   VALUES(?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(source,source_key) DO UPDATE SET
                   senses_json=excluded.senses_json,forms_json=excluded.forms_json,
                   translations_json=excluded.translations_json,raw_json=excluded.raw_json""",
                   (lang,lemma,pos,source,key,json.dumps(senses,ensure_ascii=False),
                    json.dumps(forms,ensure_ascii=False),json.dumps(translations,ensure_ascii=False),
                    json.dumps(obj,ensure_ascii=False)))
                total+=1
                if total%batch_size==0:
                    db.commit()
                    db.execute("BEGIN")
            db.execute("""INSERT INTO imports(source,license,attribution,snapshot,imported)
                VALUES(?,?,?,?,?) ON CONFLICT(source) DO UPDATE SET
                license=excluded.license,attribution=excluded.attribution,
                snapshot=excluded.snapshot,imported=excluded.imported""",
                (source,license_id,attribution,snapshot,total))
            db.commit()
        except Exception:
            db.rollback()
            raise
    return total

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("path",type=Path)
    p.add_argument("--source",required=True)
    p.add_argument("--license",required=True)
    p.add_argument("--attribution",required=True)
    p.add_argument("--snapshot",required=True)
    args=p.parse_args()
    print("Imported:",import_file(args.path,source=args.source,license_id=args.license,
                                  attribution=args.attribution,snapshot=args.snapshot))
