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

CLAIM_GUNNCHAI = "GUNNCHAI_PLATFORM_INTEGRATION_DIGITALLY_COMPLETE"
CLAIM_ALL_18 = "ALL_18_WAIKE_TRACKS_DIGITALLY_AVAILABLE"
CLAIM_18_TRACK = "18_TRACK_PLATFORM_DELIVERY_DIGITALLY_COMPLETE"
ALL_18_CLAIMS = (CLAIM_ALL_18, CLAIM_18_TRACK)


def plain(proc: subprocess.CompletedProcess) -> str:
    return ANSI.sub("", (proc.stdout or "") + (proc.stderr or ""))


def run(cmd: list[str], cwd: Path | None = None, env: dict | None = None) -> subprocess.CompletedProcess:
    e = os.environ.copy()
    if env:
        e.update(env)
    e.setdefault("SOURCE_DATE_EPOCH", SOURCE_DATE_EPOCH)
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=cwd or ROOT, env=e, text=True, capture_output=True)


def _parse_pytest_counts(out: str) -> dict[str, int]:
    """Parse pytest -q summary line for passed/failed/skipped/xfailed."""
    counts = {"passed": 0, "failed": 0, "skipped": 0, "xfailed": 0, "error": 0}
    # e.g. "12 passed, 1 skipped in 3.2s" or "5 failed, 2 passed"
    for key in counts:
        m = re.search(rf"(\d+)\s+{key}", out)
        if m:
            counts[key] = int(m.group(1))
    return counts


def _seven_gc_blocks_18(matrix: dict) -> bool:
    for row in matrix.get("rows") or []:
        if row.get("track") != "SEVEN_GC_APPRENTICESHIP":
            continue
        return (
            row.get("final_status") == "BLOCKED"
            and "SEVEN_GC_SOURCE_BLOCKS_18_OF_18" in str(row.get("blocker") or "")
        )
    return False


