"""Local recall history and transparent interval scheduling (not FSRS)."""
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
from visual_memory import connection, LOCK, get_scene

INTERVAL_DAYS = (0, 1, 3, 7, 14, 30, 60)

def normalize(s):
    return " ".join(s.strip().casefold().split())

def init(db):
    db.execute("""CREATE TABLE IF NOT EXISTS recall_attempts(
        id TEXT PRIMARY KEY, scene_id TEXT NOT NULL, response TEXT NOT NULL,
        correct INTEGER NOT NULL, occurred_at TEXT NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS recall_schedule(
        scene_id TEXT PRIMARY KEY, streak INTEGER NOT NULL, due_at TEXT NOT NULL)""")

def due_scenes(now=None):
    now = now or datetime.now(timezone.utc)
    with LOCK, connection() as db:
        init(db)
        rows = db.execute("""SELECT s.id, s.word, COALESCE(r.due_at,'') FROM scenes s
            LEFT JOIN recall_schedule r ON r.scene_id=s.id
            WHERE r.due_at IS NULL OR r.due_at <= ?
            ORDER BY s.created_at LIMIT 30""", (now.isoformat(),)).fetchall()
    return [{"scene_id": sid, "word": word, "due_at": due} for sid,word,due in rows]

def submit(scene_id, response, now=None):
    scene_id = str(UUID(scene_id))
    if not isinstance(response,str) or len(response)>200:
        raise ValueError("Invalid response")
    scene = get_scene(scene_id)
    if scene is None:
        raise KeyError("scene_not_found")
    now = now or datetime.now(timezone.utc)
    target = scene["target"]
    expected = (target.get("article","") + " " + target["lemma"]).strip()
    correct = normalize(expected) == normalize(response)
    with LOCK, connection() as db:
        init(db)
        old = db.execute("SELECT streak FROM recall_schedule WHERE scene_id=?", (scene_id,)).fetchone()
        streak = min((old[0] if old else 0) + 1, len(INTERVAL_DAYS)-1) if correct else 0
        due = now + timedelta(days=INTERVAL_DAYS[streak])
        db.execute("INSERT INTO recall_attempts VALUES (?,?,?,?,?)",
                   (str(uuid4()),scene_id,response,int(correct),now.isoformat()))
        db.execute("""INSERT INTO recall_schedule(scene_id,streak,due_at) VALUES(?,?,?)
          ON CONFLICT(scene_id) DO UPDATE SET streak=excluded.streak,due_at=excluded.due_at""",
          (scene_id,streak,due.isoformat()))
        db.commit()
    return {"correct":correct,"expected":expected,"streak":streak,"next_due":due.isoformat(),
            "algorithm":"simple_intervals_v0", "note":"Exact text matching, not speech or semantic assessment"}

def stats(scene_id):
    scene_id=str(UUID(scene_id))
    with LOCK, connection() as db:
        init(db)
        count,success=db.execute("SELECT COUNT(*),COALESCE(SUM(correct),0) FROM recall_attempts WHERE scene_id=?", (scene_id,)).fetchone()
        row=db.execute("SELECT streak,due_at FROM recall_schedule WHERE scene_id=?", (scene_id,)).fetchone()
    return {"attempts":count,"correct":success,"streak":row[0] if row else 0,
            "next_due":row[1] if row else None}
