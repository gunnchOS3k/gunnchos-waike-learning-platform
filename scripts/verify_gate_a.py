#!/usr/bin/env python3
"""Aggregate Gate A offline sync + activity engine acceptance (honest PASS/BLOCKED)."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
SOURCE_DATE_EPOCH = os.environ.get("SOURCE_DATE_EPOCH", "1700000000")
CLAIM = "OFFLINE_AND_ACTIVITY_ENGINE_DIGITALLY_COMPLETE"


def run(cmd: list[str], cwd: Path | None = None, env: dict | None = None) -> subprocess.CompletedProcess:
    e = os.environ.copy()
    if env:
        e.update(env)
    e.setdefault("SOURCE_DATE_EPOCH", SOURCE_DATE_EPOCH)
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=cwd or ROOT, env=e, text=True, capture_output=True)


def main() -> int:
    REPORTS.mkdir(exist_ok=True)
    results: dict[str, object] = {
        "generated_utc": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "AUTOMATED_PIPELINE_BLOCKED_BY_CODE",
        "claim": None,
        "checks": {},
        "test_counts": {},
        "blocked": [],
        "exit_codes": {},
        "claim_boundary": {
            "earned_only_with": [
                "Gate A sync + activity suites PASS",
                "PR1–PR3 foundation regression PASS",
                "remote CI required jobs SUCCESS including verify-gate-a",
            ],
            "does_not_claim": [
                "human/field validation",
                "accessibility certification",
                "security certification",
                "hardware lab evidence",
                "Gate B gunnchAI / 18 tracks",
            ],
        },
    }

    pin = json.loads((ROOT / "curriculum/registry/PIN.json").read_text())
    results["declared_pinned_commit"] = pin.get("pinned_commit")
    waike = Path(
        os.environ.get("WAIKE_ROOT")
        or pin.get("absolute_path_hint")
        or (ROOT.parent / "waike-research-ops")
    )
    obs = run(["git", "-C", str(waike), "rev-parse", "HEAD"])
    results["exit_codes"]["waike_rev_parse"] = obs.returncode
    observed = (obs.stdout or "").strip() if obs.returncode == 0 else ""
    results["observed_source_commit"] = observed
    results["checks"]["provenance_match"] = bool(observed) and observed == pin.get("pinned_commit")
    if not results["checks"]["provenance_match"]:
        results["blocked"].append(
            f"PROVENANCE_MISMATCH declared={pin.get('pinned_commit')} observed={observed}"
        )

    env = {
        "PYTHONPATH": str(ROOT / "services" / "hub"),
        "WAIKE_ROOT": str(waike),
        "SOURCE_DATE_EPOCH": SOURCE_DATE_EPOCH,
    }
    pytest = ROOT / ".venv/bin/pytest"
    pt = run(
        [str(pytest), "-q", str(ROOT / "tests"), str(ROOT / "services/hub/tests")],
        env=env,
    )
    results["exit_codes"]["pytest"] = pt.returncode
    results["checks"]["python_tests"] = pt.returncode == 0
    out = (pt.stdout or "") + (pt.stderr or "")
    m = re.search(r"(\d+) passed", out)
    results["test_counts"]["python_passed"] = int(m.group(1)) if m else 0
    if pt.returncode != 0:
        results["blocked"].append("python_tests_failed")
        print(out[-4000:])

    gate_a = run(
        [str(pytest), "-q", str(ROOT / "tests/gate_a")],
        env=env,
    )
    results["exit_codes"]["gate_a"] = gate_a.returncode
    results["checks"]["gate_a_tests"] = gate_a.returncode == 0
    ga_out = (gate_a.stdout or "") + (gate_a.stderr or "")
    gm = re.search(r"(\d+) passed", ga_out)
    results["test_counts"]["gate_a_passed"] = int(gm.group(1)) if gm else 0
    if gate_a.returncode != 0:
        results["blocked"].append("gate_a_tests_failed")

    required_files = [
        "reports/GATE_A_SYNC_MATRIX.md",
        "reports/GATE_A_SYNC_MATRIX.json",
        "reports/GATE_A_ACTIVITY_MATRIX.md",
        "reports/GATE_A_ACTIVITY_MATRIX.json",
        "reports/GATE_A_ADVERSARIAL_REVIEW.md",
        "reports/GATE_A_PR_BODY.md",
        ".github/workflows/gate-a.yml",
        "services/hub/app/migrations/m004_offline_sync_activities.py",
        "services/hub/app/modules/sync.py",
        "services/hub/app/modules/activity_engine.py",
    ]
    missing = [f for f in required_files if not (ROOT / f).is_file()]
    results["checks"]["required_reports_present"] = len(missing) == 0
    if missing:
        results["blocked"].append(f"missing_files:{missing}")

    head = run(["git", "rev-parse", "HEAD"])
    results["report_generated_from_sha"] = (head.stdout or "").strip()

    ok = (
        results["checks"]["provenance_match"]
        and results["checks"]["python_tests"]
        and results["checks"]["gate_a_tests"]
        and results["checks"]["required_reports_present"]
        and not results["blocked"]
    )
    if ok:
        results["status"] = "AUTOMATED_PIPELINE_PASS"
        results["claim"] = CLAIM
    else:
        results["status"] = "AUTOMATED_PIPELINE_BLOCKED_BY_CODE"
        results["claim"] = None

    (REPORTS / "GATE_A_VERIFICATION.json").write_text(json.dumps(results, indent=2) + "\n")
    md = [
        "# Gate A Verification — Offline-first sync + activity engine",
        "",
        f"- Status: `{results['status']}`",
        f"- Claim: `{results.get('claim')}`",
        f"- report_generated_from_sha: `{results.get('report_generated_from_sha')}`",
        f"- declared_pinned_commit: `{results.get('declared_pinned_commit')}`",
        f"- observed_source_commit: `{results.get('observed_source_commit')}`",
        f"- python_passed: {results['test_counts'].get('python_passed')}",
        f"- gate_a_passed: {results['test_counts'].get('gate_a_passed')}",
        "",
        "## Checks",
        "",
    ]
    for k, v in (results["checks"] or {}).items():  # type: ignore[union-attr]
        md.append(f"- {'PASS' if v else 'FAIL'} `{k}`")
    md.extend(["", "## Blockers", ""])
    blockers = results["blocked"] or ["none"]
    for b in blockers:  # type: ignore[union-attr]
        md.append(f"- {b}")
    md.extend(
        [
            "",
            "## Claim boundary",
            "",
            "Earned only with green remote Gate A CI on the final head. "
            "Does not claim human/field/a11y/security certification, fabricated hardware evidence, or Gate B.",
            "",
        ]
    )
    (REPORTS / "GATE_A_VERIFICATION.md").write_text("\n".join(md))
    print(json.dumps({"status": results["status"], "claim": results["claim"]}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
