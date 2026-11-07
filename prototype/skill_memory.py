"""Independent per-skill review tracking, retaining existing legacy review history."""
from datetime import datetime, timezone, timedelta
from uuid import UUID, uuid4
from visual_memory import LOCK, connection, get_scene

SKILLS = ("word", "article", "meaning", "image_link", "pronunciation")
DAYS = (0, 1, 3, 7, 14, 30, 60)

def setup(db):
    db.execute("""CREATE TABLE IF NOT EXISTS skill_attempts (
      id TEXT PRIMARY KEY, scene_id TEXT NOT NULL, skill TEXT NOT NULL,
      response TEXT NOT NULL, result INTEGER NOT NULL,
      assessment TEXT NOT NULL, at TEXT NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS skill_schedule (
      scene_id TEXT NOT NULL, skill TEXT NOT NULL,
      streak INTEGER NOT NULL, due_at TEXT NOT NULL,
      PRIMARY KEY(scene_id,skill))""")

def norm(s):
    return " ".join(s.casefold().strip().split())

def expected_for(scene, skill):
    t = scene["target"]
    if skill == "word":
        return t["lemma"]
    if skill == "article":
        return t["article"]
    if skill == "meaning":
        return t["translation"]
    return None

def record(scene_id, skill, response, now=None):
    sid = str(UUID(scene_id))
    if skill not in SKILLS or not isinstance(response,str) or len(response)>200:
        raise ValueError("Invalid skill or response")
    scene = get_scene(sid)
    if scene is None:
        raise KeyError("scene_not_found")
    now = now or datetime.now(timezone.utc)
    expected = expected_for(scene, skill)
    if expected is None:
        if response not in ("remembered", "forgot"):
            raise ValueError("Self assessment must be remembered or forgot")
        correct = response == "remembered"
        assessment = "self_report"
    else:
        correct = norm(expected) == norm(response)
        assessment = "exact_match"
    with LOCK, connection() as db:
        setup(db)
        row = db.execute("SELECT streak FROM skill_schedule WHERE scene_id=? AND skill=?",
                         (sid,skill)).fetchone()
        streak = min((row[0] if row else 0)+1,len(DAYS)-1) if correct else 0
        due = now + timedelta(days=DAYS[streak])
        db.execute("INSERT INTO skill_attempts VALUES (?,?,?,?,?,?,?)",
                   (str(uuid4()),sid,skill,response,int(correct),assessment,now.isoformat()))
        db.execute("""INSERT INTO skill_schedule VALUES (?,?,?,?)
          ON CONFLICT(scene_id,skill) DO UPDATE SET
          streak=excluded.streak,due_at=excluded.due_at""",
          (sid,skill,streak,due.isoformat()))
        db.commit()
    return {"skill":skill,"correct":correct,"expected":expected,"assessment":assessment,
            "streak":streak,"next_due":due.isoformat(),"algorithm":"simple_intervals_v1"}

def overview(scene_id):
    sid=str(UUID(scene_id))
    if get_scene(sid) is None:
        raise KeyError("scene_not_found")
    with LOCK, connection() as db:
        setup(db)
        rows=db.execute("""SELECT a.skill,COUNT(*),SUM(a.result),s.streak,s.due_at
          FROM skill_attempts a JOIN skill_schedule s ON a.scene_id=s.scene_id AND a.skill=s.skill
          WHERE a.scene_id=? GROUP BY a.skill,s.streak,s.due_at""",(sid,)).fetchall()
    result={skill:{"attempts":0,"correct":0,"streak":0,"next_due":None} for skill in SKILLS}
    for skill,count,correct,streak,due in rows:
        result[skill]={"attempts":count,"correct":correct,"streak":streak,"next_due":due}
    return result
