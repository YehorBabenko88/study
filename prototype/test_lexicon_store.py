import tempfile,unittest,json
from pathlib import Path
from unittest.mock import patch
import lexicon_store
class LexiconTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.p=patch.object(lexicon_store,"DB",Path(self.tmp.name)/"lexicon.sqlite3")
        self.p.start()
    def tearDown(self):
        self.p.stop()
        self.tmp.cleanup()
    def test_import_and_search(self):
        p=Path(self.tmp.name)/"sample.jsonl"
        p.write_text("\n".join(json.dumps(x,ensure_ascii=False) for x in [
          {"lang_code":"de","word":"Tasse","pos":"noun","senses":[{"glosses":["cup"]}],"forms":[{"form":"Tassen"}]},
          {"lang_code":"de","word":"Haus","pos":"noun","senses":[{"glosses":["house"]}]},
          {"lang_code":"ru","word":"чашка","pos":"noun","senses":[{"glosses":["cup"]}]}
        ]),encoding="utf-8")
        args=dict(source="test",license_id="test-license",attribution="test-author",snapshot="test-snapshot")
        self.assertEqual(lexicon_store.import_file(p,**args),3)
        self.assertEqual(lexicon_store.import_file(p,**args),3)
        self.assertEqual(lexicon_store.count(),{"de":2,"ru":1})
        found=lexicon_store.search("Tas")
        self.assertEqual(found[0]["lemma"],"Tasse")
        self.assertEqual(lexicon_store.entry_by_id(found[0]["id"])["forms"][0]["form"],"Tassen")
        self.assertEqual(lexicon_store.search("чаш",lang="ru")[0]["lemma"],"чашка")
    def test_like_injection_escaped(self):
        self.assertEqual(lexicon_store.search("%"),[])
    def test_requires_provenance(self):
        with self.assertRaises(ValueError):
            lexicon_store.import_file("missing",source="",license_id="x",attribution="x",snapshot="x")
if __name__=="__main__":unittest.main()
