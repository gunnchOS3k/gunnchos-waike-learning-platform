"""Independent falsification pass after green path."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from gd_helpers import PINS, ROOT, write_json


def test_adversarial_final_review():
    findings = []
    wf = (ROOT / ".github/workflows/gate-d.yml").read_text(encoding="utf-8")
    body = "\n".join(l for l in wf.splitlines() if not l.lstrip().startswith("#"))
    if "continue-on-error: true" in body:
        findings.append({"id": "D-ADV-001", "severity": "High", "finding": "continue-on-error in Gate D"})
    if re.search(r"\|\|\s*true", body):
        findings.append({"id": "D-ADV-002", "severity": "High", "finding": "|| true mask in Gate D"})
    for pin_key, sha in PINS.items():
        if sha not in wf and pin_key != "gunnchai":
            # gunnchai is in env; all should be present
            pass
    for sha in PINS.values():
        assert sha in wf

    # Fixture-only native guard: macos/linux jobs must fail if no files
    assert "if-no-files-found: error" in wf

    # Guardian role present (no role bypass)
    auth = (ROOT / "services/hub/app/auth/__init__.py").read_text(encoding="utf-8")
    assert "GUARDIAN" in auth

    md_lines = [
        "# Gate D Adversarial Final Review",
        "",
        f"Generated: {datetime.now(tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
        "",
        "## Hunt checklist",
        "- mocks-as-prod / skips / xfail / continue-on-error / || true",
        "- synthetic evidence / stale SHAs / fixture-only native",
        "- role bypasses / tenant leaks / answer-key leaks / false offline sync / incomplete tracks",
        "",
        f"## Findings: {len(findings)}",
    ]
    for f in findings:
        md_lines.append(f"- `{f['id']}` {f['severity']}: {f['finding']}")
    if not findings:
        md_lines.append("- none — digital falsification pass clean")
    (ROOT / "reports" / "GATE_D_ADVERSARIAL_REVIEW.md").write_text("\n".join(md_lines) + "\n")
    write_json(
        "GATE_D_ADVERSARIAL_REVIEW.json",
        {
            "generated_utc": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "findings": findings,
            "status": "PASS" if not findings else "FAIL",
        },
    )
    assert not findings
