from __future__ import annotations

import unittest
from pathlib import Path

from _bootstrap import FIXTURE_ROOT, SRC  # noqa: F401
import sys; sys.path.insert(0, str(SRC))

from litter_scoop.adapters import AnalysisContext
from litter_scoop.adapters.python_adapter import PythonAdapter
from litter_scoop.config import Config


class PythonAdapterTests(unittest.TestCase):
    def setUp(self):
        self.app = FIXTURE_ROOT / "src" / "app.py"
        ctx = AnalysisContext(
            root=FIXTURE_ROOT, files=[self.app],
            relpaths={self.app: "src/app.py"}, config=Config(),
            global_name_refs={"shared_util": 1},
        )
        self.adapter = PythonAdapter(ctx)
        self.findings = self.adapter.analyze(
            self.app, "src/app.py", self.app.read_text(encoding="utf-8")
        )
        self.rules = {}
        for f in self.findings:
            self.rules.setdefault(f.rule_id, []).append(f)

    def test_unused_imports_detected(self):
        symbols = {f.symbol for f in self.rules.get("unused-import", [])}
        self.assertIn("os", symbols)
        self.assertIn("argv", symbols)
        # json is used, shared_util is used -> must not be flagged
        self.assertNotIn("json", symbols)
        self.assertNotIn("shared_util", symbols)

    def test_unused_toplevel_detected(self):
        symbols = {f.symbol for f in self.rules.get("unused-toplevel-symbol", [])}
        self.assertIn("dead_function", symbols)
        self.assertIn("DeadClass", symbols)
        # Used / guarded symbols stay
        self.assertNotIn("AliveClass", symbols)
        self.assertNotIn("helper", symbols)
        self.assertNotIn("main", symbols)

    def test_unused_local_detected(self):
        symbols = {f.symbol for f in self.rules.get("unused-local", [])}
        self.assertIn("unused_local", symbols)
        self.assertNotIn("total", symbols)

    def test_unreachable_detected(self):
        self.assertIn("unreachable-code", self.rules)

    def test_duplicate_definition_detected(self):
        symbols = {f.symbol for f in self.rules.get("duplicate-definition", [])}
        self.assertIn("duplicate", symbols)

    def test_empty_stub_detected(self):
        symbols = {f.symbol for f in self.rules.get("empty-stub", [])}
        self.assertIn("empty_one", symbols)

    def test_commented_code_detected(self):
        self.assertIn("commented-code", self.rules)

    def test_no_false_positive_on_clean_file(self):
        clean = FIXTURE_ROOT / "src" / "utils.py"
        ctx = AnalysisContext(
            root=FIXTURE_ROOT, files=[clean],
            relpaths={clean: "src/utils.py"}, config=Config(),
            global_name_refs={"shared_util": 2},
        )
        adapter = PythonAdapter(ctx)
        findings = adapter.analyze(clean, "src/utils.py", clean.read_text(encoding="utf-8"))
        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
