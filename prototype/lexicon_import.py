"""Stream Wiktextract JSONL for audit; no network, DB writes or bulk redistribution.

This is a conservative preview parser, not a verified German-Russian importer.
It extracts German entries and marks all sense links unreviewed.
"""
import argparse
import gzip
import json
from pathlib import Path

def iter_entries(path):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as stream:
        for lineno, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL line {lineno}") from exc
            if not isinstance(entry, dict):
                raise ValueError(f"Expected object at line {lineno}")
            yield entry

def preview(path, *, limit=20):
    if limit < 1:
        raise ValueError("limit must be positive")
    result = []
    for entry in iter_entries(path):
        if entry.get("lang_code") != "de":
            continue
        lemma = entry.get("word")
        pos = entry.get("pos")
        if not isinstance(lemma, str) or not isinstance(pos, str) or not lemma.strip():
            continue
        senses = entry.get("senses", [])
        if not isinstance(senses, list):
            senses = []
        result.append({
            "lemma": lemma,
            "pos": pos,
            "senses": [
                {"glosses": s.get("glosses", []), "review_status": "unreviewed"}
                for s in senses if isinstance(s, dict)
            ],
            "source_license_review_required": True,
        })
        if len(result) >= limit:
            break
    return result

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("jsonl", type=Path)
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    print(json.dumps(preview(args.jsonl, limit=args.limit), ensure_ascii=False, indent=2))
