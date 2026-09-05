"""Tests for the system janitor (computer-junk cleanup)."""

from __future__ import annotations

import os
import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from litter_scoop.janitor import (
    JanitorBag,
    JanitorTarget,
    _flatten_absolute,
    human_size,
    render_schedule,
    scan_system,
)


def _make_old(path: Path, content: bytes, *, age_days: float = 30) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    old = time.time() - age_days * 86400
    os.utime(path, (old, old))


def _make_fresh(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


class TargetDiscoveryTests(unittest.TestCase):
    def test_no_default_keeps_only_extra(self) -> None:
        from litter_scoop.janitor import discover_targets
        targets = discover_targets(
            extra_paths=[Path("/some/dir")], include_defaults=False
        )
        self.assertEqual(len(targets), 1)
        self.assertTrue(targets[0].category.startswith("custom-"))

    def test_default_targets_present(self) -> None:
        from litter_scoop.janitor import discover_targets
        targets = discover_targets()
        self.assertGreaterEqual(len(targets), 3)
        self.assertNotIn(
            "recycle-bin", {t.category for t in targets}
        )  # risky hidden by default


class JanitorScanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.junk = self.root / "fake-temp"
        _make_old(self.junk / "a.tmp", b"old-one")
        _make_old(self.junk / "nested" / "b.log", b"old-two" * 100)
        _make_fresh(self.junk / "fresh.tmp", b"just-created")
        self.target = JanitorTarget("custom-0", "fake", self.junk)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_age_gate_keeps_recent_files(self) -> None:
        scan = scan_system(max_age_days=7, targets=[self.target])
        names = {f.path.name for f in scan.files}
        self.assertEqual(names, {"a.tmp", "b.log"})
        self.assertNotIn("fresh.tmp", names)

    def test_zero_age_means_everything(self) -> None:
        scan = scan_system(max_age_days=0, targets=[self.target])
        self.assertEqual(scan.total_files, 3)

    def test_size_accounting(self) -> None:
        scan = scan_system(max_age_days=7, targets=[self.target])
        expected = len(b"old-one") + len(b"old-two" * 100)
        self.assertEqual(scan.total_bytes, expected)
        grouped = scan.by_category()
        self.assertIn("custom-0", grouped)

    def test_name_globs_filter(self) -> None:
        target = JanitorTarget("g", "g", self.junk, name_globs=("*.log",))
        scan = scan_system(max_age_days=0, targets=[target])
        self.assertEqual({f.path.name for f in scan.files}, {"b.log"})

    def test_missing_target_recorded(self) -> None:
        ghost = JanitorTarget("x", "x", self.root / "nope")
        scan = scan_system(targets=[ghost])
        self.assertEqual(scan.files, [])
        self.assertIn("x", scan.missing_targets)

    def test_symlink_escape_is_skipped(self) -> None:
        outside = self.root / "outside.txt"
        _make_old(outside, b"outside")
        link = self.junk / "escape.lnk"
        try:
            os.symlink(outside, link)
        except (OSError, NotImplementedError):
            self.skipTest("当前平台/权限不允许创建符号链接")
        scan = scan_system(max_age_days=0, targets=[self.target])
        names = {f.path.name for f in scan.files}
        self.assertNotIn("escape.lnk", names)
        self.assertTrue(outside.exists())  # never touched
        self.assertTrue(any("escape.lnk" in p for p, _ in scan.skipped))


class JanitorBagTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.junk = self.root / "fake-temp"
        self.old = {
            "a.tmp": b"aaaa",
            "deep" + os.sep + "b.tmp": b"bbbb" * 50,
        }
        for rel, data in self.old.items():
            _make_old(self.junk / rel, data)
        self.bag_dir = self.root / "bag"
        self.bag = JanitorBag(self.bag_dir)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _scan(self):
        target = JanitorTarget("custom-0", "fake", self.junk)
        return scan_system(max_age_days=7, targets=[target])

    def test_bag_then_restore_roundtrip(self) -> None:
        scan = self._scan()
        originals = {str(f.path): f.path.read_bytes() for f in scan.files}
        batch = self.bag.scoop(scan.files, note="t")
        self.assertEqual(batch.mode, "bag")
        # sources removed, backups exist
        for f in scan.files:
            self.assertFalse(f.path.exists())
        self.assertTrue(self.bag.manifest_dir.joinpath(f"{batch.batch_id}.json").exists())
        # restore
        restored = self.bag.restore(batch.batch_id)
        self.assertEqual(len(restored), len(originals))
        for path_str, data in originals.items():
            self.assertEqual(Path(path_str).read_bytes(), data)

    def test_delete_mode_has_no_backup(self) -> None:
        scan = self._scan()
        batch = self.bag.scoop(scan.files, delete=True)
        self.assertEqual(batch.mode, "delete")
        for f in scan.files:
            self.assertFalse(f.path.exists())
        with self.assertRaises(ValueError):
            self.bag.restore(batch.batch_id)

    def test_list_and_stats(self) -> None:
        scan = self._scan()
        self.bag.scoop(scan.files)
        batches = self.bag.list_batches()
        self.assertEqual(len(batches), 1)
        stats = self.bag.stats()
        self.assertEqual(stats["batches"], 1)
        self.assertEqual(stats["items"], 2)

    def test_empty_destroys_everything(self) -> None:
        scan = self._scan()
        self.bag.scoop(scan.files)
        removed = self.bag.empty()
        self.assertEqual(removed, 1)
        self.assertFalse(self.bag.dir.exists())


class HelpersTests(unittest.TestCase):
    def test_flatten_roundtrip_windows_shape(self) -> None:
        if sys.platform.startswith("win"):
            flat = _flatten_absolute(Path(r"C:\Users\me\Temp\a.tmp"))
            self.assertEqual(flat.as_posix(), "drive-c/Users/me/Temp/a.tmp")
            # Must stay a pure relative path so bag joins work.
            self.assertFalse(flat.is_absolute())
        else:
            flat = _flatten_absolute(Path("/tmp/a.tmp"))
            self.assertEqual(flat, Path("tmp", "a.tmp"))

    def test_human_size(self) -> None:
        self.assertEqual(human_size(512), "512 B")
        self.assertTrue(human_size(2048).endswith("KB"))
        self.assertTrue(human_size(5 * 1024 ** 2).endswith("MB"))

    def test_render_schedule_mentions_task_and_runner(self) -> None:
        line = render_schedule(freq="weekly", at="09:30", day="SUN")
        self.assertIn("CatLitterJanitor", line)
        self.assertIn("janitor scoop", line)
        daily = render_schedule(freq="daily", at="08:00")
        self.assertIn("janitor scoop", daily)


if __name__ == "__main__":
    unittest.main()
