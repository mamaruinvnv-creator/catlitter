from __future__ import annotations

import sys
import unittest

from _bootstrap import FIXTURE_ROOT, SRC

sys.path.insert(0, str(SRC))

from litter_scoop.config import Config
from litter_scoop.engine import scan_project
from litter_scoop.ignore import IgnoreMatcher
from litter_scoop.project import profile_project


class EngineIntegrationTests(unittest.TestCase):
    def test_scan_fixture_project(self):
        result = scan_project(FIXTURE_ROOT, Config())
        rule_ids = {f.rule_id for f in result.findings}
        # Every adapter family should fire at least once.
        for expected in (
            "unused-import",
            "unreachable-code",
            "unused-debug-statement",
            "empty-file",
            "duplicate-file",
            "backup-file",
        ):
            self.assertIn(expected, rule_ids, f"缺少规则 {expected}")

    def test_project_profile_autodetect(self):
        matcher = IgnoreMatcher.load(FIXTURE_ROOT)
        _, profile = profile_project(FIXTURE_ROOT, matcher)
        self.assertIn("python", profile.project_types)
        self.assertIn("node", profile.project_types)
        self.assertIn("react", profile.frameworks)
        self.assertIn("python", profile.adapters)
        self.assertIn("web", profile.adapters)
        self.assertIn("generic", profile.adapters)

    def test_whole_file_findings_marked(self):
        result = scan_project(FIXTURE_ROOT, Config())
        whole = {f.rule_id for f in result.findings if f.whole_file}
        self.assertIn("empty-file", whole)
        self.assertIn("duplicate-file", whole)

    def test_disable_rule_via_config(self):
        cfg = Config()
        cfg.disable_rules = {"commented-code", "empty-stub"}
        result = scan_project(FIXTURE_ROOT, cfg)
        rule_ids = {f.rule_id for f in result.findings}
        self.assertNotIn("commented-code", rule_ids)
        self.assertNotIn("empty-stub", rule_ids)


if __name__ == "__main__":
    unittest.main()
