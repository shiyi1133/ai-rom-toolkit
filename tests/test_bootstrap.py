"""Check archive safety and installation ownership without network or binaries."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("bootstrap", ROOT / "tools/bootstrap_environment.py")
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


class BootstrapTests(unittest.TestCase):
    def test_rejects_escape_paths(self):
        for name in ["../outside", "/outside", "C:/outside", "folder/../../outside", "..\\outside"]:
            with self.subTest(name=name), self.assertRaises(ValueError):bootstrap.checked_member(name)

    def test_bad_hash_preserves_archive(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / "download.zip"
            archive.write_bytes(b"untrusted")
            with self.assertRaises(ValueError):bootstrap.verify_archive(archive, "0" * 64)
            self.assertEqual(archive.read_bytes(), b"untrusted")

    def test_zip_with_escape_does_not_extract_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); archive = root / "bad.zip"; stage = root / "stage"; stage.mkdir()
            with zipfile.ZipFile(archive, "w") as out:
                out.writestr("ok.txt", "ok"); out.writestr("../outside", "bad")
            with self.assertRaises(ValueError):bootstrap.extract_archive(archive, stage, "zip")
            self.assertEqual(list(stage.iterdir()), [])
            self.assertFalse((root / "outside").exists())

    def test_unowned_directory_is_not_adopted(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder); (target / "keep.txt").write_text("keep")
            with self.assertRaises(ValueError):bootstrap.installed({"id": "x", "sha256": "0" * 64}, target)
            self.assertEqual((target / "keep.txt").read_text(), "keep")

    def test_modified_installed_entry_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder); entry = target / "tool.exe"; entry.write_bytes(b"original")
            spec = {"id": "x", "sha256": "0" * 64, "entrypoints": ["tool.exe"]}
            marker = {"id": "x", "archive_sha256": "0" * 64,
                      "entrypoints": {"tool.exe": hashlib.sha256(b"original").hexdigest()}}
            (target / ".dependency.json").write_text(json.dumps(marker))
            self.assertTrue(bootstrap.installed(spec, target))
            entry.write_bytes(b"changed")
            with self.assertRaises(ValueError):bootstrap.installed(spec, target)