def main() -> int:
    REPORTS.mkdir(exist_ok=True)
    results: dict[str, object] = {
        "generated_utc": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "AUTOMATED_PIPELINE_BLOCKED_BY_CODE",
        "claims": [],
        "claims_blocked": [],
        "checks": {},
        "test_counts": {},
        "blocked": [],
        "source_blockers": [],
        "exit_codes": {},
        "GATE_B_REQUIRED_TESTS_SKIPPED": None,
        "gunnchai": {
            "repo": "https://github.com/gunnchOS3k/gunnchAI3k",
            "discovered_sha": "4b4f411710e8cdb8102a7e11502f8497f68156b1",
            "ci_provider": "FakeGunnchAIProvider",
        },
        "claim_boundary": {
            "earned_only_with": [
                "Gate B CI required jobs SUCCESS including verify-gate-b",
                "AI policy + context isolation + prompt injection + grade safety PASS",
                "adversarial AI sabotage suite PASS",
                "ALL_18 claims require all 18 matrix rows PASS with SEVEN_GC COURSE_DIGITAL_RC (not shell-only)",
            ],
            "does_not_claim": [
                "human/field validation",
                "accessibility certification",
                "security certification",
                "local GGUF/llama inference availability",
                "Gate C interop / Device OS",
                "pedagogical learning effectiveness",
                "EXTERNAL physical/mentor/field gates for SEVEN_GC apprenticeship",
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
        "reports/GATE_B_GUNNCHAI_CONTRACT_SNAPSHOT.md",
        "reports/GATE_B_GUNNCHAI_CONTRACT_SNAPSHOT.json",
        "reports/GATE_B_CLOSURE_TRUTH.md",
        "reports/GATE_B_CLOSURE_VERIFICATION.json",
        "reports/SEVEN_GC_SOURCE_BLOCKS_18_OF_18.md",
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
    seven_gc_blocks = False
    digital_17_pass = False
    seven_gc_row = None
    if matrix_path.is_file():
        matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
        rows = matrix.get("rows") or []
        sys.path.insert(0, str(ROOT / "tools" / "course_compiler"))
        try:
            from course_compiler.tracks import CANONICAL_TRACK_IDS

            tracks = {r.get("track") for r in rows}
            matrix_ok = tracks == set(CANONICAL_TRACK_IDS) and len(rows) == 18
            all_pass = matrix_ok and all(r.get("final_status") == "PASS" for r in rows)
            seven_gc_blocks = _seven_gc_blocks_18(matrix)
            seven_gc_row = next(
                (r for r in rows if r.get("track") == "SEVEN_GC_APPRENTICESHIP"), None
            )
            other_pass = all(
                r.get("final_status") == "PASS"
                for r in rows
                if r.get("track") != "SEVEN_GC_APPRENTICESHIP"
            )
            digital_17_pass = matrix_ok and seven_gc_blocks and other_pass
            seven_gc_digital = bool(
                seven_gc_row
                and seven_gc_row.get("final_status") == "PASS"
                and int(seven_gc_row.get("lessons") or 0) > 0
                and int(seven_gc_row.get("assignments") or 0) > 0
                and int(seven_gc_row.get("quizzes") or 0) > 0
                and int(seven_gc_row.get("labs") or 0) > 0
            )
            results["matrix_summary"] = {
                "track_count": len(rows),
                "pass_count": sum(1 for r in rows if r.get("final_status") == "PASS"),
                "blocked_count": sum(1 for r in rows if r.get("final_status") == "BLOCKED"),
                "source_sha": matrix.get("source_sha"),
                "SEVEN_GC_SOURCE_BLOCKS_18_OF_18": seven_gc_blocks,
                "full_18_course_digital_rc": bool(all_pass and seven_gc_digital),
                "SEVEN_GC_DIGITAL_RC_PRESENT": seven_gc_digital,
            }
        except Exception as exc:  # noqa: BLE001
            results["blocked"].append(f"matrix_import_error:{exc}")
            seven_gc_digital = False
    else:
        seven_gc_digital = False
    results["checks"]["matrix_18_complete"] = matrix_ok
    results["checks"]["matrix_all_tracks_pass"] = all_pass
    results["checks"]["matrix_digital_17_pass_seven_gc_blocked"] = digital_17_pass
    results["checks"]["SEVEN_GC_SOURCE_BLOCKS_18_OF_18"] = seven_gc_blocks
    results["checks"]["SEVEN_GC_DIGITAL_RC_PRESENT"] = seven_gc_digital
    results["checks"]["matrix_honest_18_or_legacy_17"] = bool(
        (all_pass and seven_gc_digital and not seven_gc_blocks) or digital_17_pass
    )
    if not matrix_ok:
        results["blocked"].append("matrix_18_incomplete_or_missing")
    elif all_pass and not seven_gc_digital:
        # Dishonest: SEVEN_GC shell must not be PASS for all-18 digital delivery.
        results["blocked"].append("matrix_marks_all_18_pass_including_SEVEN_GC_shell")
    elif not results["checks"]["matrix_honest_18_or_legacy_17"]:
        results["blocked"].append("matrix_not_honest_18_pass_or_legacy_17_blocked")
    elif seven_gc_blocks:
        results["source_blockers"].append("SEVEN_GC_SOURCE_BLOCKS_18_OF_18")

    acceptance = REPORTS / "GATE_B_TRACK_ACCEPTANCE.json"
    acceptance_ok = False
    acceptance_skips = None
    if acceptance.is_file():
        acc = json.loads(acceptance.read_text(encoding="utf-8"))
        summary = acc.get("summary") or {}
        acceptance_ok = int(summary.get("track_count") or 0) == 18
        acceptance_skips = summary.get("GATE_B_REQUIRED_TESTS_SKIPPED")
        # Reject PENDING_SUITE leftovers
        blob = acceptance.read_text(encoding="utf-8")
        if "PENDING_SUITE" in blob:
            acceptance_ok = False
            results["blocked"].append("track_acceptance_contains_PENDING_SUITE")
        if summary.get("ALL_18_WAIKE_TRACKS_DIGITALLY_AVAILABLE") is True and (
            seven_gc_blocks or not all_pass or not seven_gc_digital
        ):
            results["blocked"].append("acceptance_falsely_claims_ALL_18")
        if summary.get("ALL_18_WAIKE_TRACKS_DIGITALLY_AVAILABLE") is False and (
            all_pass and seven_gc_digital and not seven_gc_blocks
        ):
            results["blocked"].append("acceptance_withholds_earned_ALL_18")
    results["checks"]["track_acceptance"] = acceptance_ok
    if not acceptance_ok:
        results["blocked"].append("track_acceptance_missing_or_incomplete")

    # Structural B1 check: default adapter must not select Fake without allow-flag.
    sys.path.insert(0, str(ROOT / "services" / "hub"))
    try:
        from app.modules.gunnchai_adapter import (  # noqa: WPS433
            DEFAULT_RUNTIME_HAS_NO_FAKE_AI,
            FakeGunnchAIProvider,
            GunnchAIAdapter,
        )

        saved_provider = os.environ.pop("GUNNCHAI_PROVIDER", None)
        saved_allow = os.environ.pop("WAIKE_ALLOW_FAKE_AI", None)
        try:
            default_adapter = GunnchAIAdapter()
            no_fake = DEFAULT_RUNTIME_HAS_NO_FAKE_AI and not isinstance(
                default_adapter.provider, FakeGunnchAIProvider
            )
        finally:
            if saved_provider is not None:
                os.environ["GUNNCHAI_PROVIDER"] = saved_provider
            if saved_allow is not None:
                os.environ["WAIKE_ALLOW_FAKE_AI"] = saved_allow
        results["checks"]["DEFAULT_RUNTIME_HAS_NO_FAKE_AI"] = no_fake
        if not no_fake:
            results["blocked"].append("fake_ai_active_by_default")
    except Exception as exc:  # noqa: BLE001
        results["checks"]["DEFAULT_RUNTIME_HAS_NO_FAKE_AI"] = False
        results["blocked"].append(f"fake_ai_default_check_error:{exc}")

    # Contract snapshot must not report drift.
    snap = REPORTS / "GATE_B_GUNNCHAI_CONTRACT_SNAPSHOT.json"
    if snap.is_file():
        snap_data = json.loads(snap.read_text(encoding="utf-8"))
        drift_ok = snap_data.get("status") == "PASS" and not snap_data.get("drift")
        results["checks"]["gunnchai_contract_snapshot_pass"] = bool(drift_ok)
        if not drift_ok:
            results["blocked"].append("GUNNCHAI_CONTRACT_DRIFT")
    else:
        results["checks"]["gunnchai_contract_snapshot_pass"] = False
        results["blocked"].append("missing_gunnchai_contract_snapshot")

    env = {
        "PYTHONPATH": f"{ROOT / 'services' / 'hub'}:{ROOT / 'tools' / 'course_compiler'}",
        "WAIKE_ROOT": str(waike),
        # Fake only via explicit test allow-flag — never production default.
        "WAIKE_ALLOW_FAKE_AI": "1",
        "GUNNCHAI_PROVIDER": "fake",
        "SOURCE_DATE_EPOCH": SOURCE_DATE_EPOCH,
    }
    py = str(ROOT / ".venv" / "bin" / "python3")
    if not Path(py).is_file():
        py = sys.executable

    total_skipped = 0
    ai_ok = None
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
        junit = REPORTS / "GATE_B_PYTEST_JUNIT.xml"
        ai_ok = True
        for name, files in suites.items():
            cmd = [py, "-m", "pytest", "-q", *files]
            if name == "e2e":
                cmd.extend(["--junitxml", str(junit)])
            proc = run(cmd, env=env)
            results["exit_codes"][f"pytest_{name}"] = proc.returncode
            out = plain(proc)
            counts = _parse_pytest_counts(out)
            results["test_counts"][name] = counts
            total_skipped += counts["skipped"]
            results["checks"][f"pytest_{name}"] = proc.returncode == 0 and counts["skipped"] == 0
            if name == "ai":
                ai_ok = bool(results["checks"][f"pytest_{name}"])
            if proc.returncode != 0:
                results["blocked"].append(f"pytest_{name}_failed")
                results[f"pytest_{name}_tail"] = out[-2000:]
            if counts["skipped"] != 0:
                results["blocked"].append(f"pytest_{name}_skipped={counts['skipped']}")
    else:
        # Prefer acceptance summary / prior junit evidence when verify does not re-run suites.
        if acceptance_skips is not None:
            total_skipped = int(acceptance_skips)
        summary_path = REPORTS / "GATE_B_PYTEST_SUMMARY.json"
        if summary_path.is_file():
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            total_skipped = int(summary.get("skipped") or total_skipped)
            if "ai_ok" in summary:
                ai_ok = bool(summary["ai_ok"])

    results["GATE_B_REQUIRED_TESTS_SKIPPED"] = total_skipped
    results["checks"]["GATE_B_REQUIRED_TESTS_SKIPPED_eq_0"] = total_skipped == 0
    if total_skipped != 0:
        results["blocked"].append(f"GATE_B_REQUIRED_TESTS_SKIPPED={total_skipped}")

    # AI gate evidence when suites not re-run: require AI policy + security matrices present.
    ai_artifacts_ok = (REPORTS / "GATE_B_AI_POLICY_MATRIX.json").is_file() and (
        REPORTS / "GATE_B_AI_SECURITY_MATRIX.json"
    ).is_file()
    if ai_ok is None:
        ai_ok = ai_artifacts_ok and bool(results["checks"].get("required_artifacts_present"))
    results["checks"]["ai_gates_pass"] = bool(ai_ok)

    head = run(["git", "rev-parse", "HEAD"])
    results["report_generated_from_sha"] = (head.stdout or "").strip()

    platform_ok = (
        bool(results["checks"].get("provenance_match"))
        and bool(results["checks"].get("pin_allows_18"))
        and bool(results["checks"].get("required_artifacts_present"))
        and bool(results["checks"].get("gate_b_yml_no_continue_on_error"))
        and bool(results["checks"].get("gate_b_yml_no_or_true"))
        and bool(results["checks"].get("matrix_18_complete"))
        and bool(results["checks"].get("matrix_honest_18_or_legacy_17"))
        and bool(results["checks"].get("track_acceptance"))
        and bool(results["checks"].get("GATE_B_REQUIRED_TESTS_SKIPPED_eq_0"))
        and bool(results["checks"].get("DEFAULT_RUNTIME_HAS_NO_FAKE_AI"))
        and bool(results["checks"].get("gunnchai_contract_snapshot_pass"))
        and not any(
            b.startswith("pytest_") or b.startswith("PROVENANCE") or b.startswith("missing")
            or b.startswith("gate-b.yml")
            or b.startswith("matrix_")
            or b.startswith("track_acceptance")
            or b.startswith("GATE_B_REQUIRED")
            or b.startswith("acceptance_")
            or b.startswith("fake_ai")
            or b.startswith("GUNNCHAI_CONTRACT")
            for b in (results["blocked"] or [])
        )
    )

    claims: list[str] = []
    claims_blocked: list[str] = []
    if platform_ok and results["checks"].get("ai_gates_pass"):
        claims.append(CLAIM_GUNNCHAI)
    else:
        claims_blocked.append(CLAIM_GUNNCHAI)

    # ALL_18 / 18_TRACK only when SEVEN_GC has real COURSE_DIGITAL_RC and all 18 PASS.
    if seven_gc_blocks or not all_pass or not seven_gc_digital:
        claims_blocked.extend(list(ALL_18_CLAIMS))
    elif platform_ok and all_pass and seven_gc_digital:
        claims.extend(list(ALL_18_CLAIMS))
    else:
        claims_blocked.extend(list(ALL_18_CLAIMS))

    results["claims"] = claims
    results["claims_blocked"] = claims_blocked

    if platform_ok and CLAIM_GUNNCHAI in claims:
        results["status"] = "AUTOMATED_PIPELINE_PASS"
    else:
        results["status"] = "AUTOMATED_PIPELINE_BLOCKED_BY_CODE"

    (REPORTS / "GATE_B_VERIFICATION.json").write_text(json.dumps(results, indent=2) + "\n")
    md = [
        "# Gate B Verification — gunnchAI + 18 WAIKE tracks",
        "",
        f"- Status: `{results['status']}`",
        f"- Claims: {', '.join(f'`{c}`' for c in (results.get('claims') or [])) or 'none'}",
        f"- Claims blocked: {', '.join(f'`{c}`' for c in (results.get('claims_blocked') or [])) or 'none'}",
        f"- Source blockers: {', '.join(f'`{c}`' for c in (results.get('source_blockers') or [])) or 'none'}",
        f"- GATE_B_REQUIRED_TESTS_SKIPPED: `{results.get('GATE_B_REQUIRED_TESTS_SKIPPED')}`",
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
    md.extend(["", "## Source blockers", ""])
    for b in results["source_blockers"] or ["none"]:
        md.append(f"- {b}")
    md.extend(
        [
            "",
            "## Claim boundary",
            "",
            "Earn `GUNNCHAI_PLATFORM_INTEGRATION_DIGITALLY_COMPLETE` when AI gates pass. "
            "Earn `ALL_18_WAIKE_TRACKS_DIGITALLY_AVAILABLE` and "
            "`18_TRACK_PLATFORM_DELIVERY_DIGITALLY_COMPLETE` only when all 18 matrix rows "
            "PASS with SEVEN_GC COURSE_DIGITAL_RC present (not shell-only). "
            "Does not claim human/field/a11y/security certification, fabricated local-model "
            "inference, EXTERNAL apprenticeship mentor/field gates, or Gate C.",
            "",
        ]
    )
    (REPORTS / "GATE_B_VERIFICATION.md").write_text("\n".join(md), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": results["status"],
                "claims": results["claims"],
                "claims_blocked": results["claims_blocked"],
                "GATE_B_REQUIRED_TESTS_SKIPPED": results["GATE_B_REQUIRED_TESTS_SKIPPED"],
            },
            indent=2,
        )
    )
    return 0 if results["status"] == "AUTOMATED_PIPELINE_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
