from __future__ import annotations

import sys
import unittest

from _bootstrap import FIXTURE_ROOT, SRC

sys.path.insert(0, str(SRC))

from litter_scoop.adapters import AnalysisContext
from litter_scoop.adapters.web_adapter import WebAdapter, build_code_mask
from litter_scoop.config import Config


class WebAdapterTests(unittest.TestCase):
    def setUp(self):
        self.js = FIXTURE_ROOT / "web" / "tool.js"
        ctx = AnalysisContext(
            root=FIXTURE_ROOT, files=[self.js],
            relpaths={self.js: "web/tool.js"}, config=Config(),
        )
        self.adapter = WebAdapter(ctx)
        self.findings = self.adapter.analyze(
            self.js, "web/tool.js", self.js.read_text(encoding="utf-8")
        )
        self.rules = {}
        for f in self.findings:
            self.rules.setdefault(f.rule_id, []).append(f)

    def test_unused_imports(self):
        symbols = {f.symbol for f in self.rules.get("unused-import", [])}
        self.assertIn("unusedThing", symbols)
        self.assertIn("axios", symbols)
        self.assertNotIn("usedThing", symbols)

    def test_unused_function(self):
        names = {f.symbol for f in self.rules.get("unused-top-level-function", [])}
        self.assertIn("neverCalled", names)
        self.assertNotIn("called", names)
        self.assertNotIn("run", names)

    def test_debug_statements(self):
        self.assertEqual(len(self.rules.get("unused-debug-statement", [])), 2)

    def test_commented_code(self):
        self.assertTrue(self.rules.get("commented-code"))

    def test_string_mask_prevents_false_positive(self):
        source = 'const note = "console.log(1)"; // console.log(2)\n'
        mask = build_code_mask(source)
        # Inside the string must be masked out.
        self.assertFalse(mask[source.index('"') + 1])


if __name__ == "__main__":
    unittest.main()
