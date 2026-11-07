import gzip
import json
import tempfile
import unittest
from pathlib import Path
from lexicon_import import preview

class ImportPreviewTests(unittest.TestCase):
    def test_filters_and_preserves_unreviewed(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "sample.jsonl"
            rows = [
                {"lang_code": "en", "word": "cup", "pos": "noun"},
                {"lang_code": "de", "word": "Tasse", "pos": "noun", "senses": [{"glosses": ["cup"]}]},
            ]
            path.write_text("\n".join(json.dumps(x) for x in rows), encoding="utf-8")
            out = preview(path)
            self.assertEqual(len(out), 1)
            self.assertEqual(out[0]["lemma"], "Tasse")
            self.assertEqual(out[0]["senses"][0]["review_status"], "unreviewed")

    def test_gzip(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "sample.jsonl.gz"
            with gzip.open(path, "wt", encoding="utf-8") as f:
                f.write(json.dumps({"lang_code": "de", "word": "Haus", "pos": "noun"}) + "\n")
            self.assertEqual(preview(path, limit=1)[0]["lemma"], "Haus")

    def test_invalid_json_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "bad.jsonl"
            path.write_text("{bad}", encoding="utf-8")
            with self.assertRaises(ValueError):
                preview(path)

if __name__ == "__main__":
    unittest.main()
