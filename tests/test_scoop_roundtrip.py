from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from _bootstrap import FIXTURE_ROOT, SRC

sys.path.insert(0, str(SRC))

from litter_scoop.config import Config
from litter_scoop.engine import scan_project
from litter_scoop.models import sha256_file
from litter_scoop.scoop import GarbageBag, merge_ranges, remove_line_ranges


class RangeTests(unittest.TestCase):
    def test_merge_ranges(self):
        self.assertEqual(merge_ranges([(1, 2), (3, 4), (6, 7)]), [(1, 4), (6, 7)])
        self.assertEqual(merge_ranges([]), [])

    def test_remove_lines(self):
        source = "a\nb\nc\nd\n"
        self.assertEqual(remove_line_ranges(source, [(2, 3)]), "a\nd\n")


class ScoopRoundTripTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="litter-test-"))
        work = self.tmp / "proj"
        shutil.copytree(FIXTURE_ROOT, work)
        self.work = work

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _snapshot(self):
        snap = {}
        for p in self.work.rglob("*"):
            if p.is_file() and ".litter-box" not in p.parts:
                snap[p.relative_to(self.work).as_posix()] = sha256_file(p)
        return snap

    def test_bag_then_restore_is_byte_identical(self):
        before = self._snapshot()
        cfg = Config()
        cfg.require_clean_git = False
        result = scan_project(self.work, cfg)
        bag = GarbageBag(self.work, cfg)
        batch = bag.scoop(result.findings)

        # Source tree actually changed / whole-file findings removed files.
        after_scoop = self._snapshot()
        self.assertNotEqual(before, after_scoop)
        self.assertGreaterEqual(len(bag.list_batches()), 1)

        restored = bag.restore(batch.batch_id)
        self.assertTrue(restored)
        after_restore = self._snapshot()
        self.assertEqual(before, after_restore, "恢复后必须与原始字节完全一致")

    def test_delete_mode_has_no_backup(self):
        cfg = Config()
        cfg.require_clean_git = False
        result = scan_project(self.work, cfg)
        bag = GarbageBag(self.work, cfg)
        batch = bag.scoop(result.findings, delete=True)
        self.assertTrue(any(i.action.startswith("delete-") for i in batch.items))
        with self.assertRaises(Exception):
            bag.restore(batch.batch_id)

    def test_empty_removes_bag(self):
        cfg = Config()
        cfg.require_clean_git = False
        result = scan_project(self.work, cfg)
        bag = GarbageBag(self.work, cfg)
        bag.scoop(result.findings)
        removed = bag.empty()
        self.assertEqual(removed, 1)
        self.assertFalse(bag.dir.exists())


if __name__ == "__main__":
    unittest.main()
