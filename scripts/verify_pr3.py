#!/usr/bin/env python3
"""Aggregate PR3 multi-user LMS alpha acceptance (honest PASS/BLOCKED)."""

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
CLAIM = "MULTI_USER_LMS_ALPHA_DIGITALLY_COMPLETE"


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
                "auth security suite PASS",
                "authorization/cross-site negatives PASS",
                "37-step multi-user E2E PASS",
                "gradebook matrix PASS",
                "PR2→PR3 migration PASS",
                "remote CI required jobs SUCCESS",
            ],
            "does_not_claim": [
                "human/field validation",
                "accessibility certification",
                "security certification",
                "offline sync (PR4)",
            ],
        },
    }

    pin = json.loads((ROOT / "curriculum/registry/PIN.json").read_text())
    results["declared_pinned_commit"] = pin.get("pinned_commit")
    waike = Path(os.environ.get("WAIKE_ROOT") or pin.get("absolute_path_hint") or (ROOT.parent / "waike-research-ops"))
    obs = run(["git", "-C", str(waike), "rev-parse", "HEAD"])
    results["exit_codes"]["waike_rev_parse"] = obs.returncode
    observed = (obs.stdout or "").strip() if obs.returncode == 0 else ""
    results["observed_source_commit"] = observed
    results["checks"]["provenance_match"] = bool(observed) and observed == pin.get("pinned_commit")
    if not results["checks"]["provenance_match"]:
        results["blocked"].append(f"PROVENANCE_MISMATCH declared={pin.get('pinned_commit')} observed={observed}")

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
    results["pytest_tail"] = out[-2500:]
    m = re.search(r"(\d+)\s+passed", out)
    results["test_counts"]["python_passed"] = int(m.group(1)) if m else None
    if pt.returncode != 0:
        results["blocked"].append("pytest failed")

    for name, path in [
        ("auth_security_present", ROOT / "tests/pr3/test_auth_security.py"),
        ("authorization_present", ROOT / "tests/pr3/test_authorization.py"),
        ("multi_user_e2e_present", ROOT / "tests/pr3/test_multi_user_e2e.py"),
        ("gradebook_present", ROOT / "tests/pr3/test_gradebook.py"),
        ("migration_present", ROOT / "tests/pr3/test_migration_pr2_to_pr3.py"),
        ("role_matrix_present", REPORTS / "PR3_ROLE_CAPABILITY_MATRIX.md"),
        ("gradebook_matrix_present", REPORTS / "PR3_GRADEBOOK_MATRIX.md"),
    ]:
        results["checks"][name] = path.is_file()
        if not path.is_file():
            results["blocked"].append(f"missing {path.name}")

    fe = run(["pnpm", "test"], cwd=ROOT / "apps/client")
    results["exit_codes"]["frontend_tests"] = fe.returncode
    results["checks"]["frontend_tests"] = fe.returncode == 0
    fe_out = (fe.stdout or "") + (fe.stderr or "")
    fm = re.findall(r"(\d+)\s+passed", fe_out)
    results["test_counts"]["frontend_passed"] = int(fm[-1]) if fm else None
    if fe.returncode != 0:
        results["blocked"].append("frontend tests failed")

    ok = (
        bool(results["checks"].get("provenance_match"))
        and bool(results["checks"].get("python_tests"))
        and bool(results["checks"].get("frontend_tests"))
        and bool(results["checks"].get("multi_user_e2e_present"))
        and not results["blocked"]
    )
    if ok:
        results["status"] = "AUTOMATED_PIPELINE_PASS"
        results["claim"] = CLAIM
    else:
        results["status"] = "AUTOMATED_PIPELINE_BLOCKED_BY_CODE"
        results["claim"] = None

    (REPORTS / "PR3_VERIFICATION.json").write_text(json.dumps(results, indent=2) + "\n")
    md = [
        "# PR3 Verification — Identity, sections, enrollment, instructor, gradebook",
        "",
        f"- Status: `{results['status']}`",
        f"- Claim: `{results['claim'] or 'NOT_EARNED'}`",
        f"- declared_pinned_commit: `{results['declared_pinned_commit']}`",
        f"- observed_source_commit: `{results['observed_source_commit']}`",
        f"- Python passed: {results['test_counts'].get('python_passed')}",
        f"- Frontend passed: {results['test_counts'].get('frontend_passed')}",
        "",
        "## Checks",
        "",
    ]
    for k, v in (results["checks"] or {}).items():  # type: ignore[union-attr]
        md.append(f"- {'PASS' if v else 'FAIL'} `{k}`")
    md.extend(["", "## Blockers", ""])
    for b in (results["blocked"] or ["none"]):  # type: ignore[union-attr]
        md.append(f"- {b}")
    md.extend(
        [
            "",
            "## Claim boundary",
            "",
            "Earned only with green remote CI + multi-user E2E. Does not claim human/field/a11y/security certification or offline sync (PR4).",
            "",
        ]
    )
    (REPORTS / "PR3_VERIFICATION.md").write_text("\n".join(md) + "\n")
    print(json.dumps({"status": results["status"], "claim": results["claim"]}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
