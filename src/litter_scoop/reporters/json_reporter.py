"""JSON reporter (machine-readable, UTF-8, indent=2)."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime

from ..engine import ScanResult
from ..models import Severity


def render_json(result: ScanResult) -> str:
    by_severity = {s.value: 0 for s in Severity}
    for finding in result.findings:
        by_severity[finding.severity.value] += 1

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "project": {
            "root": str(result.profile.root),
            "project_types": result.profile.project_types,
            "frameworks": result.profile.frameworks,
            "languages_lines": result.profile.languages,
            "adapters": result.profile.adapters,
            "files_scanned": result.files_scanned,
            "skipped_binary": result.skipped_binary,
        },
        "summary": {
            "total": len(result.findings),
            "by_rule": dict(Counter(f.rule_id for f in result.findings)),
            "by_severity": by_severity,
        },
        "findings": [f.to_dict() for f in result.findings],
        "errors": result.errors,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
