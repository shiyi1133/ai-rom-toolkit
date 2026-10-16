"""Exercise guarded writes and preservation using synthetic bytes only."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("romkit", ROOT / "tools/romkit.py")
romkit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(romkit)


class GuardedPatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.base = self.folder / "synthetic.gba"
        self.original = bytes(range(256)) * 4
        self.base.write_bytes(self.original)
        self.definition = self.folder / "patch.json"
        self.output = self.folder / "result.gba"

    def args(self, writes, digest=None, output=None):
        self.definition.write_text(json.dumps({"base_sha256": digest or hashlib.sha256(self.original).hexdigest(), "writes": writes}), encoding="utf-8")
        return types.SimpleNamespace(rom=self.base, definition=self.definition, output=output or self.output)

    def test_changes_only_declared_bytes_and_preserves_base(self):
        romkit.guarded_patch(self.args([{"offset": 20, "before_hex": "14151617", "after_hex": "aabbccdd"}]))
        self.assertEqual(self.base.read_bytes(), self.original)
        expected = self.original[:20] + bytes.fromhex("aabbccdd") + self.original[24:]
        self.assertEqual(self.output.read_bytes(), expected)
        self.assertEqual(romkit.identity(self.output)["sha256"], hashlib.sha256(expected).hexdigest())

    def test_invalid_plans_write_nothing(self):
        one = {"offset": 20, "before_hex": "1415", "after_hex": "aabb"}
        plans = [([one], "0" * 64), ([dict(one, before_hex="0000")], None),
                 ([one, dict(one, offset=21)], None),
                 ([{"offset": 1024, "before_hex": "00", "after_hex": "ff"}], None),
                 ([dict(one, after_hex="aa")], None)]
        for writes, digest in plans:
            with self.subTest(writes=writes, digest=digest), self.assertRaises(ValueError):
                romkit.guarded_patch(self.args(writes, digest))
            self.assertFalse(self.output.exists())
            self.assertFalse(self.output.with_name(self.output.name + ".patch-report.json").exists())
            self.assertEqual(self.base.read_bytes(), self.original)

    def test_refuses_existing_output_and_input_overwrite(self):
        writes = [{"offset": 20, "before_hex": "1415", "after_hex": "aabb"}]
        with self.assertRaises(ValueError):romkit.guarded_patch(self.args(writes, output=self.base))
        self.output.write_bytes(b"keep")
        with self.assertRaises(ValueError):romkit.guarded_patch(self.args(writes))
        self.assertEqual(self.output.read_bytes(), b"keep")
        self.assertEqual(self.base.read_bytes(), self.original)

    def test_initializes_isolated_project_and_refuses_reinitialization(self):
        folder = self.folder / "project"
        args = types.SimpleNamespace(rom=self.base, platform="gba", project=folder, save=None, name="Synthetic")
        romkit.initialize(args)
        self.assertEqual((folder / "input/base.gba").read_bytes(), self.original)
        self.assertTrue((folder / "AGENTS.md").is_file())
        with self.assertRaises(ValueError):romkit.initialize(args)
        self.assertEqual(self.base.read_bytes(), self.original)

    def test_bank_offset_requires_physical_bank_and_correct_window(self):
        result = romkit.bank_offset(types.SimpleNamespace(bank=3, address="0x4567"))
        self.assertEqual(result["file_offset"], 0xC567)
        for bank, address in [(0, "0x4567"), (1, "0x1234"), (-1, "0x4567")]:
            with self.assertRaises(ValueError):romkit.bank_offset(types.SimpleNamespace(bank=bank, address=address))
