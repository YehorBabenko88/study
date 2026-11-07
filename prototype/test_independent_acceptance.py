"""Independent acceptance: synthetic fixtures only; never touch existing Study data."""
import importlib
import sqlite3
import sys
import tempfile
import types
import unittest
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
import document_import

class IndependentDocumentAcceptance(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="study-independent-")
        self.root = Path(self.temp.name)
        self.patches = [patch.object(document_import, "DB", self.root / "study.sqlite"),
                        patch.object(document_import, "ROOT", self.root / "documents")]
        for p in self.patches: p.start()

    def tearDown(self):
        for p in reversed(self.patches): p.stop()
        # On Windows this also proves all database/file handles were released.
        self.temp.cleanup()

    def pdf(self, count, text=True):
        import pymupdf
        with pymupdf.open() as pdf:
            for i in range(count):
                page = pdf.new_page()
                if text: page.insert_text((72,72), f"Acceptance page {i+1}: German language sample sentence.")
            return pdf.tobytes()

    def test_150_page_resume_after_module_reload(self):
        job = document_import.create(self.pdf(150), "synthetic-150.pdf")
        pid = job["id"]
        self.assertEqual(document_import.process(pid, batch=5)["next_page"], 5)
        # A fresh module instance reads persisted progress rather than process memory.
        spec = importlib.util.spec_from_file_location("document_import_acceptance_restart", document_import.__file__)
        restarted = importlib.util.module_from_spec(spec); spec.loader.exec_module(restarted)
        restarted.DB = document_import.DB; restarted.ROOT = document_import.ROOT
        self.assertEqual(restarted.status(pid)["next_page"], 5)
        while restarted.status(pid)["next_page"] < 150: restarted.process(pid, batch=5)
        self.assertEqual(restarted.status(pid)["status"], "complete")
        self.assertIn("page 150", restarted.page(pid,149)["text"])
        with closing(sqlite3.connect(document_import.DB)) as db:
            self.assertEqual(db.execute("select count(*) from document_pages").fetchone()[0],150)
        self.assertEqual(restarted.process(pid,batch=5)["next_page"],150)

    def test_missing_german_ocr_is_explicit_and_resumable(self):
        def unavailable(*args, **kwargs):
            self.assertEqual(kwargs["lang"], "deu")
            raise RuntimeError("deu.traineddata missing")
        fake = types.SimpleNamespace(image_to_string=unavailable)
        job = document_import.create(self.pdf(2,text=False), "scan.pdf")
        with patch.dict(sys.modules, {"pytesseract": fake}):
            result = document_import.process(job["id"], batch=1, ocr=True)
        self.assertEqual(result["next_page"],0)
        self.assertEqual(result["status"],"ocr_error")
        self.assertEqual(document_import.page(job["id"],0)["method"],"ocr_error")
        self.assertEqual(document_import.process(job["id"],batch=1)["status"],"ocr_error")
        with patch.dict(sys.modules, {"pytesseract": types.SimpleNamespace(image_to_string=lambda *a, **k: "Recovered German") }):
            result=document_import.process(job["id"],batch=1,ocr=True,retry=True)
            self.assertEqual(result["next_page"],1)
            result=document_import.process(job["id"],batch=1,ocr=True)
        self.assertEqual(result["status"],"complete")
        self.assertEqual(document_import.page(job["id"],0)["text"],"Recovered German")

    def test_upload_limit_is_inclusive_and_rejects_oversize_without_writes(self):
        data = self.pdf(1)
        with patch.object(document_import, "MAX_UPLOAD", len(data)):
            self.assertEqual(document_import.create(data, "at-limit.pdf")["page_count"], 1)
        before = list(document_import.ROOT.iterdir())
        with patch.object(document_import, "MAX_UPLOAD", len(data)-1):
            with self.assertRaises(ValueError): document_import.create(data, "over-limit.pdf")
        self.assertEqual(list(document_import.ROOT.iterdir()), before)

    def test_upload_name_never_becomes_filesystem_path(self):
        job = document_import.create(self.pdf(1), "../../outside.pdf")
        self.assertTrue((document_import.ROOT/(job["id"]+".pdf")).is_file())
        self.assertFalse((self.root/"outside.pdf").exists())
        with self.assertRaises(ValueError): document_import.status("../../outside")
        with self.assertRaises(ValueError): document_import.create(b"not a PDF", "bad.pdf")

if __name__ == "__main__": unittest.main()
