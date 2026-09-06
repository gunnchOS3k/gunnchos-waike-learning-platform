#!/usr/bin/env python3
"""Aggregate Gate B gunnchAI + 18-track acceptance (honest PASS/BLOCKED)."""

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
ANSI = re.compile(r"\x1b\[[0-9;]*m")

CLAIMS = [
    "GUNNCHAI_PLATFORM_INTEGRATION_DIGITALLY_COMPLETE",
    "ALL_18_WAIKE_TRACKS_DIGITALLY_AVAILABLE",
    "18_TRACK_PLATFORM_DELIVERY_DIGITALLY_COMPLETE",
]


def plain(proc: subprocess.CompletedProcess) -> str:
    return ANSI.sub("", (proc.stdout or "") + (proc.stderr or ""))


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
        "claims": [],
        "checks": {},
        "test_counts": {},
        "blocked": [],
        "exit_codes": {},
        "gunnchai": {
            "repo": "https://github.com/gunnchOS3k/gunnchAI3k",
            "discovered_sha": "4b4f411710e8cdb8102a7e11502f8497f68156b1",
            "ci_provider": "FakeGunnchAIProvider",
        },
        "claim_boundary": {
            "earned_only_with": [
                "Gate B CI required jobs SUCCESS including verify-gate-b",
                "18-track compile/verify/decrypt + install/learner/instructor/offline suites",
                "AI policy + context isolation + prompt injection + grade safety PASS",
                "adversarial AI sabotage suite PASS",
            ],
            "does_not_claim": [
                "human/field validation",
                "accessibility certification",
                "security certification",
                "local GGUF/llama inference availability",
                "Gate C interop / Device OS",
                "pedagogical learning effectiveness",
            ],
        },
    }

    pin = json.loads((ROOT / "curriculum/registry/PIN.json").read_text(encoding="utf-8"))
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

    allowed = set(pin.get("module_ids_allowed") or [])
    results["checks"]["pin_allows_18"] = len(allowed) == 18
    if not results["checks"]["pin_allows_18"]:
        results["blocked"].append(f"PIN module_ids_allowed count={len(allowed)} expected=18")

    required_files = [
        "reports/WAIKE_18_TRACK_PACKAGE_MATRIX.json",
        "reports/WAIKE_18_TRACK_PACKAGE_MATRIX.md",
        "reports/WAIKE_18_TRACK_PACKAGE_MATRIX.csv",
        "reports/GATE_B_AI_POLICY_MATRIX.json",
        "reports/GATE_B_AI_SECURITY_MATRIX.json",
        "reports/GATE_B_ADVERSARIAL_REVIEW.md",
        "reports/GATE_B_TRACK_ACCEPTANCE.json",
        "reports/GATE_B_GUNNCHAI_CONTRACT_DISCOVERY.md",
        ".github/workflows/gate-b.yml",
        "services/hub/app/modules/ai_policy.py",
        "services/hub/app/modules/ai_assist.py",
        "services/hub/app/modules/gunnchai_adapter.py",
        "services/hub/app/migrations/m005_ai_policy.py",
        "apps/client/src/components/ai/AiPanels.tsx",
        "apps/client/src/test/a11y.gate-b.test.tsx",
    ]
    missing = [f for f in required_files if not (ROOT / f).is_file()]
    results["checks"]["required_artifacts_present"] = len(missing) == 0
    if missing:
        results["blocked"].append(f"missing_files:{missing}")

    # Forbidden CI masks in gate-b.yml jobs (comments mentioning them are OK)
    wf = (ROOT / ".github/workflows/gate-b.yml").read_text(encoding="utf-8")
    job_body = "\n".join(
        line for line in wf.splitlines() if not line.lstrip().startswith("#")
    )
    results["checks"]["gate_b_yml_no_continue_on_error"] = "continue-on-error" not in job_body
    results["checks"]["gate_b_yml_no_or_true"] = "|| true" not in job_body and "||true" not in job_body
    if not results["checks"]["gate_b_yml_no_continue_on_error"]:
        results["blocked"].append("gate-b.yml uses continue-on-error")
    if not results["checks"]["gate_b_yml_no_or_true"]:
        results["blocked"].append("gate-b.yml uses || true")

    matrix_path = REPORTS / "WAIKE_18_TRACK_PACKAGE_MATRIX.json"
    matrix_ok = False
    all_pass = False
    if matrix_path.is_file():
        matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
        rows = matrix.get("rows") or []
        sys.path.insert(0, str(ROOT / "tools" / "course_compiler"))
        try:
            from course_compiler.tracks import CANONICAL_TRACK_IDS

            tracks = {r.get("track") for r in rows}
            matrix_ok = tracks == set(CANONICAL_TRACK_IDS) and len(rows) == 18
            all_pass = matrix_ok and all(r.get("final_status") == "PASS" for r in rows)
            results["matrix_summary"] = {
                "track_count": len(rows),
                "pass_count": sum(1 for r in rows if r.get("final_status") == "PASS"),
                "source_sha": matrix.get("source_sha"),
            }
        except Exception as exc:  # noqa: BLE001
            results["blocked"].append(f"matrix_import_error:{exc}")
    results["checks"]["matrix_18_complete"] = matrix_ok
    results["checks"]["matrix_all_tracks_pass"] = all_pass
    if not matrix_ok:
        results["blocked"].append("matrix_18_incomplete_or_missing")
    elif not all_pass:
        results["blocked"].append("matrix_has_non_pass_tracks")

    acceptance = REPORTS / "GATE_B_TRACK_ACCEPTANCE.json"
    acceptance_ok = False
    if acceptance.is_file():
        acc = json.loads(acceptance.read_text(encoding="utf-8"))
        acceptance_ok = int((acc.get("summary") or {}).get("track_count") or 0) == 18
    results["checks"]["track_acceptance"] = acceptance_ok
    if not acceptance_ok:
        results["blocked"].append("track_acceptance_missing_or_incomplete")

    env = {
        "PYTHONPATH": f"{ROOT / 'services' / 'hub'}:{ROOT / 'tools' / 'course_compiler'}",
        "WAIKE_ROOT": str(waike),
        "GUNNCHAI_PROVIDER": "fake",
        "SOURCE_DATE_EPOCH": SOURCE_DATE_EPOCH,
    }
    py = str(ROOT / ".venv" / "bin" / "python3")
    if not Path(py).is_file():
        py = sys.executable

    # Optional local suites when VERIFY_GATE_B_RUN_TESTS=1 (CI verify job relies on needs:)
    if os.environ.get("VERIFY_GATE_B_RUN_TESTS", "").lower() in {"1", "true", "yes"}:
        suites = {
            "ai": [
                "tests/gate_b/test_ai_policy.py",
                "tests/gate_b/test_ai_context_isolation.py",
                "tests/gate_b/test_ai_prompt_injection.py",
                "tests/gate_b/test_ai_grade_safety.py",
                "tests/gate_b/test_gunnchai_contract.py",
                "tests/gate_b/test_adversarial_ai_sabotage.py",
            ],
            "compiler": [
                "tests/gate_b/test_compiler_18.py",
                "tests/gate_b/test_package_security_18.py",
                "tests/gate_b/test_activity_coverage_18.py",
            ],
            "e2e": [
                "tests/gate_b/test_install_18.py",
                "tests/gate_b/test_learner_18.py",
                "tests/gate_b/test_instructor_18.py",
                "tests/gate_b/test_offline_18.py",
                "tests/gate_b/test_track_acceptance_e2e.py",
            ],
        }
        for name, files in suites.items():
            proc = run([py, "-m", "pytest", "-q", *files], env=env)
            results["exit_codes"][f"pytest_{name}"] = proc.returncode
            out = plain(proc)
            m = re.search(r"(\d+) passed", out)
            results["test_counts"][name] = int(m.group(1)) if m else None
            results["checks"][f"pytest_{name}"] = proc.returncode == 0
            if proc.returncode != 0:
                results["blocked"].append(f"pytest_{name}_failed")
                results[f"pytest_{name}_tail"] = out[-2000:]

    head = run(["git", "rev-parse", "HEAD"])
    results["report_generated_from_sha"] = (head.stdout or "").strip()

    ok = (
        bool(results["checks"].get("provenance_match"))
        and bool(results["checks"].get("pin_allows_18"))
        and bool(results["checks"].get("required_artifacts_present"))
        and bool(results["checks"].get("gate_b_yml_no_continue_on_error"))
        and bool(results["checks"].get("gate_b_yml_no_or_true"))
        and bool(results["checks"].get("matrix_18_complete"))
        and bool(results["checks"].get("matrix_all_tracks_pass"))
        and bool(results["checks"].get("track_acceptance"))
        and not results["blocked"]
    )
    if ok:
        results["status"] = "AUTOMATED_PIPELINE_PASS"
        results["claims"] = list(CLAIMS)
    else:
        results["status"] = "AUTOMATED_PIPELINE_BLOCKED_BY_CODE"
        results["claims"] = []

    (REPORTS / "GATE_B_VERIFICATION.json").write_text(json.dumps(results, indent=2) + "\n")
    md = [
        "# Gate B Verification — gunnchAI + 18 WAIKE tracks",
        "",
        f"- Status: `{results['status']}`",
        f"- Claims: {', '.join(f'`{c}`' for c in (results.get('claims') or [])) or 'none'}",
        f"- report_generated_from_sha: `{results.get('report_generated_from_sha')}`",
        f"- declared_pinned_commit: `{results.get('declared_pinned_commit')}`",
        f"- observed_source_commit: `{results.get('observed_source_commit')}`",
        f"- gunnchAI discovered SHA: `{results['gunnchai']['discovered_sha']}`",
        "",
        "## Checks",
        "",
    ]
    for k, v in (results["checks"] or {}).items():
        md.append(f"- {'PASS' if v else 'FAIL'} `{k}`")
    md.extend(["", "## Blockers", ""])
    for b in results["blocked"] or ["none"]:
        md.append(f"- {b}")
    md.extend(
        [
            "",
            "## Claim boundary",
            "",
            "Earned only with green remote Gate B CI on the final head. "
            "Does not claim human/field/a11y/security certification, fabricated local-model "
            "inference, or Gate C.",
            "",
        ]
    )
    (REPORTS / "GATE_B_VERIFICATION.md").write_text("\n".join(md), encoding="utf-8")
    print(json.dumps({"status": results["status"], "claims": results["claims"]}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
